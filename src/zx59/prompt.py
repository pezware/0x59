"""Prompt assembly for agent turns."""

from __future__ import annotations

from zx59.db import Message


def build_prompt(
    system_prompt: str,
    messages: list[Message],
    topic: str,
    current_agent: str,
    agenda: str | None = None,
) -> str:
    """Assemble a prompt string for claude -p."""
    parts: list[str] = []

    parts.append(f"[System]\n{system_prompt}")
    parts.append(f"[Topic]\n{topic}")

    if agenda is not None:
        parts.append(f"[Agenda]\n{agenda}")

    if messages:
        conversation = "\n".join(f"{m.sender}: {m.content}" for m in messages)
        parts.append(f"[Conversation]\n{conversation}")

    parts.append(
        f"[Your Turn]\n"
        f"You are {current_agent}. Respond to the conversation above.\n"
        f"Set decision_reached to true when you believe consensus has been reached."
    )

    return "\n\n".join(parts)
