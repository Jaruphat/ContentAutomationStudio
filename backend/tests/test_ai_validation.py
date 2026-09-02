"""
Tests for turning a model's text into a validated object.

This is the gate that decides whether a response is a success. Everything
downstream - including every database write - assumes it held.
"""

import pytest

from app.services.ai.task_schemas import TASK_SCHEMAS
from app.services.ai.validation import (
    SchemaViolation,
    parse_json_object,
    strip_code_fence,
    validate_against_schema,
)

SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["title", "count"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Fences and parsing
# ---------------------------------------------------------------------------

def test_plain_json_passes_through():
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'


@pytest.mark.parametrize("fenced", [
    '```json\n{"a": 1}\n```',
    '```\n{"a": 1}\n```',
    '  ```json\n{"a": 1}\n```  ',
])
def test_markdown_fences_are_stripped(fenced):
    """Models add fences despite being told not to; that is formatting."""
    assert parse_json_object(fenced) == {"a": 1}


def test_an_empty_response_is_invalid_json():
    with pytest.raises(SchemaViolation) as excinfo:
        parse_json_object("   ")
    assert excinfo.value.category == "invalid_json"


def test_malformed_json_reports_the_position():
    with pytest.raises(SchemaViolation) as excinfo:
        parse_json_object('{"a": 1,}')
    assert excinfo.value.category == "invalid_json"
    assert "line" in str(excinfo.value)


def test_a_json_array_is_not_an_object():
    """The top level must be an object; a list would not have the task's keys."""
    with pytest.raises(SchemaViolation) as excinfo:
        parse_json_object("[1, 2, 3]")
    assert excinfo.value.category == "invalid_json"
    assert "list" in str(excinfo.value)


def test_prose_around_json_is_not_guessed_at():
    """Stripping a fence is a nicety; extracting JSON from prose is not.

    Silently digging an object out of a refusal would turn 'I won't do that'
    into a storyboard.
    """
    with pytest.raises(SchemaViolation):
        parse_json_object('I cannot help with that. {"a": 1}')


def test_the_excerpt_is_bounded():
    """A runaway generation must not be quoted back in full into a log."""
    with pytest.raises(SchemaViolation) as excinfo:
        parse_json_object("x" * 5000)
    assert len(excinfo.value.excerpt) <= 400


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_a_conforming_object_validates():
    assert validate_against_schema(
        '{"title": "hello", "count": 3}', SIMPLE_SCHEMA
    ) == {"title": "hello", "count": 3}


def test_a_missing_property_is_a_schema_violation():
    with pytest.raises(SchemaViolation) as excinfo:
        validate_against_schema('{"title": "hello"}', SIMPLE_SCHEMA)
    assert excinfo.value.category == "schema_violation"
    assert "count" in str(excinfo.value)


def test_a_wrong_type_is_a_schema_violation():
    with pytest.raises(SchemaViolation) as excinfo:
        validate_against_schema(
            '{"title": "hello", "count": "three"}', SIMPLE_SCHEMA
        )
    assert excinfo.value.category == "schema_violation"


def test_an_extra_property_is_rejected():
    """Closed objects keep a model from inventing fields such as an id."""
    with pytest.raises(SchemaViolation):
        validate_against_schema(
            '{"title": "a", "count": 1, "id": "x"}', SIMPLE_SCHEMA
        )


def test_the_error_names_the_location_and_counts_the_rest():
    with pytest.raises(SchemaViolation) as excinfo:
        validate_against_schema("{}", SIMPLE_SCHEMA)
    message = str(excinfo.value)
    assert "top level" in message
    assert "other schema problem" in message


# ---------------------------------------------------------------------------
# Repair hints
# ---------------------------------------------------------------------------

def test_the_invalid_json_hint_asks_for_bare_json():
    violation = SchemaViolation("invalid_json", "trailing comma")
    hint = violation.repair_hint()
    assert "not valid JSON" in hint
    assert "trailing comma" in hint


def test_the_schema_hint_names_the_fault_to_correct():
    violation = SchemaViolation("schema_violation", "at 'scenes': too short")
    hint = violation.repair_hint()
    assert "did not satisfy the required schema" in hint
    assert "at 'scenes': too short" in hint


# ---------------------------------------------------------------------------
# The real task schemas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(TASK_SCHEMAS))
def test_every_task_schema_is_strict_mode_clean(name):
    """OpenAI strict mode requires closed objects with everything required.

    Checked here so a schema edit cannot pass local validation while being
    rejected by the vendor at request time.
    """
    def walk(node, path):
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            properties = node.get("properties", {})
            assert node.get("additionalProperties") is False, (
                f"{name}{path}: additionalProperties must be false"
            )
            assert set(node.get("required", [])) == set(properties), (
                f"{name}{path}: every property must be listed in required"
            )
            for key, value in properties.items():
                walk(value, f"{path}/{key}")
        if node.get("type") == "array":
            walk(node.get("items", {}), f"{path}[]")

    walk(TASK_SCHEMAS[name], "")
