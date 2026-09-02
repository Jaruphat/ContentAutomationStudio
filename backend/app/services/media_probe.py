"""
Media probing via ffprobe.

Shared by the render service and by the real ComfyUI provider, which probes
every file it downloads so a take records what the media actually is rather
than what its filename suggests.

Every function degrades to an empty result when ffprobe is unavailable, so a
machine without FFmpeg loses metadata rather than failing.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

logger = logging.getLogger("cas.media_probe")

VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif")

#: Container tags a muxer writes about itself. Anything else in a delivered
#: file came from an upstream generator: ComfyUI's SaveVideo embeds the entire
#: prompt graph - node classes, local model filenames and the creative prompt -
#: as a ``prompt`` tag, and other nodes reuse ``comment``/``title`` for the
#: same payload. An allow-list is used rather than a list of known-bad keys so
#: a tag nobody anticipated is still reported.
STRUCTURAL_CONTAINER_TAGS = frozenset({
    "major_brand",
    "minor_version",
    "compatible_brands",
    "encoder",
    "handler_name",
    "language",
    "vendor_id",
    "creation_time",
})


def ffmpeg_path() -> str | None:
    """Absolute path to ffmpeg, or None when it is not installed."""
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    """Absolute path to ffprobe, or None when it is not installed."""
    return shutil.which("ffprobe")


def run_captured(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """
    Run a command, capturing stdout and stderr through temporary files.

    Pipes are deliberately avoided: ``capture_output=True`` spawns reader
    threads, and on Windows those threads make pytest's faulthandler report a
    spurious access violation on every FFmpeg call, which buries real failures
    in the test output. Redirecting to files needs no reader threads and has no
    pipe-buffer deadlock risk on verbose output.

    Returns (returncode, stdout, stderr). A returncode of -1 means the process
    could not be run at all.
    """
    with tempfile.TemporaryDirectory(prefix="cas-proc-") as tmp:
        out_path = os.path.join(tmp, "stdout")
        err_path = os.path.join(tmp, "stderr")
        try:
            with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
                proc = subprocess.run(
                    cmd, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL,
                    timeout=timeout,
                )
            returncode = proc.returncode
        except (subprocess.TimeoutExpired, OSError) as exc:
            return -1, "", str(exc)

        def _read(path: str) -> str:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    return f.read()
            except OSError:
                return ""

        return returncode, _read(out_path), _read(err_path)


def _parse_frame_rate(value: str | None) -> float:
    """ffprobe reports frame rate as a rational such as '24/1'."""
    if not value:
        return 0.0
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            denom = float(denominator)
            return float(numerator) / denom if denom else 0.0
        return float(value)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_media_file(file_path: str) -> dict[str, Any]:
    """
    Return what a media file actually contains.

    Keys: ``width``, ``height``, ``codec``, ``duration_sec``, ``frame_rate``,
    ``has_audio``, ``audio_codec``. Returns ``{}`` when the file is missing or
    ffprobe is unavailable - callers must treat that as "unknown", never as
    "zero".
    """
    ffprobe = ffprobe_path()
    if not ffprobe or not os.path.isfile(file_path):
        return {}

    cmd = [
        ffprobe, "-v", "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json", file_path,
    ]
    returncode, stdout, stderr = run_captured(cmd, timeout=30)
    if returncode != 0:
        logger.warning("ffprobe failed for %s: %s", file_path, stderr[-200:])
        return {}
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}

    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = (data.get("format") or {}).get("duration")

    result: dict[str, Any] = {
        "width": int((video or {}).get("width") or 0),
        "height": int((video or {}).get("height") or 0),
        "codec": (video or {}).get("codec_name") or "",
        "duration_sec": float(duration) if duration else 0.0,
        "frame_rate": _parse_frame_rate((video or {}).get("r_frame_rate")),
        "has_audio": audio is not None,
        "audio_codec": (audio or {}).get("codec_name") or "",
    }
    return result


def read_container_tags(file_path: str) -> dict[str, Any]:
    """
    Return a file's format-level and per-stream metadata tags.

    Shape: ``{"format": {...}, "streams": [{...}, ...]}``. Returns ``{}`` when
    the file is missing or ffprobe is unavailable - "unknown", never "none".
    """
    ffprobe = ffprobe_path()
    if not ffprobe or not os.path.isfile(file_path):
        return {}

    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format_tags",
        "-show_entries", "stream_tags",
        "-of", "json", file_path,
    ]
    returncode, stdout, stderr = run_captured(cmd, timeout=30)
    if returncode != 0:
        logger.warning("ffprobe tags failed for %s: %s", file_path, stderr[-200:])
        return {}
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}

    return {
        "format": dict((data.get("format") or {}).get("tags") or {}),
        "streams": [
            dict(stream.get("tags") or {}) for stream in (data.get("streams") or [])
        ],
    }


def embedded_metadata_keys(file_path: str) -> list[str]:
    """
    Tag keys in a file that did not come from the muxer.

    Only keys are returned, never values: the values are exactly the workflow
    graph and prompt text that must not leak, so they have no business in a log
    line or an API response. Provenance is kept in the sidecar instead.

    An empty list means either that the file is clean or that ffprobe could not
    read it; callers that need to distinguish those should check
    :func:`read_container_tags` for an empty result first.
    """
    tags = read_container_tags(file_path)
    if not tags:
        return []
    keys: set[str] = set()
    for scope in [tags.get("format") or {}] + list(tags.get("streams") or []):
        keys.update(
            key for key in scope
            if key.lower() not in STRUCTURAL_CONTAINER_TAGS
        )
    return sorted(keys)
