"""
Render Service.

Executes the Timeline Manifest with FFmpeg to produce a review video, and
probes media with ffprobe.

Follows PRD section 13.3: each timeline item is normalised to the project's
resolution and frame rate as its own intermediate (stills held for the shot
duration, video trimmed), then the intermediates are concatenated.

Rendering is skipped - with an explicit reason, never a fabricated result -
when FFmpeg is unavailable, the timeline is empty, or any referenced media file
is missing. A failed render never touches approved takes or project state
(NFR-09); it only writes under the project's export directory.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import Project, Take
from app.services.timeline_service import get_timeline_manifest

logger = logging.getLogger("cas.render_service")

VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif")


def ffmpeg_path() -> str | None:
    """Absolute path to ffmpeg, or None when it is not installed."""
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    """Absolute path to ffprobe, or None when it is not installed."""
    return shutil.which("ffprobe")


def parse_resolution(value: str) -> tuple[int, int]:
    """Parse a 'WIDTHxHEIGHT' string, falling back to 1920x1080."""
    try:
        width_str, height_str = str(value).lower().split("x", 1)
        width, height = int(width_str), int(height_str)
    except (ValueError, AttributeError):
        return 1920, 1080
    # H.264 requires even dimensions.
    return max(2, width - (width % 2)), max(2, height - (height % 2))


def run_captured(
    cmd: list[str], timeout: int = 300
) -> tuple[int, str, str]:
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


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run a command; return (ok, tail of stderr)."""
    returncode, _stdout, stderr = run_captured(cmd, timeout=timeout)
    if returncode != 0:
        return False, (stderr or "")[-800:]
    return True, ""


def probe_media(file_path: str) -> dict[str, Any]:
    """Return width/height/duration/codec for a media file, or {} if unknown."""
    ffprobe = ffprobe_path()
    if not ffprobe or not os.path.isfile(file_path):
        return {}

    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name",
        "-show_entries", "format=duration",
        "-of", "json", file_path,
    ]
    returncode, stdout, _stderr = run_captured(cmd, timeout=30)
    if returncode != 0:
        return {}
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}

    streams = data.get("streams") or [{}]
    stream = streams[0]
    duration = (data.get("format") or {}).get("duration")
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "codec": stream.get("codec_name") or "",
        "duration_sec": float(duration) if duration else 0.0,
    }


def _blocked(project_id: str, reason: str) -> dict[str, Any]:
    """Uniform 'the render did not run' result."""
    return {
        "project_id": project_id,
        "rendered": False,
        "output_path": "",
        "reason": reason,
        "warnings": [],
        "segment_count": 0,
        "width": 0,
        "height": 0,
        "duration_sec": 0.0,
        "codec": "",
        "size_bytes": 0,
    }


def render_review_video(db: Session, project_id: str) -> dict[str, Any]:
    """Assemble the approved takes on the timeline into a review MP4."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project not found: {project_id}")

    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return _blocked(
            project_id,
            "FFmpeg is not installed or not on PATH, so no review video can be "
            "produced. The render plan endpoint still returns the commands.",
        )

    manifest = get_timeline_manifest(db, project_id)
    items = manifest.get("items", [])
    if not items:
        return _blocked(
            project_id,
            "Timeline is empty. Build the timeline from approved takes first.",
        )

    # Resolve every source up front so a missing asset stops the render before
    # any work is done rather than half way through.
    sources: list[tuple[dict[str, Any], Take]] = []
    for item in items:
        take = db.query(Take).filter(Take.id == item.get("take_id")).first()
        if take is None:
            return _blocked(
                project_id,
                f"Timeline position {item['order']} references a take that no "
                f"longer exists ({item.get('take_id')}).",
            )
        if take.review_status != "Approved":
            return _blocked(
                project_id,
                f"Timeline position {item['order']} uses take {take.id} with "
                f"status '{take.review_status}'. Only approved takes may be rendered.",
            )
        if not take.file_path or not os.path.isfile(take.file_path):
            return _blocked(
                project_id,
                f"Timeline position {item['order']}: media file is missing "
                f"({take.file_path or 'no path recorded'}).",
            )
        sources.append((item, take))

    width, height = parse_resolution(project.target_resolution)
    frame_rate = project.frame_rate or 24.0
    warnings: list[str] = []

    out_dir = paths.exports_dir(project_id)
    segments_dir = os.path.join(out_dir, "segments")
    os.makedirs(segments_dir, exist_ok=True)

    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )

    segment_paths: list[str] = []
    for index, (item, take) in enumerate(sources):
        duration = float(item.get("duration_sec") or 0.0) or 3.0
        segment = os.path.join(segments_dir, f"seg_{index:04d}.mp4")
        is_video = (take.file_path or "").lower().endswith(VIDEO_EXTENSIONS)

        cmd = [ffmpeg, "-y", "-loglevel", "error"]
        if not is_video:
            # Hold the still for the shot's duration.
            cmd += ["-loop", "1"]
        cmd += [
            "-i", take.file_path,
            "-t", f"{duration:g}",
            "-r", f"{frame_rate:g}",
            "-vf", scale_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-an",
            segment,
        ]

        ok, err = _run(cmd)
        if not ok:
            return _blocked(
                project_id,
                f"FFmpeg failed while normalising timeline position "
                f"{item['order']}: {err}",
            )
        segment_paths.append(segment)

    # Concatenate the normalised segments. They now share codec, resolution and
    # frame rate, so a stream copy is safe.
    concat_file = os.path.join(out_dir, "concat_list.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            # The concat demuxer treats the path as a quoted token.
            escaped = seg.replace("\\", "/").replace("'", "'\\''")
            f.write("file '" + escaped + "'\n")

    output_path = os.path.join(out_dir, "review.mp4")
    ok, err = _run([
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-c", "copy", output_path,
    ])
    if not ok:
        return _blocked(project_id, f"FFmpeg concat failed: {err}")

    probe = probe_media(output_path)
    expected = float(manifest.get("total_duration_sec") or 0.0)
    actual = probe.get("duration_sec", 0.0)
    if probe and expected and abs(actual - expected) > 1.0:
        warnings.append(
            f"Rendered duration {actual:.2f}s differs from the manifest total "
            f"{expected:.2f}s by more than one second."
        )

    logger.info(
        "Rendered review video for project %s: %s (%d segments)",
        project_id, output_path, len(segment_paths),
    )

    return {
        "project_id": project_id,
        "rendered": True,
        "output_path": output_path,
        "reason": "",
        "warnings": warnings,
        "segment_count": len(segment_paths),
        "width": probe.get("width", width),
        "height": probe.get("height", height),
        "duration_sec": actual or expected,
        "codec": probe.get("codec", "h264"),
        "size_bytes": os.path.getsize(output_path),
    }
