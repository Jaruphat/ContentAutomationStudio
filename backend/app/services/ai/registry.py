"""
Which AI providers exist, which one to use, and whether they work.

This is the only module that knows the set of providers. Routers and task
services ask it for a provider by id and get an :class:`AIProvider` back; they
never import a vendor module. Adding Anthropic or Google means adding a class
to :data:`PROVIDER_CLASSES` and nothing else.

Selection follows one rule, in this order:

1. An explicit provider id from the request - what the user picked in the UI.
2. ``CAS_AI_PROVIDER`` from the environment, when an operator has pinned one.
3. OpenAI when ``OPENAI_API_KEY`` is set.
4. The deterministic mock.

Step 4 is what makes the product usable with no key at all, and step 3 is what
makes a configured key take effect without further setup. An explicitly pinned
provider is *not* silently downgraded when it turns out to be unconfigured: the
call fails with ``not_configured`` and says which variable to set, because
quietly substituting mock output for a requested model would put unlabelled
placeholder text into a user's storyboard.
"""

import os

from app.services.ai.base import AIModelInfo, AIProvider, AIProviderError, AIProviderHealth
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.openai_provider import OpenAIProvider

#: Every provider the application can use. Order is the display order.
PROVIDER_CLASSES: tuple[type[AIProvider], ...] = (
    MockAIProvider,
    OpenAIProvider,
)

#: Overrides automatic selection. Set to a provider id, e.g. "mock".
PROVIDER_ENV = "CAS_AI_PROVIDER"


def provider_ids() -> list[str]:
    return [cls.id for cls in PROVIDER_CLASSES]


def get_provider_class(provider_id: str) -> type[AIProvider]:
    """The class for ``provider_id``, or raise ``bad_request``."""
    for cls in PROVIDER_CLASSES:
        if cls.id == provider_id:
            return cls
    raise AIProviderError(
        "bad_request",
        f"Unknown AI provider '{provider_id}'. Available: "
        f"{', '.join(provider_ids())}.",
    )


def default_provider_id() -> str:
    """The provider to use when the caller did not name one."""
    pinned = os.environ.get(PROVIDER_ENV, "").strip().lower()
    if pinned:
        # Validated rather than trusted: a typo here would otherwise surface
        # much later as a confusing task failure.
        get_provider_class(pinned)
        return pinned

    for cls in PROVIDER_CLASSES:
        # Skip the mock during auto-selection; it is the fallback, not a
        # candidate, and it always reports itself as configured.
        if cls is MockAIProvider:
            continue
        if cls(model="").is_configured():
            return cls.id

    return MockAIProvider.id


def create_provider(
    provider_id: str = "", model: str = "", **kwargs
) -> AIProvider:
    """Instantiate a provider. ``provider_id`` empty means auto-select."""
    resolved = (provider_id or "").strip().lower() or default_provider_id()
    return get_provider_class(resolved)(model=model.strip(), **kwargs)


# ---------------------------------------------------------------------------
# Catalogue and health
# ---------------------------------------------------------------------------

def _model_entry(info: AIModelInfo) -> dict[str, object]:
    return {
        "id": info.id,
        "label": info.label,
        "supports_structured_output": info.supports_structured_output,
        "note": info.note,
    }


def describe_provider(cls: type[AIProvider]) -> dict[str, object]:
    """One provider's static description, plus whether it is configured.

    The catalogue is deliberately cheap: it makes no network call, so the UI
    can populate its selector instantly and ask for health separately.
    """
    instance = cls(model="")
    return {
        "id": cls.id,
        "label": cls.label,
        "configured": instance.is_configured(),
        "requires_network": cls.requires_network,
        "requires_key": bool(cls.api_key_env),
        "api_key_env": cls.api_key_env,
        "default_model": cls.default_model,
        "mock": cls is MockAIProvider,
        "models": [_model_entry(m) for m in cls.catalogue],
    }


def describe_catalogue() -> dict[str, object]:
    """Every provider, with the id that would be used by default."""
    return {
        "default_provider_id": default_provider_id(),
        "providers": [describe_provider(cls) for cls in PROVIDER_CLASSES],
    }


async def check_health(provider_id: str = "") -> list[AIProviderHealth]:
    """Live health for one provider, or all of them.

    Never raises: a provider that cannot be reached reports ``online: false``
    with a reason, which is what the UI needs to render.
    """
    if provider_id:
        classes: tuple[type[AIProvider], ...] = (get_provider_class(provider_id),)
    else:
        classes = PROVIDER_CLASSES

    results: list[AIProviderHealth] = []
    for cls in classes:
        provider = cls(model="")
        try:
            results.append(await provider.check_health())
        except Exception as exc:  # pragma: no cover - check_health must not raise
            results.append(
                AIProviderHealth(
                    provider_id=cls.id,
                    configured=provider.is_configured(),
                    online=False,
                    error=f"Health check failed: {type(exc).__name__}.",
                )
            )
    return results


def configuration_blockers() -> list[str]:
    """Honest, user-facing notes about what AI generation cannot do yet.

    Surfaced by ``GET /api/health`` alongside the ComfyUI blockers so the
    limitation is visible without having to call an AI endpoint and fail.
    """
    blockers: list[str] = []
    for cls in PROVIDER_CLASSES:
        if cls is MockAIProvider or not cls.api_key_env:
            continue
        if not cls(model="").is_configured():
            blockers.append(
                f"{cls.label} is not configured: {cls.api_key_env} is not set, "
                f"so no real language model can be called. AI storyboard and "
                f"prompt tasks fall back to the deterministic mock provider, "
                f"whose output is mechanically derived from the input and is "
                f"not authored."
            )
    return blockers
