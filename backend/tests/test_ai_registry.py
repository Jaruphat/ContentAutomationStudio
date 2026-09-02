"""
Tests for AI provider selection, the catalogue and configuration blockers.

The behaviour under test is the promise the product makes about keys: the app
is fully usable with none, a configured key takes effect with no further setup,
and an explicitly requested provider is never silently swapped for the mock.
"""

import pytest

from app.services.ai import registry
from app.services.ai.base import AIProviderError
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.openai_provider import OpenAIProvider


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def test_default_is_mock_when_nothing_is_configured():
    """No key anywhere means the offline provider, not an error."""
    assert registry.default_provider_id() == "mock"


def test_default_is_openai_when_the_key_is_set(monkeypatch):
    """A configured key takes effect without any other configuration."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    assert registry.default_provider_id() == "openai"


def test_blank_key_does_not_count_as_configured(monkeypatch):
    """OPENAI_API_KEY= in a .env is 'unset', not 'set to empty'."""
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    assert registry.default_provider_id() == "mock"
    assert OpenAIProvider().is_configured() is False


def test_env_pin_overrides_auto_selection(monkeypatch):
    """An operator can pin the mock even with a key present."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("CAS_AI_PROVIDER", "mock")
    assert registry.default_provider_id() == "mock"


def test_env_pin_is_validated(monkeypatch):
    """A typo in the pin fails immediately, not later inside a task."""
    monkeypatch.setenv("CAS_AI_PROVIDER", "opeai")
    with pytest.raises(AIProviderError) as excinfo:
        registry.default_provider_id()
    assert excinfo.value.category == "bad_request"


def test_create_provider_honours_an_explicit_id(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    provider = registry.create_provider("mock")
    assert isinstance(provider, MockAIProvider)


def test_create_provider_auto_selects_when_id_is_blank():
    assert isinstance(registry.create_provider(""), MockAIProvider)


def test_create_provider_applies_the_requested_model():
    provider = registry.create_provider("openai", "gpt-4o-mini")
    assert provider.model == "gpt-4o-mini"


def test_create_provider_falls_back_to_the_default_model():
    provider = registry.create_provider("openai", "")
    assert provider.model == OpenAIProvider.default_model


def test_unknown_provider_is_rejected():
    with pytest.raises(AIProviderError) as excinfo:
        registry.create_provider("anthropic")
    assert excinfo.value.category == "bad_request"
    # The message must list what is available, so the caller can correct it.
    assert "mock" in str(excinfo.value)


def test_requesting_openai_without_a_key_is_not_downgraded_to_mock():
    """The critical anti-surprise: no silent substitution.

    Quietly returning mock output for a requested model would put unlabelled
    placeholder text into a user's storyboard.
    """
    provider = registry.create_provider("openai")
    assert isinstance(provider, OpenAIProvider)
    with pytest.raises(AIProviderError) as excinfo:
        provider.require_configured()
    assert excinfo.value.category == "not_configured"
    assert "OPENAI_API_KEY" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def test_catalogue_lists_every_provider():
    catalogue = registry.describe_catalogue()
    ids = [p["id"] for p in catalogue["providers"]]
    assert ids == registry.provider_ids()
    assert set(ids) == {"mock", "openai"}


def test_catalogue_reports_the_default():
    assert registry.describe_catalogue()["default_provider_id"] == "mock"


def test_catalogue_marks_the_mock_as_mock_and_offline():
    catalogue = registry.describe_catalogue()
    mock = next(p for p in catalogue["providers"] if p["id"] == "mock")
    assert mock["mock"] is True
    assert mock["configured"] is True
    assert mock["requires_network"] is False
    assert mock["requires_key"] is False


def test_catalogue_names_the_key_variable_but_never_a_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-do-not-leak")
    catalogue = registry.describe_catalogue()
    openai = next(p for p in catalogue["providers"] if p["id"] == "openai")

    assert openai["api_key_env"] == "OPENAI_API_KEY"
    assert openai["configured"] is True
    assert "sk-secret-value-do-not-leak" not in str(catalogue)


def test_catalogue_offers_models_for_each_provider():
    catalogue = registry.describe_catalogue()
    for provider in catalogue["providers"]:
        assert provider["models"], f"{provider['id']} offers no models"
        assert provider["default_model"] in [m["id"] for m in provider["models"]]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_covers_every_provider():
    healths = await registry.check_health()
    assert {h.provider_id for h in healths} == {"mock", "openai"}


@pytest.mark.asyncio
async def test_health_can_target_one_provider():
    healths = await registry.check_health("mock")
    assert len(healths) == 1
    assert healths[0].provider_id == "mock"
    assert healths[0].online is True
    assert healths[0].mock is True


@pytest.mark.asyncio
async def test_unconfigured_openai_health_is_reported_not_raised():
    """An unconfigured provider is a result, not an exception.

    It also must not touch the network: the check short-circuits on the
    missing key.
    """
    healths = await registry.check_health("openai")
    assert healths[0].configured is False
    assert healths[0].online is False
    assert "OPENAI_API_KEY" in healths[0].error


# ---------------------------------------------------------------------------
# Blockers
# ---------------------------------------------------------------------------

def test_missing_key_is_reported_as_a_blocker():
    blockers = registry.configuration_blockers()
    assert len(blockers) == 1
    assert "OPENAI_API_KEY" in blockers[0]
    # The blocker must say what happens instead, not just what is missing.
    assert "mock" in blockers[0].lower()


def test_no_blocker_once_the_key_is_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    assert registry.configuration_blockers() == []


def test_the_mock_is_never_a_blocker():
    """The offline provider always works, so it never blocks anything."""
    assert all("mock" != b for b in registry.configuration_blockers())
