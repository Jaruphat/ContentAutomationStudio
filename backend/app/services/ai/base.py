"""
Provider-neutral contract for AI text generation.

Everything above this module - story decomposition, storyboard expansion,
prompt compilation - depends only on :class:`AIProvider`. A provider is a thin
adapter that knows one vendor's HTTP shape and nothing about scenes, shots or
storyboards, which is what makes adding Anthropic or Google a new file rather
than a change to the call sites.

Three things are deliberately handled here rather than per provider, so every
vendor behaves identically:

* **Retry policy.** :func:`run_with_retries` classifies a failure, retries only
  the transient categories with exponential backoff, and hands the model its
  own invalid output as feedback when it produced malformed JSON.
* **Schema validation.** A response is only a success once it validates against
  the request's JSON Schema. Vendors that support strict structured output are
  still re-validated locally - the guarantee is ours, not theirs.
* **Provenance.** Every result carries the provider, the exact model string the
  vendor echoed back, and the prompt and schema versions the request was built
  from, so a stored artifact can be traced to what produced it.

API keys are read from the environment only, are never accepted over the API,
and never appear in a result, a log line or an error message.
"""

import asyncio
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, ClassVar

from app.services.ai.validation import SchemaViolation, validate_against_schema

logger = logging.getLogger("cas.ai")

#: Categories a provider failure can fall into. Only the transient ones are
#: retried; an auth or quota problem is a configuration fault and retrying it
#: just burns time and money.
RETRYABLE_CATEGORIES = frozenset({
    "connection",
    "timeout",
    "rate_limit",
    "server_error",
    "invalid_json",
    "schema_violation",
})

TERMINAL_CATEGORIES = frozenset({
    "auth",
    "quota",
    "bad_request",
    "content_filter",
    "not_configured",
    "unknown",
})


class AIProviderError(RuntimeError):
    """A provider call failed, tagged with why.

    ``category`` drives the retry decision and is what the API surfaces to the
    user, so it must never be widened to carry a raw provider payload: those
    can echo back the request, and the request contains the user's story.
    """

    def __init__(self, category: str, message: str, *, status_code: int = 0):
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.category in RETRYABLE_CATEGORIES


@dataclass(frozen=True)
class AIModelInfo:
    """One model a provider can be asked for."""

    id: str
    label: str
    #: Whether the vendor can enforce a JSON Schema server-side. When false the
    #: provider asks for JSON in the prompt and relies on local validation and
    #: the retry loop instead - the contract is the same either way.
    supports_structured_output: bool = True
    note: str = ""


@dataclass(frozen=True)
class StructuredRequest:
    """One structured-output call.

    ``prompt_version`` and ``schema_version`` are carried on the request rather
    than looked up later so the provenance recorded with a result is the
    version that actually produced it, even if the templates move on.
    """

    task: str
    system_prompt: str
    user_prompt: str
    schema_name: str
    json_schema: dict[str, Any]
    prompt_version: str
    schema_version: str
    model: str = ""
    temperature: float = 0.4
    max_output_tokens: int = 8000
    #: Extra guidance appended on a retry, e.g. the validation error from the
    #: previous attempt. Kept separate from ``user_prompt`` so the base prompt
    #: stays the versioned artifact.
    repair_hint: str = ""

    def with_repair_hint(self, hint: str) -> "StructuredRequest":
        from dataclasses import replace
        return replace(self, repair_hint=hint)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class StructuredResult:
    """A validated response plus everything needed to reproduce it."""

    data: dict[str, Any]
    provider_id: str
    #: The model the vendor reported serving, not the one requested: an alias
    #: such as "gpt-4.1" resolves to a dated build, and the dated build is what
    #: the provenance record has to name.
    model: str
    prompt_version: str
    schema_version: str
    attempts: int = 1
    latency_ms: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    response_id: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class AIProviderHealth:
    provider_id: str
    configured: bool
    online: bool = False
    #: Models the vendor actually reports. Empty when the provider has not been
    #: asked, or could not be reached - never a guess.
    models: list[str] = field(default_factory=list)
    error: str = ""
    mock: bool = False


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------

class AIProvider(ABC):
    """One vendor's structured-text API.

    Subclasses implement :meth:`_complete_once` - a single attempt, no retry
    logic - and the shared :meth:`complete_structured` wraps it in the common
    retry, validation and provenance handling.
    """

    #: Stable identifier used in the API, the frontend selector and provenance.
    id: ClassVar[str] = ""
    label: ClassVar[str] = ""
    #: Environment variable holding the key. Never read from anywhere else.
    api_key_env: ClassVar[str] = ""
    default_model: ClassVar[str] = ""
    #: Models offered in the selector when the vendor cannot be queried live.
    catalogue: ClassVar[tuple[AIModelInfo, ...]] = ()
    #: False for providers that never leave the machine.
    requires_network: ClassVar[bool] = True

    def __init__(self, *, model: str = "", timeout_sec: float = 120.0,
                 max_attempts: int = 3):
        self.model = model or self.default_model
        self.timeout_sec = timeout_sec
        self.max_attempts = max(1, max_attempts)

    # -- configuration ------------------------------------------------------

    def api_key(self) -> str:
        """The key from the environment, or '' when unset.

        Callers must never log or return the value; use :meth:`is_configured`
        to report configuration state.
        """
        if not self.api_key_env:
            return ""
        return os.environ.get(self.api_key_env, "").strip()

    def is_configured(self) -> bool:
        """Whether this provider has what it needs to run."""
        return bool(self.api_key()) if self.api_key_env else True

    def require_configured(self) -> None:
        if not self.is_configured():
            raise AIProviderError(
                "not_configured",
                f"{self.label} is not configured. Set {self.api_key_env} in the "
                f"environment or a .env file; the key is never read from the "
                f"request or stored in the database.",
            )

    # -- the call -----------------------------------------------------------

    @abstractmethod
    async def _complete_once(
        self, request: StructuredRequest
    ) -> tuple[str, str, TokenUsage, str]:
        """One attempt.

        Returns ``(raw_text, served_model, usage, response_id)``. Raises
        :class:`AIProviderError` with a category on failure. Must not retry:
        the shared loop owns that.
        """

    async def complete_structured(
        self, request: StructuredRequest
    ) -> StructuredResult:
        """Run the request until it yields JSON that validates, or give up.

        Malformed or schema-violating output is retried with the failure fed
        back to the model, which is the difference between a transcription slip
        the model can fix and a genuine refusal.
        """
        self.require_configured()
        started = time.monotonic()
        warnings: list[str] = []

        async def attempt(current: StructuredRequest) -> tuple[dict[str, Any], str, TokenUsage, str]:
            raw, served_model, usage, response_id = await self._complete_once(current)
            data = validate_against_schema(raw, request.json_schema)
            return data, served_model, usage, response_id

        data, served_model, usage, response_id, attempts = await run_with_retries(
            attempt, request, self.max_attempts, warnings,
        )

        return StructuredResult(
            data=data,
            provider_id=self.id,
            model=served_model or self.model,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            attempts=attempts,
            latency_ms=int((time.monotonic() - started) * 1000),
            usage=usage,
            response_id=response_id,
            warnings=warnings,
        )

    async def check_health(self) -> AIProviderHealth:
        """Whether the provider is usable. Never raises."""
        return AIProviderHealth(
            provider_id=self.id,
            configured=self.is_configured(),
            online=self.is_configured(),
        )


# ---------------------------------------------------------------------------
# Shared retry policy
# ---------------------------------------------------------------------------

#: Base backoff in seconds; each retry waits base * 2**n plus jitter.
RETRY_BASE_DELAY_SEC = 1.0
RETRY_MAX_DELAY_SEC = 20.0


def _backoff_delay(attempt_index: int) -> float:
    delay = min(RETRY_BASE_DELAY_SEC * (2 ** attempt_index), RETRY_MAX_DELAY_SEC)
    # Jitter keeps several shots queued at once from retrying in lockstep.
    return delay * (0.5 + random.random() / 2)


async def run_with_retries(
    attempt: Callable[[StructuredRequest], Awaitable[tuple[dict[str, Any], str, TokenUsage, str]]],
    request: StructuredRequest,
    max_attempts: int,
    warnings: list[str],
) -> tuple[dict[str, Any], str, TokenUsage, str, int]:
    """Retry ``attempt`` under the shared policy.

    Transient transport failures are retried unchanged. A malformed or
    schema-violating response is retried with the specific complaint appended
    to the prompt, because a model that emitted a trailing comma usually fixes
    it when told; one that refused the task will fail the same way three times
    and surface a real error rather than an empty storyboard.
    """
    current = request
    last_error: AIProviderError | None = None

    for index in range(max_attempts):
        try:
            data, served_model, usage, response_id = await attempt(current)
            return data, served_model, usage, response_id, index + 1
        except SchemaViolation as exc:
            last_error = AIProviderError(
                exc.category,
                f"The model's response did not match the {request.schema_name} "
                f"schema: {exc}",
            )
            current = current.with_repair_hint(exc.repair_hint())
        except AIProviderError as exc:
            last_error = exc
            if not exc.retryable:
                raise

        warnings.append(
            f"Attempt {index + 1} failed ({last_error.category}); retrying."
        )
        logger.warning(
            "AI attempt %d/%d for task %s failed: %s",
            index + 1, max_attempts, request.task, last_error.category,
        )
        if index + 1 < max_attempts:
            await asyncio.sleep(_backoff_delay(index))

    assert last_error is not None
    raise AIProviderError(
        last_error.category,
        f"{request.task} failed after {max_attempts} attempts: "
        f"{last_error.message}",
        status_code=last_error.status_code,
    )
