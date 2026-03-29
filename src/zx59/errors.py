"""Shared exception types for 0x59."""

from __future__ import annotations


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
