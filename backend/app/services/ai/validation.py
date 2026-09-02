"""
Turning a model's text into a validated object.

A response is not a success because the HTTP call returned 200. It is a success
once it parses as JSON and satisfies the task's schema. This module is the only
place that decides that, so every provider - and every future one - gets the
same standard, including vendors whose "strict" structured output is trusted
but still re-checked here.

When validation fails the exception carries a repair hint: the specific
complaint, phrased for the model, that the retry loop appends to the next
attempt.
"""

import json
import re
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

#: Models sometimes wrap JSON in a markdown fence despite being told not to.
#: Stripping it is a formatting nicety, not a licence to accept prose: anything
#: that still fails to parse is reported, never guessed at.
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

#: How much of a bad response to quote back. Enough to locate the fault,
#: bounded so a runaway generation cannot fill the log or the error field.
_EXCERPT_LIMIT = 400


class SchemaViolation(ValueError):
    """A response could not be turned into the object the task requires."""

    def __init__(self, category: str, message: str, *, excerpt: str = ""):
        super().__init__(message)
        #: "invalid_json" (did not parse) or "schema_violation" (parsed, wrong
        #: shape). Both are retryable, for different reasons.
        self.category = category
        self.excerpt = excerpt

    def repair_hint(self) -> str:
        """The complaint, phrased as an instruction for the next attempt."""
        if self.category == "invalid_json":
            return (
                "Your previous response was not valid JSON: "
                f"{self}. Reply with a single JSON object and nothing else - "
                "no prose, no markdown fence, no trailing commas."
            )
        return (
            f"Your previous response did not satisfy the required schema: "
            f"{self}. Correct exactly that and reply with the full JSON object "
            f"again."
        )


def strip_code_fence(text: str) -> str:
    """Remove a surrounding markdown fence, if present."""
    match = _FENCE.match(text or "")
    return match.group(1) if match else (text or "")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a response into a JSON object, or raise :class:`SchemaViolation`."""
    candidate = strip_code_fence(text).strip()
    if not candidate:
        raise SchemaViolation("invalid_json", "the response was empty")

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise SchemaViolation(
            "invalid_json",
            f"{exc.msg} at line {exc.lineno} column {exc.colno}",
            excerpt=candidate[:_EXCERPT_LIMIT],
        ) from exc

    if not isinstance(data, dict):
        raise SchemaViolation(
            "invalid_json",
            f"expected a JSON object at the top level, got {type(data).__name__}",
            excerpt=candidate[:_EXCERPT_LIMIT],
        )
    return data


def _describe(error: ValidationError) -> str:
    """A one-line, model-actionable description of a validation error."""
    location = "/".join(str(part) for part in error.absolute_path)
    where = f"at '{location}'" if location else "at the top level"
    return f"{where}: {error.message}"


def validate_object(data: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Check an already-parsed object against ``schema``.

    Used both for a fresh provider response and for a draft a client sends
    back to be applied: a draft that arrived over the wire gets exactly the
    same check as one that just came from the model, so nothing reaches the
    database on the strength of having been seen before.
    """
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        detail = _describe(errors[0])
        if len(errors) > 1:
            detail += f" (and {len(errors) - 1} other schema problem(s))"
        raise SchemaViolation("schema_violation", detail)
    return data


def validate_against_schema(
    text: str, schema: dict[str, Any]
) -> dict[str, Any]:
    """
    Parse ``text`` and check it against ``schema``.

    Returns the parsed object. Raises :class:`SchemaViolation` describing the
    first failure in document order, so the retry feedback names one concrete
    fault rather than a wall of them.
    """
    return validate_object(parse_json_object(text), schema)
