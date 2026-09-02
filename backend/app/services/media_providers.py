"""
Media generation provider registry.

The studio is provider-agnostic: a shot's stills can come from a local ComfyUI
graph or from OpenAI's Images API, and video comes from ComfyUI H3. Everything
downstream of a job - review, approval, the timeline manifest and the FFmpeg
render - works from a Take row and never asks which vendor produced it.

This module is the one place that knows the difference. It answers four
questions for the rest of the application:

* which providers exist, what media each can produce, and whether the local
  environment is configured for them (``describe_catalogue``),
* which provider a given shot and generation mode actually resolves to
  (``resolve_provider_id``) - video never silently leaves ComfyUI,
* what one generation is expected to cost before it is authorised
  (``estimate_image_cost``), and
* which adapter instance executes it (``get_provider``).

**No credential ever passes through here.** ``configured`` is computed as
"the environment variable is non-empty"; the value is never read into a return
value, a log line or an error message.
"""

import os
from dataclasses import dataclass
from typing import Any

from app.services.comfyui_adapter import MediaProvider

COMFYUI = "comfyui"
OPENAI = "openai"

#: Provider used for every video and image-to-video shot, whatever the shot's
#: image provider says. OpenAI's Images API cannot produce video, so routing a
#: video shot to it would be a silent downgrade rather than a choice.
VIDEO_PROVIDER_ID = COMFYUI

DEFAULT_IMAGE_MODEL = "gpt-image-1-mini"
DEFAULT_IMAGE_SIZE = "1024x1024"
DEFAULT_IMAGE_QUALITY = "medium"

#: The environment variable each provider needs. Presence is checked; the
#: value is never read outside the adapter that authenticates with it.
API_KEY_ENV = {OPENAI: "OPENAI_API_KEY"}

#: Published per-image list prices, in USD, used only to show an estimate
#: *before* a paid generation is authorised. They are a convenience, not a
#: billing record: OpenAI can change pricing at any time, and the authoritative
#: number is the usage recorded on the account. ``CAS_OPENAI_IMAGE_PRICE_USD``
#: overrides every entry when a deployment knows its own rate.
#:
#: Keyed by (model, size, quality).
_OPENAI_IMAGE_PRICES: dict[tuple[str, str, str], float] = {
    ("gpt-image-1", "1024x1024", "low"): 0.011,
    ("gpt-image-1", "1024x1024", "medium"): 0.042,
    ("gpt-image-1", "1024x1024", "high"): 0.167,
    ("gpt-image-1", "1024x1536", "low"): 0.016,
    ("gpt-image-1", "1024x1536", "medium"): 0.063,
    ("gpt-image-1", "1024x1536", "high"): 0.25,
    ("gpt-image-1", "1536x1024", "low"): 0.016,
    ("gpt-image-1", "1536x1024", "medium"): 0.063,
    ("gpt-image-1", "1536x1024", "high"): 0.25,
    ("gpt-image-1-mini", "1024x1024", "low"): 0.005,
    ("gpt-image-1-mini", "1024x1024", "medium"): 0.011,
    ("gpt-image-1-mini", "1024x1024", "high"): 0.036,
    ("gpt-image-1-mini", "1024x1536", "low"): 0.006,
    ("gpt-image-1-mini", "1024x1536", "medium"): 0.017,
    ("gpt-image-1-mini", "1024x1536", "high"): 0.054,
    ("gpt-image-1-mini", "1536x1024", "low"): 0.006,
    ("gpt-image-1-mini", "1536x1024", "medium"): 0.017,
    ("gpt-image-1-mini", "1536x1024", "high"): 0.054,
}

SUPPORTED_SIZES = ("1024x1024", "1024x1536", "1536x1024")
SUPPORTED_QUALITIES = ("low", "medium", "high")


class UnknownMediaProviderError(ValueError):
    """Raised when a shot names a provider this build does not have."""


@dataclass(frozen=True)
class CostEstimate:
    """What one generation is expected to cost, and how sure we are."""

    #: None when the provider is free at the API level (local ComfyUI) or when
    #: no rate is known for this model/size/quality combination.
    amount_usd: float | None
    #: Where the number came from: "free", "table", "env" or "unknown".
    source: str
    #: One sentence the UI can show next to the number.
    basis: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "amount_usd": self.amount_usd,
            "source": self.source,
            "basis": self.basis,
        }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def default_image_model() -> str:
    """The image model used when a shot does not name one."""
    return (os.environ.get("OPENAI_IMAGE_MODEL") or "").strip() or DEFAULT_IMAGE_MODEL


def is_configured(provider_id: str) -> bool:
    """Whether the local environment has what this provider needs.

    True only means the variable is set. Whether the credential behind it is
    valid can only be established by a health check, which is a separate,
    explicit call.
    """
    env_name = API_KEY_ENV.get(provider_id)
    if env_name is None:
        return True  # Local ComfyUI needs no credential.
    return bool((os.environ.get(env_name) or "").strip())


def is_paid(provider_id: str) -> bool:
    """Whether one generation on this provider is metered by a vendor."""
    return provider_id == OPENAI


def supports(provider_id: str, generation_mode: str) -> bool:
    if provider_id == OPENAI:
        return generation_mode == "image"
    return True


def resolve_provider_id(shot_provider_id: str | None, generation_mode: str) -> str:
    """The provider that will actually run this shot.

    Video and image-to-video always resolve to ComfyUI: the shot's image
    provider describes stills only.
    """
    if generation_mode != "image":
        return VIDEO_PROVIDER_ID
    provider_id = (shot_provider_id or COMFYUI).strip().lower() or COMFYUI
    if provider_id not in (COMFYUI, OPENAI):
        raise UnknownMediaProviderError(
            f"Unknown media provider '{provider_id}'. Known providers: "
            f"{COMFYUI}, {OPENAI}."
        )
    return provider_id


def resolve_model(provider_id: str, shot_model: str | None) -> str:
    """The model/workflow label recorded on the job for this provider."""
    model = (shot_model or "").strip()
    if provider_id == OPENAI:
        return model if model and model != "workflow" else default_image_model()
    # ComfyUI is driven by a registered workflow, not a model name.
    return model or "workflow"


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def normalise_size(width: Any, height: Any) -> str:
    """Map a shot's pixel dimensions onto the nearest supported image size."""
    try:
        width_i, height_i = int(width or 0), int(height or 0)
    except (TypeError, ValueError):
        width_i = height_i = 0
    if width_i <= 0 or height_i <= 0:
        return DEFAULT_IMAGE_SIZE
    if width_i > height_i:
        return "1536x1024"
    if height_i > width_i:
        return "1024x1536"
    return "1024x1024"


def estimate_image_cost(
    provider_id: str,
    model: str,
    size: str = DEFAULT_IMAGE_SIZE,
    quality: str = DEFAULT_IMAGE_QUALITY,
    count: int = 1,
) -> CostEstimate:
    """Estimated USD cost of ``count`` images from this provider.

    Local generation is reported as free at the API level - it still costs GPU
    time, which the basis line says rather than pretending the run is costless.
    """
    if provider_id != OPENAI:
        return CostEstimate(
            amount_usd=None,
            source="free",
            basis=(
                "Local ComfyUI generation is not metered by an API vendor. It "
                "uses GPU time on this machine."
            ),
        )

    count = max(1, count)
    override = (os.environ.get("CAS_OPENAI_IMAGE_PRICE_USD") or "").strip()
    if override:
        try:
            return CostEstimate(
                amount_usd=round(float(override) * count, 4),
                source="env",
                basis=(
                    "Rate taken from CAS_OPENAI_IMAGE_PRICE_USD, multiplied by "
                    f"{count} image(s)."
                ),
            )
        except ValueError:
            pass

    price = _OPENAI_IMAGE_PRICES.get((model, size, quality))
    if price is None:
        return CostEstimate(
            amount_usd=None,
            source="unknown",
            basis=(
                f"No published rate is recorded for {model} at {size}/{quality}. "
                f"This generation is metered - check your OpenAI pricing page "
                f"before confirming."
            ),
        )
    return CostEstimate(
        amount_usd=round(price * count, 4),
        source="table",
        basis=(
            f"Estimate only: {count} x {model} at {size}/{quality} list price. "
            f"The charge recorded on your account is authoritative."
        ),
    )


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def describe_catalogue() -> dict[str, Any]:
    """Everything the UI needs to offer a provider choice, and nothing more.

    Makes no network call and reads no credential value, so it is safe to poll
    and safe to render.
    """
    image_model = default_image_model()
    return {
        "video_provider_id": VIDEO_PROVIDER_ID,
        "default_image_provider_id": COMFYUI,
        "providers": [
            {
                "id": COMFYUI,
                "label": "Local ComfyUI",
                "configured": True,
                "local": True,
                "mock": _comfyui_is_mock(),
                "media_types": ["image", "video", "image-to-video"],
                "default_model": "workflow",
                "models": [{"id": "workflow", "label": "Assigned workflow"}],
                "api_key_env": "",
                "requires_confirmation": False,
                "cost_warning": (
                    "Local generation uses GPU time but has no per-image API "
                    "charge."
                ),
                "sizes": [],
                "qualities": [],
            },
            {
                "id": OPENAI,
                "label": "OpenAI Images",
                "configured": is_configured(OPENAI),
                "local": False,
                "mock": False,
                "media_types": ["image"],
                "default_model": image_model,
                "models": [
                    {"id": name, "label": name}
                    for name in dict.fromkeys(
                        [image_model, "gpt-image-1-mini", "gpt-image-1"]
                    )
                ],
                "api_key_env": API_KEY_ENV[OPENAI],
                "requires_confirmation": True,
                "cost_warning": (
                    "OpenAI Images is metered. One confirmed generation "
                    "creates one paid image per selected shot; the price "
                    "depends on model, size and quality."
                ),
                "sizes": list(SUPPORTED_SIZES),
                "qualities": list(SUPPORTED_QUALITIES),
            },
        ],
    }


def _comfyui_is_mock() -> bool:
    # Imported here: the queue manager imports this module for per-job routing.
    from app.services.queue_manager import queue_manager

    return type(queue_manager.provider).__name__.startswith("Mock")


# ---------------------------------------------------------------------------
# Adapter instances
# ---------------------------------------------------------------------------

_openai_provider: MediaProvider | None = None


def get_provider(provider_id: str) -> MediaProvider:
    """The adapter that executes jobs for this provider.

    The ComfyUI adapter is whatever the queue manager was configured with at
    startup (mock or real), so mock mode keeps working unchanged. The OpenAI
    adapter is built once and reused; it reads its key from the environment at
    construction time and never from a job payload.
    """
    global _openai_provider

    if provider_id == OPENAI:
        from app.services.openai_image_provider import OpenAIImageProvider

        if _openai_provider is None:
            _openai_provider = OpenAIImageProvider()
        return _openai_provider

    if provider_id == COMFYUI:
        from app.services.queue_manager import queue_manager

        return queue_manager.provider

    raise UnknownMediaProviderError(f"Unknown media provider '{provider_id}'.")


def reset_provider_cache() -> None:
    """Drop the cached OpenAI adapter so a changed environment is picked up.

    Used by the test suite, and by any caller that re-reads configuration.
    """
    global _openai_provider
    _openai_provider = None
