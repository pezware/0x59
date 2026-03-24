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
