"""Tests for message windowing and token estimation."""

from __future__ import annotations

from zx59.context import estimate_tokens, window_messages
from zx59.db import Message


def _msg(id: int, content: str, sender: str = "a") -> Message:
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


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert estimate_tokens("hello world") == 2  # 11 chars // 4

    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_short(self) -> None:
        assert estimate_tokens("hi") == 0  # 2 chars // 4


class TestWindowMessages:
    def test_short_conversation_unchanged(self) -> None:
        messages = [_msg(i, f"msg {i}") for i in range(5)]
        result = window_messages(messages)
        assert result == messages

    def test_ten_messages_unchanged(self) -> None:
        messages = [_msg(i, f"msg {i}") for i in range(10)]
        result = window_messages(messages)
        assert result == messages

    def test_medium_conversation_keeps_first_and_last_five(self) -> None:
        messages = [_msg(i, f"msg {i}") for i in range(15)]
        result = window_messages(messages)
        assert len(result) == 6  # first + last 5
        assert result[0] == messages[0]
        assert result[1:] == messages[10:]

    def test_long_conversation_keeps_first_and_last_three(self) -> None:
        messages = [_msg(i, f"msg {i}") for i in range(25)]
        result = window_messages(messages)
        assert len(result) == 4  # first + last 3
        assert result[0] == messages[0]
        assert result[1:] == messages[22:]

    def test_empty_input_returns_empty(self) -> None:
        assert window_messages([]) == []

    def test_single_message_preserved(self) -> None:
        messages = [_msg(0, "x" * 10000)]
        result = window_messages(messages)
        assert result == messages

    def test_eleven_messages_triggers_windowing(self) -> None:
        messages = [_msg(i, f"msg {i}") for i in range(11)]
        result = window_messages(messages)
        assert len(result) == 6  # first + last 5
        assert result[0] == messages[0]
        assert result[1:] == messages[6:]

    def test_twenty_one_messages_triggers_aggressive_windowing(self) -> None:
        messages = [_msg(i, f"msg {i}") for i in range(21)]
        result = window_messages(messages)
        assert len(result) == 4  # first + last 3
        assert result[0] == messages[0]
        assert result[1:] == messages[18:]
