"""Desktop notifications. Failure is non-fatal."""

from __future__ import annotations

import html
import platform
import subprocess
import sys


def notify(title: str, message: str) -> None:
    """Send a desktop notification. Never raises."""
    try:
        if platform.system() == "Darwin":
            safe_message = (
                message.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", " ")
                .replace("\r", "")
            )
            safe_title = (
                title.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")
            )
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{safe_message}" '
                    f'with title "{safe_title}" sound name "Glass"',
                ],
                capture_output=True,
                timeout=5,
            )
        elif platform.system() == "Linux":
            # notify-send interprets Pango markup; escape to prevent rendering
            subprocess.run(
                ["notify-send", html.escape(title), html.escape(message)],
                capture_output=True,
                timeout=5,
            )
    except Exception as e:
        print(f"[0x59] notification failed ({e}): {title}: {message}", file=sys.stderr)
