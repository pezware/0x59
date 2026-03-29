"""Desktop notifications. Failure is non-fatal."""

from __future__ import annotations

import platform
import subprocess
import sys


def notify(title: str, message: str) -> None:
    """Send a desktop notification. Never raises."""
    try:
        safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')

        if platform.system() == "Darwin":
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
            subprocess.run(
                ["notify-send", title, message],
                capture_output=True,
                timeout=5,
            )
    except Exception as e:
        print(f"[0x59] notification failed ({e}): {title}: {message}", file=sys.stderr)
