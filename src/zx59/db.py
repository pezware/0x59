"""SQLite database layer. All SQL lives here."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Channel:
    id: str
    topic: str
    agenda: str | None
    status: str
    model: str
    max_turns: int
    created_at: str
    decided_at: str | None
    decision: str | None


@dataclass(frozen=True)
class Participant:
    channel_id: str
    agent_id: str
    role: str
    system_prompt: str | None
    model: str | None


@dataclass(frozen=True)
class Message:
    id: int
    channel_id: str
    sender: str
    content: str
    msg_type: str
    token_estimate: int | None
    created_at: str


@dataclass(frozen=True)
class Artifact:
    id: int
    channel_id: str
    message_id: int | None
    name: str
    content: str
    content_type: str
    created_at: str


_SCHEMA_V0 = """\
CREATE TABLE IF NOT EXISTS channels (
    id          TEXT PRIMARY KEY,
    topic       TEXT NOT NULL,
    agenda      TEXT,
    status      TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'decided', 'closed')),
    model       TEXT NOT NULL DEFAULT 'sonnet',
    max_turns   INTEGER NOT NULL DEFAULT 20,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at  TEXT,
    decision    TEXT
);

CREATE TABLE IF NOT EXISTS participants (
    channel_id    TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    agent_id      TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'participant'
                  CHECK (role IN ('participant', 'observer')),
    system_prompt TEXT,
    model         TEXT,
    PRIMARY KEY (channel_id, agent_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id     TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    sender         TEXT NOT NULL,
    content        TEXT NOT NULL,
    msg_type       TEXT NOT NULL DEFAULT 'chat'
                   CHECK (msg_type IN ('chat', 'proposal', 'decision', 'summary', 'artifact')),
    token_estimate INTEGER,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    message_id   INTEGER REFERENCES messages(id),
    name         TEXT NOT NULL,
    content      TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/markdown',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_MIGRATIONS: dict[int, str] = {
    0: _SCHEMA_V0,
}


def _generate_channel_id() -> str:
    """Generate a short, unique channel ID."""
    return uuid.uuid4().hex[:12]


class DB:
    """SQLite database for 0x59 channels, messages, and artifacts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        """Execute a SQL statement. For internal and test use."""
        return self._conn.execute(sql, params)

    def migrate(self) -> None:
        """Run pending schema migrations.

        user_version tracks the next migration to apply (0 = fresh DB).
        Only migrations with version >= user_version are executed.
        After running, user_version is set to max(applied) + 1.
        """
        (current_version,) = self._conn.execute("PRAGMA user_version").fetchone()
        applied = False
        for version in sorted(_MIGRATIONS):
            if version < current_version:
                continue
            self._conn.executescript(_MIGRATIONS[version])
            applied = True
        if applied:
            target = max(_MIGRATIONS) + 1
            self._conn.execute(f"PRAGMA user_version={target}")
            self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ── Channels ──────────────────────────────────────────────────────

    def create_channel(
        self,
        topic: str,
        model: str,
        agenda: str | None = None,
        max_turns: int = 20,
    ) -> str:
        """Create a new channel. Returns the channel ID."""
        channel_id = _generate_channel_id()
        self._conn.execute(
            "INSERT INTO channels (id, topic, agenda, model, max_turns) VALUES (?, ?, ?, ?, ?)",
            (channel_id, topic, agenda, model, max_turns),
        )
        self._conn.commit()
        return channel_id

    def get_channel(self, channel_id: str) -> Channel | None:
        """Get a channel by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT id, topic, agenda, status, model, max_turns, "
            "created_at, decided_at, decision FROM channels WHERE id = ?",
            (channel_id,),
        ).fetchone()
        if row is None:
            return None
        return Channel(*row)

    def decide_channel(self, channel_id: str, decision: str) -> None:
        """Mark a channel as decided with the given decision summary."""
        self._conn.execute(
            "UPDATE channels SET status = 'decided', decision = ?, "
            "decided_at = datetime('now') WHERE id = ?",
            (decision, channel_id),
        )
        self._conn.commit()

    def close_channel(self, channel_id: str) -> None:
        """Mark a channel as closed."""
        self._conn.execute(
            "UPDATE channels SET status = 'closed' WHERE id = ?",
            (channel_id,),
        )
        self._conn.commit()

    def list_channels(self, status: str | None = None) -> list[Channel]:
        """List channels, optionally filtered by status."""
        if status is not None:
            rows = self._conn.execute(
                "SELECT id, topic, agenda, status, model, max_turns, "
                "created_at, decided_at, decision FROM channels "
                "WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, topic, agenda, status, model, max_turns, "
                "created_at, decided_at, decision FROM channels "
                "ORDER BY created_at DESC",
            ).fetchall()
        return [Channel(*row) for row in rows]

    # ── Participants ──────────────────────────────────────────────────

    def add_participant(
        self,
        channel_id: str,
        agent_id: str,
        role: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> None:
        """Add a participant to a channel."""
        self._conn.execute(
            "INSERT INTO participants (channel_id, agent_id, role, system_prompt, model) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, agent_id, role, system_prompt, model),
        )
        self._conn.commit()

    def get_participants(self, channel_id: str) -> list[Participant]:
        """Get all participants for a channel, in insertion order."""
        rows = self._conn.execute(
            "SELECT channel_id, agent_id, role, system_prompt, model "
            "FROM participants WHERE channel_id = ? ORDER BY rowid",
            (channel_id,),
        ).fetchall()
        return [Participant(*row) for row in rows]

    # ── Messages ──────────────────────────────────────────────────────

    def append_message(
        self,
        channel_id: str,
        sender: str,
        content: str,
        msg_type: str = "chat",
        token_estimate: int | None = None,
    ) -> int:
        """Append a message to a channel. Returns the message ID."""
        cursor = self._conn.execute(
            "INSERT INTO messages (channel_id, sender, content, msg_type, token_estimate) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, sender, content, msg_type, token_estimate),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def get_messages(self, channel_id: str, limit: int | None = None) -> list[Message]:
        """Get messages for a channel, ordered by ID.

        If limit is provided, returns the most recent N messages.
        """
        if limit is not None:
            rows = self._conn.execute(
                "SELECT id, channel_id, sender, content, msg_type, "
                "token_estimate, created_at FROM messages "
                "WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
                (channel_id, limit),
            ).fetchall()
            rows.reverse()
        else:
            rows = self._conn.execute(
                "SELECT id, channel_id, sender, content, msg_type, "
                "token_estimate, created_at FROM messages "
                "WHERE channel_id = ? ORDER BY id",
                (channel_id,),
            ).fetchall()
        return [Message(*row) for row in rows]

    # ── Artifacts ─────────────────────────────────────────────────────

    def save_artifact(
        self,
        channel_id: str,
        name: str,
        content: str,
        message_id: int | None = None,
        content_type: str = "text/markdown",
    ) -> int:
        """Save an artifact. Returns the artifact ID."""
        cursor = self._conn.execute(
            "INSERT INTO artifacts (channel_id, message_id, name, content, content_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (channel_id, message_id, name, content, content_type),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def get_artifacts(self, channel_id: str) -> list[Artifact]:
        """Get all artifacts for a channel."""
        rows = self._conn.execute(
            "SELECT id, channel_id, message_id, name, content, content_type, created_at "
            "FROM artifacts WHERE channel_id = ?",
            (channel_id,),
        ).fetchall()
        return [Artifact(*row) for row in rows]
