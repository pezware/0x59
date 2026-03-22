"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from zx59.db import DB


@pytest.fixture
def db(tmp_path: Path) -> Iterator[DB]:
    """Create a fresh DB instance backed by a temporary file."""
    database = DB(tmp_path / "test.db")
    yield database
    database.close()
