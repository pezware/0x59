"""Message windowing for context management."""

from __future__ import annotations

from zx59.db import Message


def estimate_tokens(text: str) -> int:
    """Naive token estimate: ~1 token per 4 characters."""
    return len(text) // 4


def window_messages(messages: list[Message]) -> list[Message]:
    """Apply windowing strategy based on conversation length.

    - ≤10 messages: return all
    - 11-20 messages: first message + last 5
    - 21+ messages: first message + last 3
    """
    n = len(messages)
    if n <= 10:
        return messages
    if n <= 20:
        return [messages[0], *messages[-5:]]
    return [messages[0], *messages[-3:]]
