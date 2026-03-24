"""Artifact export to files."""

from __future__ import annotations

from pathlib import Path

from zx59.db import Artifact


def export_artifact(artifact: Artifact, path: Path) -> Path:
    """Write artifact content to a file. Returns the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.content)
    return path
