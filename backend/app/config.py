"""
Environment configuration loading.

The application reads every secret from the process environment. A ``.env``
file at the repository root is a convenience for local development: it is read
once at startup and only fills in variables that are not already set, so an
explicitly exported value always wins over the file.

Nothing here ever logs a value. The loader reports which *names* it supplied,
which is enough to debug a missing key without printing one.

``CAS_DISABLE_DOTENV=1`` skips the file entirely. The test suite sets it so a
developer's real ``.env`` - and the real ``OPENAI_API_KEY`` in it - cannot leak
into a test run and turn a mock-provider assertion into a billed API call.
"""

import logging
import os

logger = logging.getLogger("cas.config")

# ``app/config.py`` -> ``app`` -> ``backend`` -> repository root.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_APP_DIR)
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)

#: Searched in order; the first file found is used. The backend directory is
#: included so a backend-only checkout still works.
ENV_FILE_CANDIDATES = (
    os.path.join(_REPO_ROOT, ".env"),
    os.path.join(_BACKEND_DIR, ".env"),
)


def dotenv_disabled() -> bool:
    return os.environ.get("CAS_DISABLE_DOTENV", "").strip().lower() in (
        "1", "true", "yes",
    )


def load_env_file() -> tuple[str, list[str]]:
    """Load the first ``.env`` found, without overriding the real environment.

    Returns ``(path_used, names_supplied)``. ``path_used`` is empty when no
    file was read, which is the normal case in CI and in the test suite.
    """
    if dotenv_disabled():
        return "", []

    path = next((p for p in ENV_FILE_CANDIDATES if os.path.isfile(p)), "")
    if not path:
        return "", []

    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - dependency is pinned
        logger.warning("python-dotenv is not installed; %s was not read", path)
        return "", []

    supplied: list[str] = []
    # override=False by hand rather than load_dotenv(override=False): this way
    # the names actually applied can be reported, and a key already exported in
    # the shell is never quietly replaced by a stale file.
    for name, value in dotenv_values(path, encoding="utf-8").items():
        if value is None or name in os.environ:
            continue
        os.environ[name] = value
        supplied.append(name)

    if supplied:
        # Names only. Never the values.
        logger.info(
            "Loaded %d variable(s) from %s: %s",
            len(supplied), path, ", ".join(sorted(supplied)),
        )
    return path, supplied
