"""
OpenAI provider.

Speaks the Chat Completions API over httpx, which the project already depends
on for ComfyUI. The vendor SDK is deliberately not used: the adapter is one
request shape and one response shape, and going direct means the tests exercise
the bytes that would actually go on the wire rather than a mocked-out client
method.

Structured output is requested with ``response_format: json_schema`` and
``strict: true`` so the model is constrained server-side, but the result is
still validated locally by the shared base class. Server-side enforcement is
a nicety; the guarantee is ours.

The key comes from ``OPENAI_API_KEY`` in the environment - loaded from ``.env``
at startup if present - and nowhere else. It is sent in the Authorization
header and appears in no log line, no error message and no API response.
"""

import logging
import os
from typing import Any

import httpx

from app.services.ai.base import (
    AIModelInfo,
    AIProvider,
    AIProviderError,
    AIProviderHealth,
    StructuredRequest,
    TokenUsage,
)

logger = logging.getLogger("cas.ai.openai")

DEFAULT_BASE_URL = "https://api.openai.com/v1"

#: Offered in the selector when the vendor cannot be queried live. The live
#: list from ``GET /v1/models`` is preferred whenever the provider is
#: configured, so this is a starting point rather than a claim about what the
#: account can actually reach.
CATALOGUE: tuple[AIModelInfo, ...] = (
    AIModelInfo(
        "gpt-4.1", "GPT-4.1",
        note="Strong default for story decomposition.",
    ),
    AIModelInfo(
        "gpt-4.1-mini", "GPT-4.1 mini",
        note="Cheaper and faster; good for prompt compilation.",
    ),
    AIModelInfo(
        "gpt-4o", "GPT-4o",
        note="Widely available fallback.",
    ),
    AIModelInfo(
        "gpt-4o-mini", "GPT-4o mini",
        note="Lowest cost of the listed models.",
    ),
)


class OpenAIProvider(AIProvider):
    """Structured text generation through OpenAI Chat Completions."""

    id = "openai"
    label = "OpenAI"
    api_key_env = "OPENAI_API_KEY"
    default_model = "gpt-4.1"
    catalogue = CATALOGUE

    def __init__(
        self,
        *,
        model: str = "",
        base_url: str = "",
        timeout_sec: float = 120.0,
        max_attempts: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        super().__init__(
            model=model or os.environ.get("OPENAI_MODEL", "").strip(),
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
        )
        self.base_url = (
            base_url
            or os.environ.get("OPENAI_BASE_URL", "").strip()
            or DEFAULT_BASE_URL
        ).rstrip("/")
        # Injected by the tests so the exact request this builds is asserted
        # against, rather than the call being stubbed out a layer higher.
        self._transport = transport

    # -- wire format --------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key()}",
            "Content-Type": "application/json",
        }
        organization = os.environ.get("OPENAI_ORG_ID", "").strip()
        if organization:
            headers["OpenAI-Organization"] = organization
        return headers

    def build_payload(self, request: StructuredRequest) -> dict[str, Any]:
        """The request body. Separated out so tests can assert on it directly."""
        user_content = request.user_prompt
        if request.repair_hint:
            user_content = f"{user_content}\n\nCORRECTION\n{request.repair_hint}"

        return {
            "model": request.model or self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.json_schema,
                },
            },
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_sec,
            transport=self._transport,
        )

    @staticmethod
    def _classify(status_code: int) -> str:
        """Map an HTTP status onto a retry category."""
        if status_code in (401, 403):
            return "auth"
        if status_code == 429:
            return "rate_limit"
        if status_code == 402:
            return "quota"
        if status_code == 400:
            return "bad_request"
        if status_code == 404:
            # A model name the account cannot reach. Retrying will not help.
            return "bad_request"
        if status_code >= 500:
            return "server_error"
        return "unknown"

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        """A short, safe description of a failed call.

        Only the vendor's own message is used. The request body is never echoed
        back, because it holds the user's brief and plot.
        """
        try:
            body = response.json()
        except ValueError:
            return f"HTTP {response.status_code}"
        error = body.get("error") or {}
        message = error.get("message") or ""
        code = error.get("code") or error.get("type") or ""
        parts = [p for p in (f"HTTP {response.status_code}", code, message) if p]
        return " - ".join(parts)[:500]

    async def _complete_once(
        self, request: StructuredRequest
    ) -> tuple[str, str, TokenUsage, str]:
        payload = self.build_payload(request)

        try:
            async with self._client() as client:
                response = await client.post(
                    "/chat/completions", json=payload, headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                "timeout",
                f"OpenAI did not respond within {self.timeout_sec:g}s.",
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                "connection", f"Could not reach OpenAI: {type(exc).__name__}."
            ) from exc

        if response.status_code >= 400:
            raise AIProviderError(
                self._classify(response.status_code),
                self._error_detail(response),
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "server_error", "OpenAI returned a response that was not JSON."
            ) from exc

        choices = body.get("choices") or []
        if not choices:
            raise AIProviderError(
                "server_error", "OpenAI returned no choices in the response."
            )

        choice = choices[0]
        finish_reason = choice.get("finish_reason") or ""
        message = choice.get("message") or {}

        if message.get("refusal"):
            # A refusal is a decision, not a transport fault; retrying it three
            # times just repeats it.
            raise AIProviderError(
                "content_filter",
                f"The model declined this request: {message['refusal']}"[:500],
            )
        if finish_reason == "length":
            raise AIProviderError(
                "invalid_json",
                "The response was cut off by the output token limit, so it is "
                "incomplete JSON. Raise max_output_tokens or ask for fewer "
                "shots per call.",
            )

        content = message.get("content")
        if not content:
            raise AIProviderError(
                "server_error", "OpenAI returned an empty message."
            )

        usage_body = body.get("usage") or {}
        usage = TokenUsage(
            prompt_tokens=int(usage_body.get("prompt_tokens") or 0),
            completion_tokens=int(usage_body.get("completion_tokens") or 0),
            total_tokens=int(usage_body.get("total_tokens") or 0),
        )
        # The served model, which for an alias is the dated build that ran.
        served_model = body.get("model") or payload["model"]
        return content, served_model, usage, body.get("id") or ""

    # -- health -------------------------------------------------------------

    async def check_health(self) -> AIProviderHealth:
        """Ask the vendor what it can serve. Never raises."""
        if not self.is_configured():
            return AIProviderHealth(
                provider_id=self.id,
                configured=False,
                error=f"{self.api_key_env} is not set.",
            )
        try:
            async with self._client() as client:
                response = await client.get("/models", headers=self._headers())
            if response.status_code >= 400:
                return AIProviderHealth(
                    provider_id=self.id, configured=True, online=False,
                    error=self._error_detail(response),
                )
            data = response.json().get("data") or []
            models = sorted(
                str(entry.get("id"))
                for entry in data
                if entry.get("id") and str(entry["id"]).startswith("gpt")
            )
            return AIProviderHealth(
                provider_id=self.id, configured=True, online=True, models=models,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return AIProviderHealth(
                provider_id=self.id, configured=True, online=False,
                error=f"Could not reach OpenAI: {type(exc).__name__}.",
            )
