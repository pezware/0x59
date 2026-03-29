"""Artifact export to files."""

from __future__ import annotations

from pathlib import Path

from zx59.db import Artifact


def validate_export_name(name: str) -> Path:
    """Validate an artifact name for safe use as an export path.

    Rejects absolute paths and parent-directory traversals.
    """
    p = Path(name)
    if p.is_absolute():
        raise ValueError(f"Refusing absolute export path: {name}")
    if ".." in p.parts:
        raise ValueError(f"Refusing path with '..' components: {name}")
    return p


def export_artifact(artifact: Artifact, path: Path) -> Path:
    """Write artifact content to a file. Returns the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.content)
    return path
