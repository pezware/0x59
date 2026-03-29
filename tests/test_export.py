"""Tests for artifact export."""

from __future__ import annotations

from pathlib import Path

import pytest

from zx59.db import Artifact
from zx59.export import export_artifact, validate_export_name


def _artifact(name: str = "doc.md", content: str = "# Hello") -> Artifact:
    return Artifact(
        id=1,
        channel_id="test",
        message_id=None,
        name=name,
        content=content,
        content_type="text/markdown",
        created_at="2025-01-01",
    )


class TestExportArtifact:
    def test_creates_file_with_content(self, tmp_path: Path) -> None:
        art = _artifact(content="# Design\n\nUse JWT.")
        path = tmp_path / "output.md"
        result = export_artifact(art, path)

        assert result == path
        assert path.read_text() == "# Design\n\nUse JWT."

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        art = _artifact()
        path = tmp_path / "sub" / "dir" / "doc.md"
        export_artifact(art, path)

        assert path.exists()
        assert path.read_text() == "# Hello"


class TestValidateExportName:
    def test_rejects_absolute_path(self) -> None:
        with pytest.raises(ValueError, match="absolute"):
            validate_export_name("/etc/passwd")

    def test_rejects_dotdot_traversal(self) -> None:
        with pytest.raises(ValueError, match="\\.\\."):
            validate_export_name("../../.ssh/keys")

    def test_rejects_embedded_dotdot(self) -> None:
        with pytest.raises(ValueError, match="\\.\\."):
            validate_export_name("foo/../../bar")

    def test_allows_simple_name(self) -> None:
        assert validate_export_name("design.md") == Path("design.md")

    def test_allows_subdirectory(self) -> None:
        assert validate_export_name("docs/out.md") == Path("docs/out.md")
