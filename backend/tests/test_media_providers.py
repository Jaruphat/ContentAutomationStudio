"""The media provider registry: routing, configuration and cost.

These tests pin the rules that decide where a shot's media comes from and what
it is allowed to cost, because both are decisions a user is charged for.
"""

import pytest

from app.services import media_providers


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def test_image_shot_honours_the_shot_provider():
    assert media_providers.resolve_provider_id("openai", "image") == "openai"
    assert media_providers.resolve_provider_id("comfyui", "image") == "comfyui"


@pytest.mark.parametrize("mode", ["video", "image-to-video"])
def test_video_never_leaves_comfyui_whatever_the_shot_says(mode):
    """OpenAI Images cannot produce video, so routing there would be a silent
    downgrade rather than a choice the user made."""
    assert media_providers.resolve_provider_id("openai", mode) == "comfyui"


def test_missing_provider_falls_back_to_local():
    assert media_providers.resolve_provider_id(None, "image") == "comfyui"
    assert media_providers.resolve_provider_id("", "image") == "comfyui"


def test_unknown_provider_is_refused_rather_than_guessed():
    with pytest.raises(media_providers.UnknownMediaProviderError):
        media_providers.resolve_provider_id("midjourney", "image")


def test_openai_only_supports_images():
    assert media_providers.supports("openai", "image") is True
    assert media_providers.supports("openai", "video") is False
    assert media_providers.supports("comfyui", "video") is True


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_local_comfyui_needs_no_credential():
    assert media_providers.is_configured("comfyui") is True
    assert media_providers.is_paid("comfyui") is False


def test_openai_is_configured_only_when_the_variable_is_set(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert media_providers.is_configured("openai") is False
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    assert media_providers.is_configured("openai") is True
    assert media_providers.is_paid("openai") is True


def test_whitespace_only_key_does_not_count_as_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    assert media_providers.is_configured("openai") is False


def test_catalogue_never_carries_a_key_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-appear")
    catalogue = media_providers.describe_catalogue()
    assert "sk-should-never-appear" not in repr(catalogue)
    openai = next(p for p in catalogue["providers"] if p["id"] == "openai")
    assert openai["configured"] is True
    assert openai["api_key_env"] == "OPENAI_API_KEY"
    assert openai["requires_confirmation"] is True
    assert catalogue["video_provider_id"] == "comfyui"


def test_catalogue_default_model_follows_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    openai = next(
        p for p in media_providers.describe_catalogue()["providers"]
        if p["id"] == "openai"
    )
    assert openai["default_model"] == "gpt-image-1"
    assert "gpt-image-1" in [m["id"] for m in openai["models"]]


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------

def test_local_generation_is_reported_as_unmetered_not_as_zero():
    estimate = media_providers.estimate_image_cost("comfyui", "workflow")
    assert estimate.amount_usd is None
    assert estimate.source == "free"
    assert "GPU time" in estimate.basis


def test_known_model_and_size_are_priced_from_the_table():
    estimate = media_providers.estimate_image_cost(
        "openai", "gpt-image-1-mini", "1024x1024", "medium"
    )
    assert estimate.source == "table"
    assert estimate.amount_usd == pytest.approx(0.011)
    assert "Estimate only" in estimate.basis


def test_cost_scales_with_the_number_of_images():
    one = media_providers.estimate_image_cost(
        "openai", "gpt-image-1-mini", "1024x1024", "medium", count=1
    )
    twelve = media_providers.estimate_image_cost(
        "openai", "gpt-image-1-mini", "1024x1024", "medium", count=12
    )
    assert twelve.amount_usd == pytest.approx((one.amount_usd or 0) * 12)


def test_unknown_rate_is_reported_as_unknown_not_as_free():
    """A model with no published rate must not be shown as costing nothing -
    it is still metered, and the user is the one who pays for the guess."""
    estimate = media_providers.estimate_image_cost(
        "openai", "some-future-model", "1024x1024", "medium"
    )
    assert estimate.amount_usd is None
    assert estimate.source == "unknown"
    assert "metered" in estimate.basis


def test_environment_override_wins_over_the_table(monkeypatch):
    monkeypatch.setenv("CAS_OPENAI_IMAGE_PRICE_USD", "0.25")
    estimate = media_providers.estimate_image_cost(
        "openai", "gpt-image-1-mini", "1024x1024", "medium", count=2
    )
    assert estimate.source == "env"
    assert estimate.amount_usd == pytest.approx(0.5)


def test_unparseable_override_falls_back_to_the_table(monkeypatch):
    monkeypatch.setenv("CAS_OPENAI_IMAGE_PRICE_USD", "free please")
    estimate = media_providers.estimate_image_cost(
        "openai", "gpt-image-1-mini", "1024x1024", "medium"
    )
    assert estimate.source == "table"


@pytest.mark.parametrize(
    "width,height,expected",
    [
        (1920, 1080, "1536x1024"),
        (1080, 1920, "1024x1536"),
        (1024, 1024, "1024x1024"),
        (0, 0, "1024x1024"),
        (None, None, "1024x1024"),
    ],
)
def test_size_is_mapped_onto_a_supported_aspect(width, height, expected):
    assert media_providers.normalise_size(width, height) == expected


# ---------------------------------------------------------------------------
# Adapter resolution
# ---------------------------------------------------------------------------

def test_comfyui_resolves_to_the_queue_manager_adapter():
    from app.services.queue_manager import queue_manager

    assert media_providers.get_provider("comfyui") is queue_manager.provider


def test_openai_adapter_is_reused_and_reset(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    first = media_providers.get_provider("openai")
    assert media_providers.get_provider("openai") is first
    media_providers.reset_provider_cache()
    assert media_providers.get_provider("openai") is not first


def test_unknown_provider_has_no_adapter():
    with pytest.raises(media_providers.UnknownMediaProviderError):
        media_providers.get_provider("midjourney")
