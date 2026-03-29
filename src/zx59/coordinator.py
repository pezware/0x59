"""Coordinator turn engine for inter-agent conversations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from zx59.context import estimate_tokens, window_messages
from zx59.db import DB
from zx59.errors import ClaudeResponseError
from zx59.prompt import build_prompt
from zx59.schema import schema_json


class ClaudeRunner(Protocol):
    """Interface for calling Claude. Injected into Coordinator for testability."""

    def run(
        self, prompt: str, model: str, json_schema: str, *, session_name: str | None = None
    ) -> str: ...


@dataclass(frozen=True)
class TurnInfo:
    """Info emitted after each turn for live display."""

    turn: int
    max_turns: int
    agent_id: str
    message: str
    decision_reached: bool


@dataclass(frozen=True)
class ConversationResult:
    """Outcome of a coordinator run."""

    channel_id: str
    status: str  # "decided" | "max_turns" | "error"
    total_turns: int
    decision: str | None


class Coordinator:
    """Turn-based conversation engine between Claude agents."""

    def __init__(self, db: DB, runner: ClaudeRunner) -> None:
        self._db = db
        self._runner = runner

    def run(
        self,
        channel_id: str,
        max_turns: int | None = None,
        *,
        on_turn: Callable[[TurnInfo], None] | None = None,
    ) -> ConversationResult:
        """Run a conversation to completion or max turns."""
        channel = self._db.get_channel(channel_id)
        if channel is None:
            raise ValueError(f"Channel {channel_id} not found")

        if max_turns is None:
            max_turns = channel.max_turns

        participants = self._db.get_participants(channel_id)
        agents = [p for p in participants if p.role == "participant"]
        if len(agents) < 2:
            raise ValueError(f"Channel {channel_id} needs at least 2 participants")

        pending_decision_by: str | None = None
        turn = 0
        json_schema = schema_json()

        for turn in range(1, max_turns + 1):
            agent = agents[(turn - 1) % len(agents)]
            model = agent.model or channel.model

            messages = self._db.get_messages(channel_id)
            windowed = window_messages(messages)
            prompt = build_prompt(
                system_prompt=agent.system_prompt or "",
                messages=windowed,
                topic=channel.topic,
                current_agent=agent.agent_id,
                agenda=channel.agenda,
            )

            session_name = f"0x59 | {agent.agent_id} | {channel.topic[:50]}"
            raw = self._runner.run(prompt, model, json_schema, session_name=session_name)

            try:
                response = json.loads(raw)
            except json.JSONDecodeError as err:
                raise ClaudeResponseError(raw) from err

            content: str = response.get("message", "")

            token_est = estimate_tokens(content)
            decision_reached = bool(response.get("decision_reached", False))
            msg_type = "decision" if decision_reached else "chat"

            msg_id = self._db.append_message(
                channel_id, agent.agent_id, content, msg_type, token_est
            )

            if on_turn:
                on_turn(TurnInfo(turn, max_turns, agent.agent_id, content, decision_reached))

            # Save any artifacts
            for artifact in response.get("artifacts", []):
                self._db.save_artifact(
                    channel_id=channel_id,
                    name=artifact["name"],
                    content=artifact["content"],
                    message_id=msg_id,
                    content_type=artifact.get("content_type", "text/markdown"),
                )

            # Decision detection: two different agents must agree consecutively
            if decision_reached:
                if pending_decision_by is not None and pending_decision_by != agent.agent_id:
                    decision_summary = response.get("decision_summary", content)
                    self._db.decide_channel(channel_id, decision_summary)
                    return ConversationResult(channel_id, "decided", turn, decision_summary)
                pending_decision_by = agent.agent_id
            else:
                pending_decision_by = None

        return ConversationResult(channel_id, "max_turns", turn, None)
