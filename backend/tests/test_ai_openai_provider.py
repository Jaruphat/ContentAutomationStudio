"""
Tests for the OpenAI adapter.

Every call goes through ``httpx.MockTransport``, so the assertions are against
the exact request the provider would put on the wire and the exact response
shapes OpenAI returns. No test here reaches the network, and none needs a key
beyond a fake one in the environment.

The suite deliberately covers the failure modes that decide the retry policy:
which status codes are terminal, what a refusal is, and what a truncated
response means.
"""

import json

import httpx
import pytest

from app.services.ai import base
from app.services.ai.base import AIProviderError, StructuredRequest
from app.services.ai.openai_provider import OpenAIProvider

SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}

FAKE_KEY = "sk-test-fake-key-not-real"


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    # The retry sleep would otherwise make the failure tests take seconds.
    monkeypatch.setattr(base, "_backoff_delay", lambda index: 0.0)


def make_request(**overrides) -> StructuredRequest:
    fields = {
        "task": "unit_test",
        "system_prompt": "You are a director.",
        "user_prompt": "Decompose this brief.",
        "schema_name": "unit_test",
        "json_schema": SCHEMA,
        "prompt_version": "1.0",
        "schema_version": "1.0",
    }
    fields.update(overrides)
    return StructuredRequest(**fields)


def completion_body(content: str, **overrides) -> dict:
    body = {
        "id": "chatcmpl-abc123",
        "model": "gpt-4.1-2026-01-01",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": content},
        }],
        "usage": {
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
        },
    }
    body.update(overrides)
    return body


def provider_returning(handler, **kwargs) -> OpenAIProvider:
    return OpenAIProvider(transport=httpx.MockTransport(handler), **kwargs)


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------

def test_the_payload_requests_strict_structured_output():
    payload = OpenAIProvider().build_payload(make_request())

    response_format = payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == SCHEMA


def test_the_payload_carries_system_and_user_messages():
    payload = OpenAIProvider().build_payload(make_request())
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert payload["messages"][0]["content"] == "You are a director."
    assert payload["messages"][1]["content"] == "Decompose this brief."


def test_a_repair_hint_is_appended_to_the_user_message_only():
    request = make_request().with_repair_hint("Fix the trailing comma.")
    payload = OpenAIProvider().build_payload(request)

    assert "Decompose this brief." in payload["messages"][1]["content"]
    assert "Fix the trailing comma." in payload["messages"][1]["content"]
    # The system prompt is the versioned artifact and must stay untouched.
    assert payload["messages"][0]["content"] == "You are a director."


def test_the_request_model_overrides_the_provider_default():
    payload = OpenAIProvider(model="gpt-4o").build_payload(
        make_request(model="gpt-4.1-mini")
    )
    assert payload["model"] == "gpt-4.1-mini"


def test_the_model_comes_from_the_environment_when_unset(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    assert OpenAIProvider().model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_the_key_is_sent_as_a_bearer_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json=completion_body('{"value": "ok"}'))

    await provider_returning(handler).complete_structured(make_request())

    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    assert seen["url"].endswith("/chat/completions")


@pytest.mark.asyncio
async def test_the_base_url_is_configurable(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=completion_body('{"value": "ok"}'))

    await provider_returning(handler).complete_structured(make_request())
    assert seen["url"].startswith("https://proxy.example/v1/")


@pytest.mark.asyncio
async def test_the_organisation_header_is_sent_when_set(monkeypatch):
    monkeypatch.setenv("OPENAI_ORG_ID", "org-123")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["org"] = request.headers.get("openai-organization")
        return httpx.Response(200, json=completion_body('{"value": "ok"}'))

    await provider_returning(handler).complete_structured(make_request())
    assert seen["org"] == "org-123"


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_successful_call_returns_validated_data_and_usage():
    def handler(request):
        return httpx.Response(200, json=completion_body('{"value": "ok"}'))

    result = await provider_returning(handler).complete_structured(make_request())

    assert result.data == {"value": "ok"}
    assert result.provider_id == "openai"
    # The dated build the vendor actually served, not the alias requested.
    assert result.model == "gpt-4.1-2026-01-01"
    assert result.response_id == "chatcmpl-abc123"
    assert result.usage.total_tokens == 150


@pytest.mark.asyncio
async def test_a_fenced_response_is_still_accepted():
    def handler(request):
        return httpx.Response(
            200, json=completion_body('```json\n{"value": "ok"}\n```'),
        )

    result = await provider_returning(handler).complete_structured(make_request())
    assert result.data == {"value": "ok"}


@pytest.mark.asyncio
async def test_strict_mode_output_is_still_validated_locally():
    """Server-side enforcement is a nicety; the guarantee is ours."""
    def handler(request):
        return httpx.Response(200, json=completion_body('{"unexpected": 1}'))

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler, max_attempts=1).complete_structured(
            make_request()
        )
    assert excinfo.value.category == "schema_violation"


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,category", [
    (401, "auth"),
    (403, "auth"),
    (429, "rate_limit"),
    (402, "quota"),
    (400, "bad_request"),
    (404, "bad_request"),
    (500, "server_error"),
    (503, "server_error"),
    (418, "unknown"),
])
def test_status_codes_map_to_retry_categories(status, category):
    assert OpenAIProvider._classify(status) == category


@pytest.mark.asyncio
async def test_an_auth_failure_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"error": {
            "message": "Incorrect API key provided", "code": "invalid_api_key",
        }})

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler).complete_structured(make_request())

    assert excinfo.value.category == "auth"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_server_error_is_retried_then_succeeds():
    responses = [
        httpx.Response(500, json={"error": {"message": "overloaded"}}),
        httpx.Response(200, json=completion_body('{"value": "ok"}')),
    ]

    def handler(request):
        return responses.pop(0)

    result = await provider_returning(handler).complete_structured(make_request())
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_a_refusal_is_terminal_not_transient():
    """A refusal is a decision; retrying it three times just repeats it."""
    body = completion_body("")
    body["choices"][0]["message"] = {"refusal": "I can't help with that."}
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=body)

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler).complete_structured(make_request())

    assert excinfo.value.category == "content_filter"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_truncated_response_is_reported_as_incomplete_json():
    body = completion_body('{"value": "ok')
    body["choices"][0]["finish_reason"] = "length"

    def handler(request):
        return httpx.Response(200, json=body)

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler, max_attempts=1).complete_structured(
            make_request()
        )
    assert excinfo.value.category == "invalid_json"
    assert "token limit" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_timeout_is_classified_as_a_timeout():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler, max_attempts=1).complete_structured(
            make_request()
        )
    assert excinfo.value.category == "timeout"


@pytest.mark.asyncio
async def test_a_connection_failure_is_classified_as_connection():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler, max_attempts=1).complete_structured(
            make_request()
        )
    assert excinfo.value.category == "connection"


@pytest.mark.asyncio
async def test_an_empty_choices_list_is_a_server_error():
    def handler(request):
        return httpx.Response(200, json=completion_body("", choices=[]))

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler, max_attempts=1).complete_structured(
            make_request()
        )
    assert excinfo.value.category == "server_error"


@pytest.mark.asyncio
async def test_a_non_json_body_is_a_server_error():
    def handler(request):
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler, max_attempts=1).complete_structured(
            make_request()
        )
    assert excinfo.value.category == "server_error"


# ---------------------------------------------------------------------------
# Secret hygiene
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_error_message_echoes_the_key_or_the_prompt():
    """Vendor errors can quote the request back, and the request holds the
    user's brief. Only the vendor's own message is surfaced."""
    def handler(request):
        return httpx.Response(400, json={"error": {
            "message": "Invalid value",
            "code": "invalid_request_error",
            "param": "messages",
            # A hostile or careless upstream echoing the request back.
            "request_body": json.loads(request.content.decode()),
        }})

    with pytest.raises(AIProviderError) as excinfo:
        await provider_returning(handler).complete_structured(
            make_request(user_prompt="TOP SECRET PLOT")
        )

    message = str(excinfo.value)
    assert FAKE_KEY not in message
    assert "TOP SECRET PLOT" not in message
    assert "Invalid value" in message


def test_the_error_detail_is_length_bounded():
    response = httpx.Response(
        400, json={"error": {"message": "x" * 5000}},
    )
    assert len(OpenAIProvider._error_detail(response)) <= 500


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_lists_the_models_the_account_can_reach():
    def handler(request):
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"data": [
            {"id": "gpt-4.1"},
            {"id": "gpt-4o-mini"},
            {"id": "text-embedding-3-small"},
        ]})

    health = await provider_returning(handler).check_health()

    assert health.online is True
    assert health.configured is True
    assert health.mock is False
    # Embedding models are not text generators and are filtered out.
    assert health.models == ["gpt-4.1", "gpt-4o-mini"]


@pytest.mark.asyncio
async def test_health_reports_an_auth_failure_without_raising():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    health = await provider_returning(handler).check_health()

    assert health.configured is True
    assert health.online is False
    assert "bad key" in health.error


@pytest.mark.asyncio
async def test_health_reports_an_unreachable_vendor_without_raising():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    health = await provider_returning(handler).check_health()

    assert health.online is False
    assert "Could not reach OpenAI" in health.error


@pytest.mark.asyncio
async def test_health_without_a_key_makes_no_request(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    called = []

    def handler(request):
        called.append(1)
        return httpx.Response(200, json={"data": []})

    health = await provider_returning(handler).check_health()

    assert called == []
    assert health.configured is False
    assert "OPENAI_API_KEY" in health.error
