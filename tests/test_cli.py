"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import FakeClaude, make_response
from zx59.cli import main
from zx59.db import DB


class TestCLIParsing:
    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_no_command_exits_zero(self) -> None:
        result = main([])
        assert result == 0

    def test_chat_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["chat", "--help"])
        assert exc_info.value.code == 0

    def test_log_requires_channel_id(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["log"])
        assert exc_info.value.code != 0


class TestCLIReadCommands:
    """Commands that only read from the DB (no Claude calls)."""

    def test_ls_empty_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        result = main(["--db", str(db_path), "ls"])
        assert result == 0

    def test_ls_with_channels(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = DB(db_path)
        db.create_channel(topic="First topic", model="sonnet")
        db.create_channel(topic="Second topic", model="haiku")
        db.close()

        result = main(["--db", str(db_path), "ls"])
        assert result == 0

    def test_ls_status_filter(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        result = main(["--db", str(db_path), "ls", "--open"])
        assert result == 0

    def test_log_nonexistent_channel(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        result = main(["--db", str(db_path), "log", "nonexistent"])
        assert result == 1

    def test_log_existing_channel(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = DB(db_path)
        cid = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(cid, "a", "participant")
        db.append_message(cid, "a", "Hello world")
        db.close()

        result = main(["--db", str(db_path), "log", cid])
        assert result == 0

    def test_decision_nonexistent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        result = main(["--db", str(db_path), "decision", "nope"])
        assert result == 1

    def test_decision_existing(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = DB(db_path)
        cid = db.create_channel(topic="Test", model="sonnet")
        db.decide_channel(cid, "Use JWT")
        db.close()

        result = main(["--db", str(db_path), "decision", cid])
        assert result == 0

    def test_artifacts_empty(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = DB(db_path)
        cid = db.create_channel(topic="Test", model="sonnet")
        db.close()

        result = main(["--db", str(db_path), "artifacts", cid])
        assert result == 0


class TestCLIChatCommand:
    """Chat command with FakeClaude."""

    def test_chat_runs_conversation(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        fake = FakeClaude(
            [
                make_response("I propose X", decision=True, summary="Do X"),
                make_response("Agreed", decision=True, summary="Do X"),
            ]
        )
        with patch("zx59.cli._create_runner", return_value=fake):
            result = main(["--db", str(db_path), "chat", "Test topic"])
        assert result == 0

        db = DB(db_path)
        channels = db.list_channels()
        assert len(channels) == 1
        assert channels[0].topic == "Test topic"
        assert channels[0].status == "decided"
        db.close()

    def test_chat_with_model_override(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        fake = FakeClaude(
            [
                make_response("Quick", decision=True, summary="Done"),
                make_response("Yep", decision=True, summary="Done"),
            ]
        )
        with patch("zx59.cli._create_runner", return_value=fake):
            result = main(["--db", str(db_path), "chat", "Fast topic", "--model", "haiku"])
        assert result == 0

    def test_discuss_with_agents(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        fake = FakeClaude(
            [
                make_response("Design it", decision=True, summary="Designed"),
                make_response("Approved", decision=True, summary="Designed"),
            ]
        )
        with patch("zx59.cli._create_runner", return_value=fake):
            result = main(
                [
                    "--db",
                    str(db_path),
                    "discuss",
                    "Auth design",
                    "--agent",
                    "architect",
                    "You are an architect.",
                    "--agent",
                    "reviewer",
                    "You review code.",
                    "--agenda",
                    "1. Tokens\n2. Sessions",
                ]
            )
        assert result == 0

        db = DB(db_path)
        participants = db.get_participants(db.list_channels()[0].id)
        agent_ids = [p.agent_id for p in participants]
        assert "architect" in agent_ids
        assert "reviewer" in agent_ids
        db.close()
