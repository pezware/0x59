"""JSON schema definitions for structured agent responses."""

from __future__ import annotations

import json

RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The agent's conversational response",
        },
        "decision_reached": {
            "type": "boolean",
            "description": "True when the agent believes consensus has been reached",
        },
        "decision_summary": {
            "type": "string",
            "description": "Summary of the decision (when decision_reached is true)",
        },
        "artifacts": {
            "type": "array",
            "description": "Documents or code produced during this turn",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "content_type": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        },
    },
    "required": ["message", "decision_reached"],
}


def schema_json() -> str:
    """Return the response schema as a JSON string."""
    return json.dumps(RESPONSE_SCHEMA)
