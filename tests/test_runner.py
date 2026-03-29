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
