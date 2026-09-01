"""
Central filesystem path resolution for Content Automation Studio.

Every runtime directory is derived from a single base so that the database,
imported workflows, generated media and exports always live under the same
tree. Previously each module recomputed the backend directory on its own and
modules nested one level deeper (``app/services/*``) resolved to ``backend/app``
instead of ``backend``, splitting runtime data across two trees.

The base directory can be overridden with the ``CAS_DATA_DIR`` environment
variable, which is what the test suite uses to keep artifacts out of the
developer's working tree.

All paths are absolute and safe for Windows paths containing spaces and
Unicode characters.
"""

import os

# ``app/paths.py`` -> ``app`` -> ``backend``
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(APP_DIR)


def _resolve_data_dir() -> str:
    """Return the base runtime data directory, honouring CAS_DATA_DIR."""
    override = os.environ.get("CAS_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(BACKEND_DIR, "data")


def data_dir() -> str:
    """Base runtime data directory (created on demand)."""
    path = _resolve_data_dir()
    os.makedirs(path, exist_ok=True)
    return path


def db_path() -> str:
    """Absolute path to the SQLite database file."""
    return os.path.join(data_dir(), "cas.db")


def workflows_dir() -> str:
    """Directory holding imported ComfyUI workflow source JSON."""
    path = os.path.join(data_dir(), "workflows")
    os.makedirs(path, exist_ok=True)
    return path


def snapshots_dir() -> str:
    """Directory holding per-job workflow snapshots for reproducibility."""
    path = os.path.join(data_dir(), "snapshots")
    os.makedirs(path, exist_ok=True)
    return path


def generated_dir() -> str:
    """Directory holding generated media returned by a provider."""
    path = os.path.join(data_dir(), "generated")
    os.makedirs(path, exist_ok=True)
    return path


def exports_dir(project_id: str | None = None) -> str:
    """Directory holding rendered/exported output, optionally per project."""
    path = os.path.join(data_dir(), "exports")
    if project_id:
        path = os.path.join(path, project_id)
    os.makedirs(path, exist_ok=True)
    return path
