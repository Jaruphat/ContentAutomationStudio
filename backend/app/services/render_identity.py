"""Identify the exact bytes a human or agent scored, without trusting timestamps."""
import hashlib
from pathlib import Path

from app import paths


def render_path(project_id: str) -> Path:
    return Path(paths.exports_dir(project_id)) / "review.mp4"


def render_sha256(project_id: str) -> str:
    try:
        with render_path(project_id).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        return ""
