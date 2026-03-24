"""Coordinator turn engine for inter-agent conversations."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

from zx59.context import estimate_tokens, window_messages
from zx59.db import DB
from zx59.prompt import build_prompt
from zx59.schema import schema_json


class ClaudeRunner(Protocol):
    """Interface for calling Claude. Injected into Coordinator for testability."""

    def run(self, prompt: str, model: str, json_schema: str) -> str: ...


@dataclass(frozen=True)
class ConversationResult:
    """Outcome of a coordinator run."""

    channel_id: str
    status: str  # "decided" | "max_turns" | "error"
    total_turns: int
    decision: str | None


class ClaudeError(Exception):
    """Raised when the claude CLI returns a non-zero exit code."""

    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"claude exited with code {returncode}: {stderr}")


class ClaudeResponseError(Exception):
    """Raised when claude output is not valid JSON."""

    def __init__(self, raw_output: str) -> None:
        self.raw_output = raw_output
        super().__init__(f"Invalid JSON response: {raw_output[:200]}")


class SubprocessClaudeRunner:
    """Real ClaudeRunner that calls claude -p via subprocess."""

    def __init__(self) -> None:
        if shutil.which("claude") is None:
            raise ClaudeError(-1, "Claude Code CLI not found in PATH")

    def run(self, prompt: str, model: str, json_schema: str) -> str:
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                model,
                "--output-format",
                "json",
                "--json-schema",
                json_schema,
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise ClaudeError(result.returncode, result.stderr)
        return result.stdout


class Coordinator:
    """Turn-based conversation engine between Claude agents."""

    def __init__(self, db: DB, runner: ClaudeRunner) -> None:
        self._db = db
        self._runner = runner

    def run(self, channel_id: str, max_turns: int | None = None) -> ConversationResult:
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

        pending_decision = False
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

            raw = self._runner.run(prompt, model, json_schema)

            try:
                response = json.loads(raw)
            except json.JSONDecodeError as err:
                raise ClaudeResponseError(raw) from err

            # Extract message from Claude's JSON envelope if present
            content: str = response.get("result", response.get("message", ""))
            if "message" in response and "result" not in response:
                content = response["message"]

            token_est = estimate_tokens(content)
            decision_reached = bool(response.get("decision_reached", False))
            msg_type = "decision" if decision_reached else "chat"

            msg_id = self._db.append_message(
                channel_id, agent.agent_id, content, msg_type, token_est
            )

            # Save any artifacts
            for artifact in response.get("artifacts", []):
                self._db.save_artifact(
                    channel_id=channel_id,
                    name=artifact["name"],
                    content=artifact["content"],
                    message_id=msg_id,
                    content_type=artifact.get("content_type", "text/markdown"),
                )

            # Decision detection: both agents must agree consecutively
            if decision_reached:
                if pending_decision:
                    decision_summary = response.get("decision_summary", content)
                    self._db.decide_channel(channel_id, decision_summary)
                    return ConversationResult(channel_id, "decided", turn, decision_summary)
                pending_decision = True
            else:
                pending_decision = False

        return ConversationResult(channel_id, "max_turns", turn, None)
