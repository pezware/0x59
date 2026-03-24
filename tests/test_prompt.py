"""Tests for prompt assembly."""

from __future__ import annotations

from zx59.db import Message
from zx59.prompt import build_prompt


def _msg(id: int, content: str, sender: str = "agent-a") -> Message:
    """Create a test Message with minimal required fields."""
    return Message(
        id=id,
        channel_id="test",
        sender=sender,
        content=content,
        msg_type="chat",
        token_estimate=None,
        created_at="2025-01-01",
    )


class TestBuildPrompt:
    def test_system_prompt_appears_first(self) -> None:
        prompt = build_prompt(
            system_prompt="You are helpful.",
            messages=[],
            topic="Test",
            current_agent="agent-a",
        )
        lines = prompt.strip().split("\n")
        assert lines[0] == "[System]"
        assert lines[1] == "You are helpful."

    def test_topic_included(self) -> None:
        prompt = build_prompt(
            system_prompt="Role.",
            messages=[],
            topic="Auth design",
            current_agent="agent-a",
        )
        assert "[Topic]" in prompt
        assert "Auth design" in prompt

    def test_messages_in_order(self) -> None:
        messages = [
            _msg(1, "First message", sender="agent-a"),
            _msg(2, "Second message", sender="agent-b"),
            _msg(3, "Third message", sender="agent-a"),
        ]
        prompt = build_prompt(
            system_prompt="Role.",
            messages=messages,
            topic="Test",
            current_agent="agent-a",
        )
        first_pos = prompt.index("First message")
        second_pos = prompt.index("Second message")
        third_pos = prompt.index("Third message")
        assert first_pos < second_pos < third_pos

    def test_agent_names_in_messages(self) -> None:
        messages = [_msg(1, "Hello", sender="architect")]
        prompt = build_prompt(
            system_prompt="Role.",
            messages=messages,
            topic="Test",
            current_agent="reviewer",
        )
        assert "architect: Hello" in prompt

    def test_agenda_included_when_provided(self) -> None:
        prompt = build_prompt(
            system_prompt="Role.",
            messages=[],
            topic="Test",
            current_agent="agent-a",
            agenda="1. First\n2. Second",
        )
        assert "[Agenda]" in prompt
        assert "1. First" in prompt

    def test_agenda_absent_when_none(self) -> None:
        prompt = build_prompt(
            system_prompt="Role.",
            messages=[],
            topic="Test",
            current_agent="agent-a",
        )
        assert "[Agenda]" not in prompt

    def test_current_agent_in_instruction(self) -> None:
        prompt = build_prompt(
            system_prompt="Role.",
            messages=[],
            topic="Test",
            current_agent="reviewer",
        )
        assert "reviewer" in prompt.split("[Your Turn]")[-1]

    def test_empty_messages_still_has_structure(self) -> None:
        prompt = build_prompt(
            system_prompt="Role.",
            messages=[],
            topic="Test",
            current_agent="agent-a",
        )
        assert "[System]" in prompt
        assert "[Topic]" in prompt
        assert "[Your Turn]" in prompt
