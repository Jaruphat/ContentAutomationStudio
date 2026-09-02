"""
AI text generation for the story tasks.

Layering, outermost first:

* ``tasks`` - project state in, persisted scenes/shots/prompts out. The only
  module here that knows about the ORM.
* ``prompts`` / ``task_schemas`` - versioned templates and the JSON Schemas the
  responses must satisfy. Pure data, no I/O.
* ``registry`` - which providers exist and which one to use.
* ``base`` - the provider contract, plus the retry, validation and provenance
  handling every vendor shares.
* ``mock_provider`` / ``openai_provider`` - one vendor's wire format each.
* ``validation`` - text in, validated object out.

API keys are read from the environment only. They are never accepted over the
API, never stored, and never appear in a response, a log line or an error.
"""

from app.services.ai.base import (
    AIModelInfo,
    AIProvider,
    AIProviderError,
    AIProviderHealth,
    StructuredRequest,
    StructuredResult,
    TokenUsage,
)
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.registry import (
    PROVIDER_CLASSES,
    check_health,
    configuration_blockers,
    create_provider,
    default_provider_id,
    describe_catalogue,
    get_provider_class,
    provider_ids,
)

__all__ = [
    "AIModelInfo",
    "AIProvider",
    "AIProviderError",
    "AIProviderHealth",
    "MockAIProvider",
    "OpenAIProvider",
    "PROVIDER_CLASSES",
    "StructuredRequest",
    "StructuredResult",
    "TokenUsage",
    "check_health",
    "configuration_blockers",
    "create_provider",
    "default_provider_id",
    "describe_catalogue",
    "get_provider_class",
    "provider_ids",
]
