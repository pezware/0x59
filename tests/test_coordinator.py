"""Tests for the coordinator turn engine."""

from __future__ import annotations

import pytest

from tests.conftest import FakeClaude, make_response, setup_channel
from zx59.coordinator import Coordinator
from zx59.db import DB
from zx59.runner import ClaudeResponseError


class TestCoordinatorDecision:
    def test_basic_two_turn_decision(self, db: DB) -> None:
        channel_id = setup_channel(db)
        fake = FakeClaude(
            [
                make_response("I propose JWT", decision=True, summary="Use JWT"),
                make_response("Agreed", decision=True, summary="Use JWT"),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)

        assert result.status == "decided"
        assert result.total_turns == 2
        assert result.decision == "Use JWT"

    def test_decision_requires_both_agents(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=4)
        fake = FakeClaude(
            [
                make_response("I propose JWT", decision=True, summary="Use JWT"),
                make_response("Not convinced yet", decision=False),
                make_response("How about sessions?", decision=False),
                make_response("Ok fine", decision=False),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)

        assert result.status == "max_turns"
        assert result.total_turns == 4

    def test_decision_resets_when_second_agent_disagrees(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=6)
        fake = FakeClaude(
            [
                make_response("JWT?", decision=True, summary="JWT"),
                make_response("No", decision=False),
                make_response("Sessions?", decision=False),
                make_response("Maybe JWT after all", decision=True, summary="JWT v2"),
                make_response("Yes JWT", decision=True, summary="JWT final"),
                make_response("Confirmed", decision=True, summary="JWT final"),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)

        # Turns 4+5: proposer=true, challenger=true → decided
        assert result.status == "decided"
        assert result.total_turns == 5


class TestCoordinatorTurns:
    def test_max_turns_stops_conversation(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=3)
        fake = FakeClaude(
            [
                make_response("Turn 1"),
                make_response("Turn 2"),
                make_response("Turn 3"),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)

        assert result.status == "max_turns"
        assert result.total_turns == 3

    def test_round_robin_agent_selection(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=4)
        fake = FakeClaude(
            [
                make_response("A1"),
                make_response("B1"),
                make_response("A2"),
                make_response("B2"),
            ]
        )
        coord = Coordinator(db, fake)
        coord.run(channel_id)

        messages = db.get_messages(channel_id)
        senders = [m.sender for m in messages]
        assert senders == ["proposer", "challenger", "proposer", "challenger"]

    def test_agent_model_override_used(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Test", model="sonnet", max_turns=2)
        db.add_participant(channel_id, "cheap", "participant", model="haiku")
        db.add_participant(channel_id, "expensive", "participant", model="opus")

        fake = FakeClaude(
            [
                make_response("Hi", decision=True),
                make_response("Bye", decision=True, summary="Done"),
            ]
        )
        coord = Coordinator(db, fake)
        coord.run(channel_id)

        models_used = [call[1] for call in fake.calls]
        assert models_used == ["haiku", "opus"]


class TestCoordinatorPersistence:
    def test_messages_persisted_to_db(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=2)
        fake = FakeClaude(
            [
                make_response("Hello"),
                make_response("World"),
            ]
        )
        coord = Coordinator(db, fake)
        coord.run(channel_id)

        messages = db.get_messages(channel_id)
        assert len(messages) == 2
        assert messages[0].content == "Hello"
        assert messages[1].content == "World"

    def test_artifacts_saved(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=2)
        fake = FakeClaude(
            [
                make_response(
                    "Here's the doc",
                    artifacts=[{"name": "design.md", "content": "# Design"}],
                ),
                make_response("Looks good", decision=True, summary="Done"),
            ]
        )
        coord = Coordinator(db, fake)
        coord.run(channel_id)

        artifacts = db.get_artifacts(channel_id)
        assert len(artifacts) == 1
        assert artifacts[0].name == "design.md"
        assert artifacts[0].content == "# Design"

    def test_channel_marked_decided(self, db: DB) -> None:
        channel_id = setup_channel(db)
        fake = FakeClaude(
            [
                make_response("Yes", decision=True, summary="Agreed"),
                make_response("Yes", decision=True, summary="Agreed"),
            ]
        )
        coord = Coordinator(db, fake)
        coord.run(channel_id)

        channel = db.get_channel(channel_id)
        assert channel is not None
        assert channel.status == "decided"
        assert channel.decision == "Agreed"


class TestCoordinatorErrors:
    def test_malformed_json_raises(self, db: DB) -> None:
        channel_id = setup_channel(db)
        fake = FakeClaude(["not valid json at all"])
        coord = Coordinator(db, fake)
        with pytest.raises(ClaudeResponseError):
            coord.run(channel_id)

    def test_channel_not_found_raises(self, db: DB) -> None:
        fake = FakeClaude([])
        coord = Coordinator(db, fake)
        with pytest.raises(ValueError, match="not found"):
            coord.run("nonexistent")

    def test_insufficient_participants_raises(self, db: DB) -> None:
        channel_id = db.create_channel(topic="Solo", model="sonnet")
        db.add_participant(channel_id, "loner", "participant")
        fake = FakeClaude([])
        coord = Coordinator(db, fake)
        with pytest.raises(ValueError, match="at least 2"):
            coord.run(channel_id)
