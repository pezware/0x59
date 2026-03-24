"""Tests for the JSON schema definitions."""

from __future__ import annotations

import json

from zx59.schema import RESPONSE_SCHEMA, schema_json


class TestResponseSchema:
    def test_required_fields(self) -> None:
        assert "message" in RESPONSE_SCHEMA["required"]
        assert "decision_reached" in RESPONSE_SCHEMA["required"]

    def test_message_is_string(self) -> None:
        props = RESPONSE_SCHEMA["properties"]
        assert props["message"]["type"] == "string"

    def test_decision_reached_is_boolean(self) -> None:
        props = RESPONSE_SCHEMA["properties"]
        assert props["decision_reached"]["type"] == "boolean"

    def test_artifacts_items_require_name_and_content(self) -> None:
        items = RESPONSE_SCHEMA["properties"]["artifacts"]["items"]
        assert "name" in items["required"]
        assert "content" in items["required"]

    def test_schema_json_round_trips(self) -> None:
        serialized = schema_json()
        parsed = json.loads(serialized)
        assert parsed == RESPONSE_SCHEMA
