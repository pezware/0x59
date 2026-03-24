"""Shared test fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from zx59.db import DB


@pytest.fixture
def db(tmp_path: Path) -> Iterator[DB]:
    """Create a fresh DB instance backed by a temporary file."""
    database = DB(tmp_path / "test.db")
    yield database
    database.close()


class FakeClaude:
    """Test double for ClaudeRunner. Returns pre-configured responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, str, str]] = []

    def run(self, prompt: str, model: str, json_schema: str) -> str:
        self.calls.append((prompt, model, json_schema))
        return next(self._responses)


def make_response(
    message: str,
    decision: bool = False,
    summary: str | None = None,
    artifacts: list[dict[str, str]] | None = None,
) -> str:
    """Build a JSON response string for FakeClaude."""
    r: dict[str, object] = {"message": message, "decision_reached": decision}
    if summary is not None:
        r["decision_summary"] = summary
    if artifacts is not None:
        r["artifacts"] = artifacts
    return json.dumps(r)


def setup_channel(db: DB, max_turns: int = 20) -> str:
    """Create a channel with two default participants."""
    channel_id = db.create_channel(topic="Test topic", model="sonnet", max_turns=max_turns)
    db.add_participant(channel_id, "proposer", "participant", system_prompt="You propose.")
    db.add_participant(channel_id, "challenger", "participant", system_prompt="You challenge.")
    return channel_id
