"""Claude CLI runner implementation."""

from __future__ import annotations

import json
import shutil
import subprocess

from zx59.errors import ClaudeError, ClaudeResponseError

__all__ = ["ClaudeError", "ClaudeResponseError", "SubprocessClaudeRunner"]


class SubprocessClaudeRunner:
    """Real ClaudeRunner that calls claude -p via subprocess."""

    def __init__(self) -> None:
        if shutil.which("claude") is None:
            raise ClaudeError(-1, "Claude Code CLI not found in PATH")

    def run(
        self, prompt: str, model: str, json_schema: str, *, session_name: str | None = None
    ) -> str:
        cmd = [
            "claude",
            "-p",
            "--no-session-persistence",
            "--model",
            model,
            "--output-format",
            "json",
            "--json-schema",
            json_schema,
        ]
        if session_name:
            cmd.extend(["-n", session_name])
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise ClaudeError(result.returncode, result.stderr)

        raw = result.stdout
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as err:
            raise ClaudeResponseError(raw) from err

        # Claude CLI wraps output in an envelope. With --json-schema the
        # parsed object lands in "structured_output" while "result" is empty.
        if isinstance(envelope, dict):
            structured = envelope.get("structured_output")
            if isinstance(structured, dict):
                return json.dumps(structured)
            inner = envelope.get("result")
            if inner:
                return str(inner) if not isinstance(inner, str) else inner

        return raw
