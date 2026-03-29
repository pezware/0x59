"""Tests for the Claude CLI runner."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from zx59.runner import ClaudeError, ClaudeResponseError, SubprocessClaudeRunner


class TestSubprocessClaudeRunnerEnvelope:
    """Verify the runner unwraps the Claude CLI JSON envelope."""

    def test_unwraps_envelope_returns_inner_result(self) -> None:
        inner_json = json.dumps({"message": "hello", "decision_reached": False})
        envelope = json.dumps({"type": "result", "result": inner_json, "subtype": "success"})
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result),
        ):
            runner = SubprocessClaudeRunner()
            output = runner.run("prompt", "sonnet", "{}")

        assert output == inner_json

    def test_returns_raw_when_no_envelope(self) -> None:
        raw_json = json.dumps({"message": "hello", "decision_reached": False})
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=raw_json, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result),
        ):
            runner = SubprocessClaudeRunner()
            output = runner.run("prompt", "sonnet", "{}")

        assert output == raw_json

    def test_raises_on_non_zero_exit(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error msg"
        )

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result),
        ):
            runner = SubprocessClaudeRunner()
            with pytest.raises(ClaudeError, match="error msg"):
                runner.run("prompt", "sonnet", "{}")

    def test_unwraps_structured_output_when_result_empty(self) -> None:
        """Claude CLI puts structured output in 'structured_output', not 'result'."""
        structured = {"message": "hello", "decision_reached": False}
        envelope = json.dumps({"type": "result", "result": "", "structured_output": structured})
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result),
        ):
            runner = SubprocessClaudeRunner()
            output = runner.run("prompt", "sonnet", "{}")

        assert json.loads(output) == structured

    def test_prefers_structured_output_over_result(self) -> None:
        """When both are present, structured_output wins."""
        structured = {"message": "from structured", "decision_reached": True}
        envelope = json.dumps(
            {"type": "result", "result": "stale", "structured_output": structured}
        )
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result),
        ):
            runner = SubprocessClaudeRunner()
            output = runner.run("prompt", "sonnet", "{}")

        assert json.loads(output) == structured

    def test_passes_session_name_flag(self) -> None:
        """When session_name is given, runner passes -n to claude."""
        inner_json = json.dumps({"message": "hi", "decision_reached": False})
        envelope = json.dumps({"type": "result", "result": inner_json})
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result) as mock_run,
        ):
            runner = SubprocessClaudeRunner()
            runner.run("prompt", "sonnet", "{}", session_name="0x59 | agent | Topic")

        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd
        name_idx = cmd.index("-n")
        assert cmd[name_idx + 1] == "0x59 | agent | Topic"

    def test_uses_no_session_persistence(self) -> None:
        """Runner should pass --no-session-persistence to avoid orphan sessions."""
        inner_json = json.dumps({"message": "hi", "decision_reached": False})
        envelope = json.dumps({"type": "result", "result": inner_json})
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result) as mock_run,
        ):
            runner = SubprocessClaudeRunner()
            runner.run("prompt", "sonnet", "{}")

        cmd = mock_run.call_args[0][0]
        assert "--no-session-persistence" in cmd

    def test_omits_name_flag_when_no_session_name(self) -> None:
        inner_json = json.dumps({"message": "hi", "decision_reached": False})
        envelope = json.dumps({"type": "result", "result": inner_json})
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout=envelope, stderr="")

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result) as mock_run,
        ):
            runner = SubprocessClaudeRunner()
            runner.run("prompt", "sonnet", "{}")

        cmd = mock_run.call_args[0][0]
        assert "-n" not in cmd

    def test_raises_on_invalid_json(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not json at all", stderr=""
        )

        with (
            patch("zx59.runner.shutil.which", return_value="/usr/bin/claude"),
            patch("zx59.runner.subprocess.run", return_value=mock_result),
        ):
            runner = SubprocessClaudeRunner()
            with pytest.raises(ClaudeResponseError, match="Invalid JSON"):
                runner.run("prompt", "sonnet", "{}")
