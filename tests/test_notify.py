"""Tests for desktop notifications."""

from __future__ import annotations

from unittest.mock import patch

from zx59.notify import notify


class TestNotify:
    def test_does_not_raise_on_failure(self) -> None:
        with patch("zx59.notify.subprocess.run", side_effect=OSError("no command")):
            notify("Test", "Message")  # should not raise

    def test_does_not_raise_on_unknown_platform(self) -> None:
        with patch("zx59.notify.platform.system", return_value="Unknown"):
            notify("Test", "Message")  # should not raise

    def test_backslash_quote_escaped_on_macos(self) -> None:
        """A backslash-quote in input must not break out of the AppleScript string."""
        with (
            patch("zx59.notify.platform.system", return_value="Darwin"),
            patch("zx59.notify.subprocess.run") as mock_run,
        ):
            # Input: literal backslash + quote (the injection vector)
            notify("Title", 'test\\"inject')
            script = mock_run.call_args[0][0][2]  # osascript -e <script>
            # After correct escaping: \ -> \\, then " -> \"
            # So \" in input becomes \\\" in the script
            # AppleScript reads \\\": \\ = literal \, \" = literal " (still in string)
            assert 'test\\\\\\"inject' in script

    def test_lone_backslash_escaped_on_macos(self) -> None:
        with (
            patch("zx59.notify.platform.system", return_value="Darwin"),
            patch("zx59.notify.subprocess.run") as mock_run,
        ):
            notify("Title", "back\\slash")
            script = mock_run.call_args[0][0][2]
            assert "back\\\\slash" in script

    def test_failure_message_includes_exception(self, capsys: object) -> None:
        """Error details should be surfaced, not swallowed."""
        from io import StringIO

        captured_err = StringIO()
        with (
            patch("zx59.notify.subprocess.run", side_effect=OSError("specific error")),
            patch("sys.stderr", captured_err),
        ):
            notify("Test", "Message")
        assert "specific error" in captured_err.getvalue()
