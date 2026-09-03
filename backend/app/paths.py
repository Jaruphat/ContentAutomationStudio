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


def is_within_data_dir(file_path: str) -> bool:
    """Whether a stored path really lives inside the runtime data directory.

    A database row could in principle hold any absolute path - a re-imported
    project, a hand-edited database - so this is what stands between a stored
    string and an arbitrary file read. The comparison is done on the resolved
    real paths so a symlink cannot step outside, and ``commonpath`` raising on
    differing Windows drive letters is itself proof the target is outside.
    """
    if not file_path:
        return False
    base = os.path.realpath(data_dir())
    target = os.path.realpath(file_path)
    try:
        return os.path.commonpath([base, target]) == base
    except ValueError:
        return False


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


def references_dir(project_id: str) -> str:
    """Directory holding a project's Visual Reference Bible images.

    Per project rather than shared: an image is owned by exactly one project,
    and keeping the trees separate means a path check can also serve as an
    ownership check.

    Project ids are server-generated UUIDs, so a separator here would mean a
    caller passed something else entirely; that is refused rather than
    sanitised, because quietly rewriting it would hide the bug.
    """
    path = references_root(project_id)
    os.makedirs(path, exist_ok=True)
    return path


def references_root(project_id: str) -> str:
    """The reference directory's path without creating it.

    Used by deletion, which wants to remove the tree rather than make one.
    """
    if not project_id or {"/", "\\"} & set(project_id) or project_id in (".", ".."):
        raise ValueError(f"Refusing to build a reference directory for {project_id!r}")
    return os.path.join(data_dir(), "references", project_id)


def exports_dir(project_id: str | None = None) -> str:
    """Directory holding rendered/exported output, optionally per project."""
    path = os.path.join(data_dir(), "exports")
    if project_id:
        path = os.path.join(path, project_id)
    os.makedirs(path, exist_ok=True)
    return path
