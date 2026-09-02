"""
Render Service.

Executes the Timeline Manifest with FFmpeg to produce a review video, and
probes media with ffprobe.

Follows PRD section 13.3: each timeline item is normalised to the project's
resolution and frame rate as its own intermediate (stills held for the shot
duration, video trimmed), then the intermediates are concatenated.

Audio is preserved when any approved take carries it - MiniMax H3 emits video
with a native stereo track. The concat demuxer stream-copies the
intermediates, so they must all share one stream layout: when the timeline
carries audio anywhere, every segment gets an AAC stereo track and the ones
with no source audio (stills, silent clips) get silence synthesised. When
nothing on the timeline has audio, the render stays video-only rather than
padding a silent track onto it.

Rendering is skipped - with an explicit reason, never a fabricated result -
when FFmpeg is unavailable, the timeline is empty, or any referenced media file
is missing. A failed render never touches approved takes or project state
(NFR-09); it only writes under the project's export directory.
"""

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import Project, Take
# ffmpeg_path/ffprobe_path are re-exported: callers and tests treat this
# module as the render entry point and ask it whether FFmpeg is available.
from app.services.media_probe import (  # noqa: F401
    VIDEO_EXTENSIONS,
    ffmpeg_path,
    ffprobe_path,
    probe_media_file,
    run_captured,
)
from app.services.timeline_service import get_timeline_manifest

logger = logging.getLogger("cas.render_service")

#: Every segment that carries audio is normalised to this layout so the concat
#: demuxer can stream-copy them into one file.
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_BITRATE = "192k"


def parse_resolution(value: str) -> tuple[int, int]:
    """Parse a 'WIDTHxHEIGHT' string, falling back to 1920x1080."""
    try:
        width_str, height_str = str(value).lower().split("x", 1)
        width, height = int(width_str), int(height_str)
    except (ValueError, AttributeError):
        return 1920, 1080
    # H.264 requires even dimensions.
    return max(2, width - (width % 2)), max(2, height - (height % 2))


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run a command; return (ok, tail of stderr)."""
    returncode, _stdout, stderr = run_captured(cmd, timeout=timeout)
    if returncode != 0:
        return False, (stderr or "")[-800:]
    return True, ""


def probe_media(file_path: str) -> dict[str, Any]:
    """Return width/height/duration/codec for a media file, or {} if unknown."""
    return probe_media_file(file_path)


def _source_has_audio(file_path: str) -> bool | None:
    """Whether a source file carries audio, or None when it cannot be probed.

    None is not False: without ffprobe the render must say it could not tell
    rather than silently claim the media had no audio.
    """
    probe = probe_media_file(file_path)
    if not probe:
        return None
    return bool(probe.get("has_audio"))


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
        "has_audio": False,
        "audio_codec": "",
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

    # Decide once whether this render carries audio at all: the segments have
    # to agree, because the concat step stream-copies them.
    source_audio = [_source_has_audio(take.file_path) for _item, take in sources]
    if any(flag is None for flag in source_audio):
        warnings.append(
            "ffprobe is unavailable, so source audio could not be detected. "
            "The review video was rendered without audio."
        )
        source_audio = [False] * len(source_audio)
    keep_audio = any(source_audio)

    segment_paths: list[str] = []
    for index, (item, take) in enumerate(sources):
        duration = float(item.get("duration_sec") or 0.0) or 3.0
        segment = os.path.join(segments_dir, f"seg_{index:04d}.mp4")
        is_video = (take.file_path or "").lower().endswith(VIDEO_EXTENSIONS)
        # A still or a silent clip on an otherwise-audible timeline needs a
        # synthesised silent track to match the other segments.
        needs_silence = keep_audio and not source_audio[index]

        cmd = [ffmpeg, "-y", "-loglevel", "error"]
        if not is_video:
            # Hold the still for the shot's duration.
            cmd += ["-loop", "1"]
        cmd += ["-i", take.file_path]
        if needs_silence:
            cmd += [
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:"
                      f"sample_rate={AUDIO_SAMPLE_RATE}",
            ]
        cmd += ["-map", "0:v:0"]
        if keep_audio:
            cmd += ["-map", "1:a:0"] if needs_silence else ["-map", "0:a:0"]
        cmd += [
            "-t", f"{duration:g}",
            "-r", f"{frame_rate:g}",
            "-vf", scale_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]
        if keep_audio:
            cmd += [
                "-c:a", "aac",
                "-ar", str(AUDIO_SAMPLE_RATE),
                "-ac", str(AUDIO_CHANNELS),
                "-b:a", AUDIO_BITRATE,
            ]
            if needs_silence:
                # anullsrc never ends; without this a clip shorter than its
                # timeline slot would be padded with audio-only frames.
                cmd += ["-shortest"]
        else:
            cmd += ["-an"]
        cmd.append(segment)

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
    if keep_audio and probe and not probe.get("has_audio"):
        # The sources had audio but the assembled file does not - report it
        # rather than let a silent review video pass as correct.
        warnings.append(
            "Source takes carry audio but the assembled review video has no "
            "audio stream."
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
        "has_audio": bool(probe.get("has_audio")) if probe else keep_audio,
        "audio_codec": probe.get("audio_codec", "aac" if keep_audio else ""),
    }
