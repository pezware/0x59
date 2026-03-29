"""Tests for the coordinator turn engine."""

from __future__ import annotations

import pytest

from tests.conftest import FakeClaude, make_response, setup_channel
from zx59.coordinator import Coordinator, TurnInfo
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

    def test_three_agent_decision_requires_different_agents(self, db: DB) -> None:
        """Same agent proposing twice in a row should not trigger a decision."""
        channel_id = db.create_channel(topic="Test", model="sonnet", max_turns=6)
        db.add_participant(channel_id, "a", "participant", system_prompt="Agent A")
        db.add_participant(channel_id, "b", "participant", system_prompt="Agent B")
        db.add_participant(channel_id, "c", "participant", system_prompt="Agent C")

        fake = FakeClaude(
            [
                # Turn 1 (a): proposes decision
                make_response("Let's agree", decision=True, summary="Plan X"),
                # Turn 2 (b): disagrees
                make_response("No way", decision=False),
                # Turn 3 (c): proposes decision
                make_response("I agree with A", decision=True, summary="Plan X"),
                # Turn 4 (a): agrees — different agent from c, so decision fires
                make_response("Confirmed", decision=True, summary="Plan X"),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)

        assert result.status == "decided"
        assert result.total_turns == 4

    def test_same_agent_cannot_self_confirm_decision(self, db: DB) -> None:
        """In a 3-agent setup, an agent cannot confirm its own proposal."""
        channel_id = db.create_channel(topic="Test", model="sonnet", max_turns=6)
        db.add_participant(channel_id, "a", "participant", system_prompt="Agent A")
        db.add_participant(channel_id, "b", "participant", system_prompt="Agent B")
        db.add_participant(channel_id, "c", "participant", system_prompt="Agent C")

        fake = FakeClaude(
            [
                # Turn 1 (a): proposes decision
                make_response("Let's do X", decision=True, summary="X"),
                # Turn 2 (b): disagrees
                make_response("Nope", decision=False),
                # Turn 3 (c): disagrees
                make_response("Nope", decision=False),
                # Turn 4 (a): proposes again — same agent, should NOT self-confirm
                make_response("Let's do X again", decision=True, summary="X"),
                # Turn 5 (b): agrees — different agent, decision fires
                make_response("Ok fine", decision=True, summary="X"),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)

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


class TestCoordinatorOnTurn:
    def test_on_turn_called_for_each_turn(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=3)
        fake = FakeClaude(
            [
                make_response("First"),
                make_response("Second"),
                make_response("Third"),
            ]
        )
        turns: list[TurnInfo] = []
        coord = Coordinator(db, fake)
        coord.run(channel_id, on_turn=turns.append)

        assert len(turns) == 3
        assert turns[0].turn == 1
        assert turns[0].max_turns == 3
        assert turns[0].agent_id == "proposer"
        assert turns[0].message == "First"
        assert turns[1].agent_id == "challenger"
        assert turns[2].agent_id == "proposer"

    def test_on_turn_reflects_decision_state(self, db: DB) -> None:
        channel_id = setup_channel(db)
        fake = FakeClaude(
            [
                make_response("Propose", decision=True, summary="X"),
                make_response("Agree", decision=True, summary="X"),
            ]
        )
        turns: list[TurnInfo] = []
        coord = Coordinator(db, fake)
        coord.run(channel_id, on_turn=turns.append)

        assert turns[0].decision_reached is True
        assert turns[1].decision_reached is True

    def test_no_on_turn_callback_is_fine(self, db: DB) -> None:
        channel_id = setup_channel(db, max_turns=2)
        fake = FakeClaude(
            [
                make_response("A"),
                make_response("B"),
            ]
        )
        coord = Coordinator(db, fake)
        result = coord.run(channel_id)  # no on_turn — should not error
        assert result.total_turns == 2


class TestCoordinatorSessionName:
    def test_session_name_passed_to_runner(self, db: DB) -> None:
        """Runner should receive a session name containing agent_id and topic."""
        channel_id = setup_channel(db, max_turns=2)

        class CapturingRunner:
            def __init__(self) -> None:
                self.session_names: list[str | None] = []

            def run(
                self, prompt: str, model: str, json_schema: str, *, session_name: str | None = None
            ) -> str:
                self.session_names.append(session_name)
                return make_response("hi")

        runner = CapturingRunner()
        coord = Coordinator(db, runner)
        coord.run(channel_id)

        assert len(runner.session_names) == 2
        assert "proposer" in (runner.session_names[0] or "")
        assert "challenger" in (runner.session_names[1] or "")
        assert "Test topic" in (runner.session_names[0] or "")


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
