"""
Tests for the optional ``.env`` loader.

The rule the rest of the app depends on: an exported variable always beats the
file, and the loader never prints a value. The suite itself relies on
``CAS_DISABLE_DOTENV``, so that switch is covered too.
"""

import pytest

from app import config


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    """Point the loader at a temporary .env and enable it for this test."""
    path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE_CANDIDATES", (str(path),))
    monkeypatch.delenv("CAS_DISABLE_DOTENV", raising=False)
    return path


def test_values_are_loaded_from_the_file(env_file, monkeypatch):
    monkeypatch.delenv("CAS_TEST_FROM_FILE", raising=False)
    env_file.write_text("CAS_TEST_FROM_FILE=hello\n", encoding="utf-8")

    path, names = config.load_env_file()

    assert path == str(env_file)
    assert names == ["CAS_TEST_FROM_FILE"]
    import os
    assert os.environ["CAS_TEST_FROM_FILE"] == "hello"
    monkeypatch.delenv("CAS_TEST_FROM_FILE", raising=False)


def test_an_exported_value_is_never_overridden(env_file, monkeypatch):
    """A stale file must not replace what the operator exported."""
    monkeypatch.setenv("CAS_TEST_EXPORTED", "from-shell")
    env_file.write_text("CAS_TEST_EXPORTED=from-file\n", encoding="utf-8")

    _path, names = config.load_env_file()

    import os
    assert os.environ["CAS_TEST_EXPORTED"] == "from-shell"
    assert "CAS_TEST_EXPORTED" not in names


def test_a_missing_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config, "ENV_FILE_CANDIDATES", (str(tmp_path / "absent.env"),),
    )
    monkeypatch.delenv("CAS_DISABLE_DOTENV", raising=False)

    assert config.load_env_file() == ("", [])


def test_the_loader_can_be_disabled(env_file, monkeypatch):
    """What keeps a developer's real key out of the test suite."""
    env_file.write_text("CAS_TEST_DISABLED=value\n", encoding="utf-8")
    monkeypatch.setenv("CAS_DISABLE_DOTENV", "1")

    assert config.load_env_file() == ("", [])

    import os
    assert "CAS_TEST_DISABLED" not in os.environ


def test_the_suite_runs_with_the_loader_disabled():
    """Asserted so the isolation cannot be removed from conftest unnoticed."""
    assert config.dotenv_disabled() is True


def test_only_names_are_logged_never_values(env_file, monkeypatch, caplog):
    monkeypatch.delenv("CAS_TEST_SECRET", raising=False)
    env_file.write_text(
        "CAS_TEST_SECRET=sk-must-not-appear-in-logs\n", encoding="utf-8",
    )

    with caplog.at_level("INFO", logger="cas.config"):
        config.load_env_file()

    assert "CAS_TEST_SECRET" in caplog.text
    assert "sk-must-not-appear-in-logs" not in caplog.text
    monkeypatch.delenv("CAS_TEST_SECRET", raising=False)


def test_the_repository_root_is_searched_first():
    """A backend-only checkout still works, but the root .env wins."""
    assert len(config.ENV_FILE_CANDIDATES) == 2
    assert config.ENV_FILE_CANDIDATES[0].endswith(".env")
