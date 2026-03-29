"""Tests for the database layer."""

from __future__ import annotations

import sqlite3

import pytest

from zx59.db import DB


class TestDBSetup:
    """Database initialization and configuration."""

    def test_creates_database_file(self, db: DB) -> None:
        assert db.path.exists()

    def test_wal_mode_enabled(self, db: DB) -> None:
        row = db.execute("PRAGMA journal_mode").fetchone()
        assert row is not None
        assert row[0] == "wal"

    def test_foreign_keys_enabled(self, db: DB) -> None:
        row = db.execute("PRAGMA foreign_keys").fetchone()
        assert row is not None
        assert row[0] == 1

    def test_migration_is_idempotent(self, db: DB) -> None:
        """Running migrations again should not raise or duplicate tables."""
        db.migrate()
        # If we get here without error, migrations are idempotent
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "channels" in table_names
        assert "participants" in table_names
        assert "messages" in table_names
        assert "artifacts" in table_names

    def test_user_version_tracks_applied_migrations(self, db: DB) -> None:
        """user_version should equal max(migration_index) + 1 after init."""
        (version,) = db.execute("PRAGMA user_version").fetchone()
        assert version == 1  # migration 0 applied → user_version = 1

    def test_migrate_skips_when_up_to_date(self, db: DB) -> None:
        """Re-running migrate on an up-to-date DB should not change user_version."""
        (before,) = db.execute("PRAGMA user_version").fetchone()
        db.migrate()
        (after,) = db.execute("PRAGMA user_version").fetchone()
        assert before == after


class TestChannels:
    """Channel CRUD operations."""

    def test_create_channel(self, db: DB) -> None:
        channel_id = db.create_channel(
            topic="Test discussion",
            model="sonnet",
        )
        assert isinstance(channel_id, str)
        assert len(channel_id) > 0

    def test_create_channel_with_agenda(self, db: DB) -> None:
        channel_id = db.create_channel(
            topic="Design review",
            agenda="1. Architecture\n2. Security",
            model="opus",
            max_turns=10,
        )
        channel = db.get_channel(channel_id)
        assert channel is not None
        assert channel.topic == "Design review"
        assert channel.agenda == "1. Architecture\n2. Security"
        assert channel.model == "opus"
        assert channel.max_turns == 10
        assert channel.status == "open"

    def test_get_nonexistent_channel(self, db: DB) -> None:
        assert db.get_channel("nonexistent") is None

    def test_update_channel_decision(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Quick chat", model="haiku")
        db.decide_channel(channel_id, decision="Use JWT tokens")
        channel = db.get_channel(channel_id)
        assert channel is not None
        assert channel.status == "decided"
        assert channel.decision == "Use JWT tokens"
        assert channel.decided_at is not None

    def test_close_channel(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Done", model="sonnet")
        db.close_channel(channel_id)
        channel = db.get_channel(channel_id)
        assert channel is not None
        assert channel.status == "closed"

    def test_list_channels(self, db: DB) -> None:
        db.create_channel(topic="Open one", model="sonnet")
        cid2 = db.create_channel(topic="Decided one", model="sonnet")
        db.decide_channel(cid2, decision="Done")
        db.create_channel(topic="Open two", model="haiku")

        all_channels = db.list_channels()
        assert len(all_channels) == 3

        open_channels = db.list_channels(status="open")
        assert len(open_channels) == 2

        decided_channels = db.list_channels(status="decided")
        assert len(decided_channels) == 1


class TestParticipants:
    """Participant management."""

    def test_add_participant(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(
            channel_id=channel_id,
            agent_id="architect",
            role="participant",
            system_prompt="You are an architect.",
        )
        participants = db.get_participants(channel_id)
        assert len(participants) == 1
        assert participants[0].agent_id == "architect"
        assert participants[0].role == "participant"
        assert participants[0].system_prompt == "You are an architect."

    def test_add_multiple_participants(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "proposer", "participant", "Propose things.")
        db.add_participant(channel_id, "reviewer", "participant", "Review things.")
        participants = db.get_participants(channel_id)
        assert len(participants) == 2

    def test_add_observer(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "watcher", "observer")
        participants = db.get_participants(channel_id)
        assert participants[0].role == "observer"

    def test_duplicate_participant_raises(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "agent-a", "participant")
        with pytest.raises(sqlite3.IntegrityError):
            db.add_participant(channel_id, "agent-a", "participant")

    def test_participant_with_model_override(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "cheap-agent", "participant", model="haiku")
        participants = db.get_participants(channel_id)
        assert participants[0].model == "haiku"

    def test_fk_violation_on_bad_channel(self, db: DB) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.add_participant("nonexistent", "agent", "participant")


class TestMessages:
    """Message storage and retrieval."""

    def test_append_and_get_messages(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "agent-a", "participant")

        msg_id = db.append_message(
            channel_id=channel_id,
            sender="agent-a",
            content="Hello, world!",
        )
        assert isinstance(msg_id, int)

        messages = db.get_messages(channel_id)
        assert len(messages) == 1
        assert messages[0].sender == "agent-a"
        assert messages[0].content == "Hello, world!"
        assert messages[0].msg_type == "chat"

    def test_messages_ordered_by_id(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "a", "participant")
        db.add_participant(channel_id, "b", "participant")

        db.append_message(channel_id, "a", "First")
        db.append_message(channel_id, "b", "Second")
        db.append_message(channel_id, "a", "Third")

        messages = db.get_messages(channel_id)
        assert [m.content for m in messages] == ["First", "Second", "Third"]

    def test_message_types(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "a", "participant")

        db.append_message(channel_id, "a", "Let's discuss", msg_type="chat")
        db.append_message(channel_id, "a", "I propose X", msg_type="proposal")
        db.append_message(channel_id, "a", "Decided: X", msg_type="decision")
        db.append_message(channel_id, "system", "Summary so far", msg_type="summary")

        messages = db.get_messages(channel_id)
        assert [m.msg_type for m in messages] == ["chat", "proposal", "decision", "summary"]

    def test_get_messages_with_limit(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "a", "participant")

        for i in range(10):
            db.append_message(channel_id, "a", f"Message {i}")

        messages = db.get_messages(channel_id, limit=3)
        assert len(messages) == 3
        # Should return the LAST 3 messages (most recent)
        assert messages[0].content == "Message 7"
        assert messages[2].content == "Message 9"

    def test_get_messages_empty_channel(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Empty", model="sonnet")
        messages = db.get_messages(channel_id)
        assert messages == []

    def test_message_with_token_estimate(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "a", "participant")

        db.append_message(channel_id, "a", "Hello", token_estimate=5)
        messages = db.get_messages(channel_id)
        assert messages[0].token_estimate == 5

    def test_fk_violation_on_bad_channel(self, db: DB) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.append_message("nonexistent", "a", "Hello")


class TestArtifacts:
    """Artifact storage."""

    def test_save_and_get_artifacts(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.add_participant(channel_id, "a", "participant")
        msg_id = db.append_message(channel_id, "a", "Here's the doc")

        artifact_id = db.save_artifact(
            channel_id=channel_id,
            name="design.md",
            content="# Design\n\nUse JWT.",
            message_id=msg_id,
        )
        assert isinstance(artifact_id, int)

        artifacts = db.get_artifacts(channel_id)
        assert len(artifacts) == 1
        assert artifacts[0].name == "design.md"
        assert artifacts[0].content == "# Design\n\nUse JWT."
        assert artifacts[0].content_type == "text/markdown"
        assert artifacts[0].message_id == msg_id

    def test_save_artifact_without_message(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        artifact_id = db.save_artifact(
            channel_id=channel_id,
            name="standalone.txt",
            content="Just a note.",
            content_type="text/plain",
        )
        artifacts = db.get_artifacts(channel_id)
        assert len(artifacts) == 1
        assert artifacts[0].message_id is None
        assert artifacts[0].content_type == "text/plain"
        assert isinstance(artifact_id, int)

    def test_multiple_artifacts(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet")
        db.save_artifact(channel_id, "doc1.md", "First")
        db.save_artifact(channel_id, "doc2.md", "Second")

        artifacts = db.get_artifacts(channel_id)
        assert len(artifacts) == 2

    def test_fk_violation_on_bad_channel(self, db: DB) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.save_artifact("nonexistent", "fail.md", "Nope")
