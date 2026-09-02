"""
Tests for the shared provider contract: retry policy and provenance.

The retry loop is written once in the base class rather than per vendor, so it
is tested once here against a stub provider whose failures are scripted. That
keeps these assertions about *policy* rather than about any vendor's HTTP.
"""

import json

import pytest

from app.services.ai import base
from app.services.ai.base import (
    AIProvider,
    AIProviderError,
    StructuredRequest,
    TokenUsage,
)

SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}

VALID = json.dumps({"value": "ok"})

#: Captured before the no-backoff fixture patches the module, so the backoff
#: test can exercise the real curve rather than the stub.
_REAL_BACKOFF = base._backoff_delay


def make_request(**overrides) -> StructuredRequest:
    fields = {
        "task": "unit_test",
        "system_prompt": "system",
        "user_prompt": "user",
        "schema_name": "unit_test",
        "json_schema": SCHEMA,
        "prompt_version": "1.0",
        "schema_version": "1.0",
    }
    fields.update(overrides)
    return StructuredRequest(**fields)


class ScriptedProvider(AIProvider):
    """Returns or raises whatever the script says, one entry per attempt."""

    id = "scripted"
    label = "Scripted"
    api_key_env = ""
    default_model = "scripted-1"

    def __init__(self, script, **kwargs):
        super().__init__(**kwargs)
        self.script = list(script)
        self.seen: list[StructuredRequest] = []

    async def _complete_once(self, request):
        self.seen.append(request)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step, self.model, TokenUsage(1, 2, 3), "resp-1"


class KeyedProvider(ScriptedProvider):
    id = "keyed"
    api_key_env = "CAS_TEST_AI_KEY"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    """Remove the retry sleep so policy tests do not spend real seconds."""
    monkeypatch.setattr(base, "_backoff_delay", lambda index: 0.0)


# ---------------------------------------------------------------------------
# Success path and provenance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_valid_response_succeeds_on_the_first_attempt():
    provider = ScriptedProvider([VALID])
    result = await provider.complete_structured(make_request())

    assert result.data == {"value": "ok"}
    assert result.attempts == 1
    assert result.warnings == []


@pytest.mark.asyncio
async def test_provenance_carries_the_versions_from_the_request():
    """Versions travel on the request so an artifact names what produced it,
    even after the templates move on."""
    provider = ScriptedProvider([VALID])
    result = await provider.complete_structured(
        make_request(prompt_version="2.3", schema_version="4.5")
    )

    assert result.prompt_version == "2.3"
    assert result.schema_version == "4.5"
    assert result.provider_id == "scripted"
    assert result.usage.as_dict() == {
        "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3,
    }


@pytest.mark.asyncio
async def test_the_served_model_is_recorded_not_the_requested_alias():
    provider = ScriptedProvider([VALID], model="dated-build-2026-01-01")
    result = await provider.complete_structured(make_request())
    assert result.model == "dated-build-2026-01-01"


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_transient_failure_is_retried():
    provider = ScriptedProvider([
        AIProviderError("connection", "network blip"),
        VALID,
    ])
    result = await provider.complete_structured(make_request())

    assert result.attempts == 2
    assert len(result.warnings) == 1
    assert "connection" in result.warnings[0]


@pytest.mark.asyncio
async def test_malformed_json_is_retried_with_the_complaint_fed_back():
    """The difference between a transcription slip and a refusal.

    A model told exactly what was wrong usually fixes it; one that refused
    fails the same way every time and surfaces a real error.
    """
    provider = ScriptedProvider(["{not json", VALID])
    result = await provider.complete_structured(make_request())

    assert result.attempts == 2
    assert provider.seen[0].repair_hint == ""
    assert "not valid JSON" in provider.seen[1].repair_hint


@pytest.mark.asyncio
async def test_a_schema_violation_is_retried_with_the_specific_fault():
    provider = ScriptedProvider([json.dumps({"wrong": "shape"}), VALID])
    result = await provider.complete_structured(make_request())

    assert result.attempts == 2
    assert "did not satisfy the required schema" in provider.seen[1].repair_hint
    assert "value" in provider.seen[1].repair_hint


@pytest.mark.asyncio
async def test_the_base_prompt_is_not_mutated_by_a_repair():
    """The versioned template stays the artifact; hints ride alongside it."""
    provider = ScriptedProvider(["{not json", VALID])
    await provider.complete_structured(make_request(user_prompt="ORIGINAL"))

    assert provider.seen[0].user_prompt == "ORIGINAL"
    assert provider.seen[1].user_prompt == "ORIGINAL"


@pytest.mark.asyncio
@pytest.mark.parametrize("category", sorted(base.TERMINAL_CATEGORIES))
async def test_terminal_categories_fail_on_the_first_attempt(category):
    """Retrying an auth or quota fault just burns time and money."""
    provider = ScriptedProvider([
        AIProviderError(category, "terminal"),
        VALID,
    ])
    with pytest.raises(AIProviderError) as excinfo:
        await provider.complete_structured(make_request())

    assert excinfo.value.category == category
    # The second script entry was never reached.
    assert len(provider.seen) == 1


@pytest.mark.asyncio
async def test_retries_stop_at_max_attempts():
    provider = ScriptedProvider(
        [AIProviderError("timeout", "slow")] * 3, max_attempts=3,
    )
    with pytest.raises(AIProviderError) as excinfo:
        await provider.complete_structured(make_request())

    assert len(provider.seen) == 3
    assert excinfo.value.category == "timeout"
    assert "after 3 attempts" in str(excinfo.value)


@pytest.mark.asyncio
async def test_persistent_bad_output_surfaces_an_error_not_an_empty_result():
    """A storyboard endpoint must never quietly return zero scenes."""
    provider = ScriptedProvider(["nonsense"] * 3, max_attempts=3)
    with pytest.raises(AIProviderError) as excinfo:
        await provider.complete_structured(make_request())
    assert excinfo.value.category == "invalid_json"


@pytest.mark.asyncio
async def test_max_attempts_of_one_disables_retrying():
    provider = ScriptedProvider(["nonsense", VALID], max_attempts=1)
    with pytest.raises(AIProviderError):
        await provider.complete_structured(make_request())
    assert len(provider.seen) == 1


def test_backoff_grows_and_is_capped():
    delays = [_REAL_BACKOFF(i) for i in range(8)]
    # Jittered, so assert the bounds rather than exact values.
    assert all(0 < d <= base.RETRY_MAX_DELAY_SEC for d in delays)
    assert delays[-1] > delays[0]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_unconfigured_provider_never_makes_the_call(monkeypatch):
    monkeypatch.delenv("CAS_TEST_AI_KEY", raising=False)
    provider = KeyedProvider([VALID])

    with pytest.raises(AIProviderError) as excinfo:
        await provider.complete_structured(make_request())

    assert excinfo.value.category == "not_configured"
    assert provider.seen == []


@pytest.mark.asyncio
async def test_a_configured_provider_proceeds(monkeypatch):
    monkeypatch.setenv("CAS_TEST_AI_KEY", "value")
    provider = KeyedProvider([VALID])
    result = await provider.complete_structured(make_request())
    assert result.data == {"value": "ok"}


def test_the_key_is_read_only_from_the_environment(monkeypatch):
    monkeypatch.setenv("CAS_TEST_AI_KEY", "  spaced-key  ")
    assert KeyedProvider([]).api_key() == "spaced-key"


def test_a_keyless_provider_is_always_configured():
    assert ScriptedProvider([]).is_configured() is True


def test_the_error_message_names_the_variable_to_set(monkeypatch):
    monkeypatch.delenv("CAS_TEST_AI_KEY", raising=False)
    with pytest.raises(AIProviderError) as excinfo:
        KeyedProvider([]).require_configured()
    assert "CAS_TEST_AI_KEY" in str(excinfo.value)
