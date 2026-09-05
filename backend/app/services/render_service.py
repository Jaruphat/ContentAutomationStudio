"""
Render Service.

Executes the Timeline Manifest with FFmpeg to produce a review video, and
probes media with ffprobe.

Follows PRD section 13.3: each timeline item is normalised to the project's
resolution and frame rate as its own intermediate (stills held for the shot
duration, video trimmed), then the intermediates are concatenated.

Audio is preserved when any approved take carries it - MiniMax H3 emits video
with a native stereo track. The concat demuxer requires the intermediates to
share one stream layout: when the timeline carries audio anywhere, every
segment gets an AAC stereo track and the ones with no source audio (stills,
silent clips) get silence synthesised. The assembled program is then loudness
normalised while its video is stream-copied. When nothing on the timeline has
audio, the render stays video-only rather than padding a silent track onto it.

The delivered MP4 carries no inherited container metadata. ComfyUI's SaveVideo
embeds the whole prompt graph - creative prompt text, node classes and local
model filenames - in the file it writes, and FFmpeg copies input metadata to
the output by default, so both the per-segment normalisation and the concat
step pass ``-map_metadata -1 -map_chapters -1``. The same provenance is written
alongside the video as ``review.provenance.json``: kept, auditable and
inspectable, but not shipped inside the deliverable.

Rendering is skipped - with an explicit reason, never a fabricated result -
when FFmpeg is unavailable, the timeline is empty, or any referenced media file
is missing. A failed render never touches approved takes or project state
(NFR-09); it only writes under the project's export directory.
"""

import hashlib
import json
import logging
import math
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import GenerationJob, Project, Scene, Shot, Take, Workflow
# ffmpeg_path/ffprobe_path are re-exported: callers and tests treat this
# module as the render entry point and ask it whether FFmpeg is available.
from app.services.media_probe import (  # noqa: F401
    VIDEO_EXTENSIONS,
    embedded_metadata_keys,
    embedded_metadata_keys_from_tags,
    ffmpeg_path,
    ffprobe_path,
    probe_media_file,
    read_container_tags,
    run_captured,
)
from app.services.timeline_service import aspect_override_warnings, get_timeline_manifest
from app.services import generation_planning, narration, subtitle_service

logger = logging.getLogger("cas.render_service")

#: How far the takes' own audio is pushed down under the narration. Enough for
#: a voice to sit clearly on top, not so far that the scene goes silent behind
#: it - the room tone is part of what the video model produced.
NARRATION_DUCK_DB = -11.0

#: Where a music bed sits under the programme by default. A bed mixed at
#: parity is a duet with the film, not a bed.
MUSIC_GAIN_DB = -18.0

#: How much further the bed drops once a voice is over it. Music at reading
#: level under narration is the commonest way a review cut becomes
#: unwatchable.
MUSIC_NARRATION_DUCK_DB = -8.0

#: A shot whose own audio is not used. The clip still plays; it is silent.
AUDIO_MODE_MUTE = "mute"

#: Every segment that carries audio is normalised to this layout so the concat
#: demuxer can stream-copy them into one file.
AUDIO_SAMPLE_RATE = 48000
AUDIO_CHANNELS = 2
AUDIO_BITRATE = "192k"
AUDIO_TARGET_LUFS = -16.0
AUDIO_TRUE_PEAK_DBTP = -1.5
AUDIO_LOUDNESS_RANGE = 11.0
AUDIO_LIMIT_LINEAR = 0.79

#: Drop every tag and chapter the input carried. Applied to each segment and
#: again to the concat output, because either stage would otherwise inherit
#: the generator's embedded workflow graph.
STRIP_METADATA_ARGS = ["-map_metadata", "-1", "-map_chapters", "-1"]

#: Filename of the provenance record written next to the review video.
PROVENANCE_FILENAME = "review.provenance.json"


def parse_resolution(value: str) -> tuple[int, int]:
    """Compatibility wrapper around the canonical project parser."""
    return generation_planning.parse_resolution(value)


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run a command; return (ok, tail of stderr)."""
    returncode, _stdout, stderr = run_captured(cmd, timeout=timeout)
    if returncode != 0:
        return False, (stderr or "")[-800:]
    return True, ""


def _measure_loudness(ffmpeg: str, file_path: str) -> dict[str, float] | None:
    """Measure EBU R128 integrated loudness and true peak."""
    returncode, _stdout, stderr = run_captured([
        ffmpeg, "-hide_banner", "-nostats", "-i", file_path,
        "-af",
        f"loudnorm=I={AUDIO_TARGET_LUFS:g}:TP={AUDIO_TRUE_PEAK_DBTP:g}:"
        f"LRA={AUDIO_LOUDNESS_RANGE:g}:print_format=json",
        "-f", "null", "-",
    ], timeout=300)
    if returncode != 0:
        return None
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(stderr[start:end + 1])
        measured = {
            "integrated_lufs": float(payload["input_i"]),
            "true_peak_dbtp": float(payload["input_tp"]),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return measured if all(math.isfinite(value) for value in measured.values()) else None


def probe_media(file_path: str) -> dict[str, Any]:
    """Return width/height/duration/codec for a media file, or {} if unknown."""
    return probe_media_file(file_path)


def _shot_audio_direction(
    db: Session, sources: list[tuple[dict[str, Any], "Take"]]
) -> list[tuple[bool, float]]:
    """``(muted, gain_db)`` per timeline position, in render order.

    Read once for the whole render rather than per segment, so the report of
    what was done is built from the same values the segments were made with
    instead of a second read of rows that may have moved in between.
    """
    shot_ids = [take.shot_id for _item, take in sources]
    shots = {
        shot.id: shot
        for shot in db.query(Shot).filter(Shot.id.in_(shot_ids)).all()
    } if shot_ids else {}
    plan: list[tuple[bool, float]] = []
    for shot_id in shot_ids:
        shot = shots.get(shot_id)
        mode = (getattr(shot, "audio_mode", "") or "native").lower()
        gain = float(getattr(shot, "audio_gain_db", 0.0) or 0.0)
        plan.append((mode == AUDIO_MODE_MUTE, gain))
    return plan


def _source_has_audio(file_path: str) -> bool | None:
    """Whether a source file carries audio, or None when it cannot be probed.

    None is not False: without ffprobe the render must say it could not tell
    rather than silently claim the media had no audio.
    """
    probe = probe_media_file(file_path)
    if not probe:
        return None
    return bool(probe.get("has_audio"))


def _blocked(
    project_id: str,
    reason: str,
    *,
    metadata_status: str = "unverified",
    leaked_metadata_keys: list[str] | None = None,
) -> dict[str, Any]:
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
        "audio_direction": {
            "muted_shots": [],
            "adjusted_shots": {},
            "music": {"present": False, "gain_db": 0.0,
                      "ducked_under_narration": False, "path": ""},
        },
        "provenance_path": "",
        "embedded_metadata_keys": leaked_metadata_keys or [],
        "metadata_status": metadata_status,
        "warning_metadata": [],
        # Nothing was produced, so neither claim can be made.
        "delivery_validation": {
            "pipeline_pass": False,
            "delivery_spec_pass": False,
        },
    }


def _discard_delivery(path: str) -> None:
    """Delete a rejected output, or quarantine it if deletion is unavailable."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        try:
            os.replace(path, f"{path}.quarantined")
        except OSError:
            logger.exception("Could not delete or quarantine rejected render %s", path)


def _sha256(file_path: str) -> str:
    """SHA-256 of a file, or '' when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _segment_provenance(
    db: Session, index: int, item: dict[str, Any], take: Take
) -> dict[str, Any]:
    """Everything needed to trace one delivered segment back to its origin."""
    shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    scene = (
        db.query(Scene).filter(Scene.id == shot.scene_id).first()
        if shot is not None else None
    )
    job = (
        db.query(GenerationJob).filter(GenerationJob.id == take.job_id).first()
        if take.job_id else None
    )
    workflow = (
        db.query(Workflow).filter(Workflow.id == job.workflow_id).first()
        if job is not None and job.workflow_id else None
    )

    record: dict[str, Any] = {
        "segment_index": index,
        "timeline_order": item.get("order"),
        "duration_sec": item.get("duration_sec"),
        "take": {
            "id": take.id,
            "source_path": take.file_path,
            "source_sha256": _sha256(take.file_path),
            "probe": probe_media_file(take.file_path),
            # What the source file carried before the render stripped it.
            "embedded_metadata_keys": embedded_metadata_keys(take.file_path),
            "lineage": take.lineage or {},
        },
    }
    if scene is not None:
        record["scene"] = {
            "id": scene.id, "order": scene.order, "title": scene.title,
        }
    if shot is not None:
        record["shot"] = {
            "id": shot.id,
            "order": shot.order,
            "generation_mode": shot.generation_mode,
            "image_prompt": shot.image_prompt,
            "video_prompt": shot.video_prompt,
            "negative_prompt": shot.negative_prompt,
        }
    if job is not None:
        record["job"] = {
            "id": job.id,
            "seed": job.seed,
            "comfyui_prompt_id": job.comfyui_prompt_id,
            "attempts": job.attempts,
            "workflow_snapshot_path": job.workflow_snapshot_path,
            "workflow_sha256": job.workflow_sha256,
        }
    if workflow is not None:
        record["workflow"] = {
            "id": workflow.id,
            "name": workflow.name,
            "purpose": workflow.purpose,
            "version": workflow.version,
            "source_format": workflow.source_format,
            "sha256_hash": workflow.sha256_hash,
        }
    return record


def write_render_provenance(
    db: Session,
    project: Project,
    sources: list[tuple[dict[str, Any], Take]],
    output_path: str,
    render_settings: dict[str, Any],
    container_tags: dict[str, Any] | None = None,
) -> str:
    """
    Write the sidecar recording what went into the review video.

    The deliverable itself is stripped of container metadata, so this file is
    the record: which take, job, workflow snapshot, seed and prompt produced
    each segment. It sits next to the video under the project's export
    directory and is never muxed into it.

    Returns the sidecar path, or '' when it could not be written - a provenance
    failure must not fail an otherwise good render.
    """
    output_probe = probe_media_file(output_path)
    output_width = int(output_probe.get("width") or render_settings.get("width") or 0)
    output_height = int(
        output_probe.get("height") or render_settings.get("height") or 0
    )
    divisor = math.gcd(output_width, output_height)
    output_aspect_ratio = (
        f"{output_width // divisor}:{output_height // divisor}"
        if divisor else project.aspect_ratio
    )
    override_warnings = aspect_override_warnings(
        db, project, [take for _item, take in sources]
    )

    payload = {
        "kind": "cas.review_render.provenance",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "id": project.id,
            "title": project.title,
            "target_resolution": project.target_resolution,
            "frame_rate": project.frame_rate,
            "aspect_ratio": output_aspect_ratio,
        },
        "output": {
            "path": output_path,
            "filename": os.path.basename(output_path),
            "sha256": _sha256(output_path),
            "size_bytes": (
                os.path.getsize(output_path) if os.path.isfile(output_path) else 0
            ),
            "probe": output_probe,
            "container_tags": (
                container_tags
                if container_tags is not None
                else read_container_tags(output_path)
            ),
        },
        "render_settings": render_settings,
        "warnings": override_warnings,
        "delivery_validation": {
            "pipeline_pass": True,
            "delivery_spec_pass": not override_warnings,
        },
        "segments": [
            _segment_provenance(db, index, item, take)
            for index, (item, take) in enumerate(sources)
        ],
        "note": (
            "Container metadata is stripped from the delivered MP4 so the "
            "generator's embedded workflow graph, model filenames and prompt "
            "text are not shipped inside it. This sidecar is the provenance "
            "record."
        ),
    }

    sidecar = os.path.join(os.path.dirname(output_path), PROVENANCE_FILENAME)
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{PROVENANCE_FILENAME}.",
            suffix=".tmp",
            dir=os.path.dirname(sidecar),
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, sidecar)
    except OSError as exc:
        logger.warning("Could not write render provenance to %s: %s", sidecar, exc)
        return ""
    finally:
        if temporary:
            try:
                os.remove(temporary)
            except OSError:
                pass
    return sidecar


def render_review_video(
    db: Session, project_id: str, *, narrate: bool = False, voice: Any = None
) -> dict[str, Any]:
    """Assemble the approved takes on the timeline into a review MP4.

    With ``narrate`` set, the shots' dialogue is spoken and mixed over the
    takes' own audio, so a narrated short comes out of the app complete rather
    than needing a voice muxed onto it afterwards. ``voice`` overrides the
    platform speech engine, which is how this is tested without one.
    """
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

    manifest = get_timeline_manifest(db, project_id, strict_lineage=True)
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

    # A waiver that only reaches the sidecar leaves whoever is looking at the
    # render result believing the delivery passed. It is repeated here, scoped
    # to the takes this render actually assembles.
    override_warnings = aspect_override_warnings(
        db, project, [take for _item, take in sources]
    )
    warnings: list[str] = [warning["message"] for warning in override_warnings]

    out_dir = paths.exports_dir(project_id)
    segments_dir = os.path.join(out_dir, "segments")
    try:
        os.makedirs(segments_dir, exist_ok=True)
    except OSError as exc:
        return _blocked(
            project_id,
            f"Could not prepare the render directory: {exc}",
        )

    subtitle_settings = subtitle_service.settings_for_project(project)
    subtitle_record: dict[str, Any] = {
        "settings": subtitle_settings.model_dump(),
        "cue_count": 0,
        "ass_sidecar": {"path": "", "sha256": ""},
        "srt_sidecar": {"path": "", "sha256": ""},
        "burned_in": False,
    }
    keep_sidecars = {
        "off": set(),
        "soft": {"subtitles.ass", "subtitles.srt"},
        "burn_in": {"subtitles.ass"},
    }[subtitle_settings.mode]
    try:
        subtitle_service.remove_stale_sidecars(project_id, keep_sidecars)
        if subtitle_settings.mode != "off":
            ass = subtitle_service.write_ass_sidecar(db, project)
            subtitle_record["cue_count"] = ass["cue_count"]
            subtitle_record["ass_sidecar"] = {
                "path": ass["path"], "sha256": ass["sha256"],
            }
            if subtitle_settings.mode == "soft":
                srt = subtitle_service.write_srt_sidecar(db, project)
                subtitle_record["srt_sidecar"] = {
                    "path": srt["path"], "sha256": srt["sha256"],
                }
            elif not ass["cue_count"]:
                warnings.append(
                    "Subtitle burn-in is enabled, but the current timeline has no "
                    "non-blank Shot dialogue. The review was rendered without subtitles."
                )
    except subtitle_service.SubtitleSidecarError as exc:
        return _blocked(project_id, f"Subtitle sidecar publication failed: {exc}")
    except ValueError as exc:
        return _blocked(project_id, f"Subtitle timing or text validation failed: {exc}")

    burn_subtitles = bool(
        subtitle_settings.mode == "burn_in" and subtitle_record["cue_count"]
    )
    subtitle_filter = (
        subtitle_service.ffmpeg_subtitles_filter(
            subtitle_record["ass_sidecar"]["path"]
        )
        if burn_subtitles else ""
    )

    # Fill the delivery frame edge-to-edge. Provider images commonly use a
    # nearby-but-different aspect ratio (for example 2:3 assets in a 9:16
    # project); fitting with padding produced visible black letterbox bars.
    # Scale to cover, then center-crop the small excess instead.
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:(iw-ow)/2:(ih-oh)/2,setsar=1"
    )

    # Decide once whether this render carries audio at all: the segments have
    # to agree, because the concat step stream-copies them.
    source_audio = [_source_has_audio(take.file_path) for _item, take in sources]
    if any(flag is None for flag in source_audio):
        return _blocked(
            project_id,
            "Source audio could not be detected because ffprobe was unavailable "
            "or could not read the media. Rendering is blocked to prevent audio loss.",
        )

    # What the director asked for, shot by shot. Resolved here rather than in
    # the loop so the report can be built from the same values the segments
    # were made with, instead of from a second read of the same rows.
    shot_audio = _shot_audio_direction(db, sources)
    muted_shots = [
        take.shot_id for index, (_item, take) in enumerate(sources)
        if shot_audio[index][0]
    ]
    adjusted_shots = {
        take.shot_id: shot_audio[index][1]
        for index, (_item, take) in enumerate(sources)
        if shot_audio[index][1]
    }

    keep_audio = any(
        flag and not shot_audio[index][0]
        for index, flag in enumerate(source_audio)
    )

    segment_paths: list[str] = []
    for index, (item, take) in enumerate(sources):
        duration = float(item.get("duration_sec") or 0.0) or 3.0
        segment = os.path.join(segments_dir, f"seg_{index:04d}.mp4")
        is_video = (take.file_path or "").lower().endswith(VIDEO_EXTENSIONS)
        # A still or a silent clip on an otherwise-audible timeline needs a
        # synthesised silent track to match the other segments.
        muted, gain_db = shot_audio[index]
        # A still, a silent clip, or one the director muted all need the same
        # synthesised track: the segments have to share a layout for the
        # concat demuxer's stream copy.
        needs_silence = keep_audio and (not source_audio[index] or muted)

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
        # Streams are mapped explicitly, so the source's tags and chapters
        # would otherwise ride along into the segment and then the delivery.
        cmd += STRIP_METADATA_ARGS
        cmd += [
            "-t", f"{duration:g}",
            "-r", f"{frame_rate:g}",
            "-vf", scale_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]
        if keep_audio:
            if gain_db and not needs_silence:
                cmd += ["-af", f"volume={gain_db:g}dB"]
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

    # Concatenate the normalised segments. Video can be stream-copied; audio is
    # decoded once so loudness normalisation applies to the assembled program.
    concat_file = os.path.join(out_dir, "concat_list.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            # The concat demuxer treats the path as a quoted token.
            escaped = seg.replace("\\", "/").replace("'", "'\\''")
            f.write("file '" + escaped + "'\n")

    output_path = os.path.join(out_dir, "review.mp4")
    loudness_input: float | None = None
    loudness_output: float | None = None
    output_true_peak: float | None = None
    loudness_target_achieved: bool | None = None
    loudness_gain_db: float | None = None
    concat_output = (
        os.path.join(out_dir, "review.pre-normalized.mp4")
        if keep_audio or burn_subtitles else output_path
    )
    concat_cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        *STRIP_METADATA_ARGS,
        "-c", "copy", concat_output,
    ]
    ok, err = _run(concat_cmd)
    if not ok:
        return _blocked(project_id, f"FFmpeg concat failed: {err}")

    narration_report: dict[str, Any] = {"present": False}
    if narrate:
        track = None
        try:
            track = narration.build_track(
                narration.cues_for_project(db, project_id),
                os.path.join(out_dir, "narration.wav"),
                voice=voice,
            )
        except Exception as exc:  # a voice engine is not worth losing a render
            warnings.append(f"Narration could not be produced: {exc}")
        narration_report = narration.describe(track)
        if track is not None:
            narrated = os.path.join(out_dir, "review.narrated.mp4")
            if keep_audio:
                mix_cmd = [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-i", concat_output, "-i", track.path,
                    "-filter_complex",
                    f"[0:a]volume={NARRATION_DUCK_DB:g}dB[bed];"
                    f"[bed][1:a]amix=inputs=2:duration=first:normalize=0[aout]",
                    "-map", "0:v", "-map", "[aout]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                    narrated,
                ]
            else:
                # Nothing on the timeline had audio, so the voice becomes the
                # programme's only track and the render now carries audio.
                mix_cmd = [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-i", concat_output, "-i", track.path,
                    "-map", "0:v", "-map", "1:a", "-shortest",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                    narrated,
                ]
            ok, err = _run(mix_cmd)
            if not ok:
                return _blocked(project_id, f"FFmpeg narration mix failed: {err}")
            try:
                os.remove(concat_output)
            except OSError:
                pass
            concat_output = narrated
            keep_audio = True
            if track.overruns:
                warnings.append(
                    f"{len(track.overruns)} narration line(s) run past the shot "
                    f"they belong to; the picture was left in step."
                )
            if track.failures:
                warnings.append(
                    f"{len(track.failures)} narration line(s) could not be spoken."
                )

    # --- Music bed -------------------------------------------------------
    # Laid after narration so it can be ducked under the voice, and before
    # loudness normalisation so the whole programme is measured together.
    music_report: dict[str, Any] = {
        "present": False, "gain_db": 0.0,
        "ducked_under_narration": False, "path": "",
    }
    music_path = (project.music_path or "").strip()
    if music_path and not os.path.isfile(music_path):
        # Losing a whole render over a moved file is the wrong trade; so is
        # delivering a silent film that was meant to have music and saying
        # nothing about it.
        warnings.append(
            f"The project's music bed file is missing, so the film was "
            f"rendered without it: {music_path}"
        )
    elif music_path:
        music_gain = float(
            project.music_gain_db if project.music_gain_db is not None
            else MUSIC_GAIN_DB
        )
        ducked = bool(narration_report.get("present"))
        if ducked:
            music_gain += MUSIC_NARRATION_DUCK_DB
        bedded = os.path.join(out_dir, "review.bedded.mp4")
        if keep_audio:
            # apad so a bed shorter than the film does not end the mix early;
            # duration=first then cuts it to the programme.
            filter_complex = (
                f"[1:a]volume={music_gain:g}dB,apad[bed];"
                f"[0:a][bed]amix=inputs=2:duration=first:normalize=0[aout]"
            )
            bed_cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", concat_output, "-i", music_path,
                "-filter_complex", filter_complex,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                bedded,
            ]
        else:
            # Nothing on the timeline had audio, so the bed becomes the only
            # track. Padded then cut with -shortest, so a bed shorter than the
            # film does not truncate the picture and a longer one does not
            # extend it.
            bed_cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", concat_output, "-i", music_path,
                "-filter_complex", f"[1:a]volume={music_gain:g}dB,apad[aout]",
                "-map", "0:v", "-map", "[aout]", "-shortest",
                "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                bedded,
            ]
        ok, err = _run(bed_cmd)
        if not ok:
            return _blocked(project_id, f"FFmpeg music bed mix failed: {err}")
        try:
            os.remove(concat_output)
        except OSError:
            pass
        concat_output = bedded
        keep_audio = True
        music_report = {
            "present": True,
            "gain_db": music_gain,
            "ducked_under_narration": ducked,
            "path": music_path,
        }

    audio_direction = {
        "muted_shots": muted_shots,
        "adjusted_shots": adjusted_shots,
        "music": music_report,
    }

    if keep_audio:
        input_measurement = _measure_loudness(ffmpeg, concat_output)
        if input_measurement is None:
            loudness_gain_db = 0.0
            warnings.append(
                "The assembled audio was silent or its loudness could not be "
                "measured, so no delivery gain was applied."
            )
        else:
            loudness_input = input_measurement["integrated_lufs"]
            loudness_gain_db = AUDIO_TARGET_LUFS - loudness_input
        final_cmd = [
            ffmpeg, "-y", "-loglevel", "error", "-i", concat_output,
            *STRIP_METADATA_ARGS,
        ]
        if burn_subtitles:
            final_cmd += [
                "-vf", subtitle_filter, "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            ]
        else:
            final_cmd += ["-c:v", "copy"]
        final_cmd += [
            "-af",
            f"volume={loudness_gain_db:g}dB,"
            f"alimiter=limit={AUDIO_LIMIT_LINEAR:g}:attack=5:release=50:level=false",
            "-c:a", "aac",
            "-ar", str(AUDIO_SAMPLE_RATE),
            "-ac", str(AUDIO_CHANNELS),
            "-b:a", AUDIO_BITRATE,
            output_path,
        ]
        ok, err = _run(final_cmd)
        try:
            os.remove(concat_output)
        except OSError:
            pass
        if not ok:
            if burn_subtitles:
                return _blocked(project_id, f"FFmpeg subtitle burn-in failed: {err}")
            return _blocked(project_id, f"FFmpeg audio normalisation failed: {err}")
        output_measurement = _measure_loudness(ffmpeg, output_path)
        if output_measurement is not None:
            loudness_output = output_measurement["integrated_lufs"]
            output_true_peak = output_measurement["true_peak_dbtp"]
            loudness_target_achieved = (
                abs(loudness_output - AUDIO_TARGET_LUFS) <= 1.0
                and output_true_peak <= AUDIO_TRUE_PEAK_DBTP
            )
        if loudness_target_achieved is False:
            warnings.append(
                f"Audio could not reach {AUDIO_TARGET_LUFS:g} LUFS without "
                f"exceeding the true-peak ceiling; measured {loudness_output:.2f} "
                f"LUFS and {output_true_peak:.2f} dBTP."
            )

    elif burn_subtitles:
        ok, err = _run([
            ffmpeg, "-y", "-loglevel", "error", "-i", concat_output,
            *STRIP_METADATA_ARGS,
            "-vf", subtitle_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-an", output_path,
        ])
        try:
            os.remove(concat_output)
        except OSError:
            pass
        if not ok:
            return _blocked(project_id, f"FFmpeg subtitle burn-in failed: {err}")

    subtitle_record["burned_in"] = burn_subtitles

    # Warnings that describe an accepted exception (the aspect waiver) are
    # tracked separately from warnings that describe an actual defect in this
    # delivery: a waiver explains a failure, it does not erase the others.
    material_warnings: list[str] = []

    probe = probe_media(output_path)
    expected = float(manifest.get("total_duration_sec") or 0.0)
    actual = probe.get("duration_sec", 0.0)
    if probe and expected and abs(actual - expected) > 1.0:
        message = (
            f"Rendered duration {actual:.2f}s differs from the manifest total "
            f"{expected:.2f}s by more than one second."
        )
        warnings.append(message)
        material_warnings.append(message)
    if keep_audio and probe and not probe.get("has_audio"):
        # The sources had audio but the assembled file does not - report it
        # rather than let a silent review video pass as correct.
        message = (
            "Source takes carry audio but the assembled review video has no "
            "audio stream."
        )
        warnings.append(message)
        material_warnings.append(message)

    # An empty ffprobe result is unknown, not clean. Only a successful probe
    # with no non-structural keys is allowed to become a deliverable.
    container_tags = read_container_tags(output_path)
    leaked = embedded_metadata_keys_from_tags(container_tags)
    metadata_status = (
        "unverified" if not container_tags else ("leaked" if leaked else "clean")
    )
    if metadata_status != "clean":
        if leaked:
            reason = (
                "Rendered output carried disallowed container metadata keys: "
                + ", ".join(leaked)
                + ". The rejected deliverable was removed."
            )
        else:
            reason = (
                "Rendered output metadata could not be verified with ffprobe. "
                "The rejected deliverable was removed."
            )
        _discard_delivery(output_path)
        return _blocked(
            project_id,
            reason,
            metadata_status=metadata_status,
            leaked_metadata_keys=leaked,
        )

    provenance_path = write_render_provenance(
        db, project, sources, output_path,
        {
            "width": width,
            "height": height,
            "frame_rate": frame_rate,
            "segment_count": len(segment_paths),
            "audio": {
                "kept": keep_audio,
                "sample_rate": AUDIO_SAMPLE_RATE if keep_audio else 0,
                "channels": AUDIO_CHANNELS if keep_audio else 0,
                "bitrate": AUDIO_BITRATE if keep_audio else "",
                "target_lufs": AUDIO_TARGET_LUFS if keep_audio else None,
                "true_peak_dbtp": AUDIO_TRUE_PEAK_DBTP if keep_audio else None,
                "loudness_range_lu": AUDIO_LOUDNESS_RANGE if keep_audio else None,
                # What was asked for, shot by shot, so a delivered file can be
                # checked against the direction it was made under rather than
                # only against its measured loudness.
                "direction": audio_direction,
                "measured_input_lufs": loudness_input,
                "measured_output_lufs": loudness_output,
                "measured_output_true_peak_dbtp": output_true_peak,
                "target_achieved": loudness_target_achieved,
                "applied_gain_db": loudness_gain_db,
            },
            "container_metadata_stripped": True,
            "subtitles": subtitle_record,
        },
        container_tags=container_tags,
    )
    if not provenance_path:
        _discard_delivery(output_path)
        return _blocked(
            project_id,
            "The rendered output was removed because its provenance sidecar "
            "could not be written.",
            metadata_status=metadata_status,
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
        # What was spoken over the film, and which lines did not go cleanly.
        "audio_direction": audio_direction,
        "narration": narration_report,
        "provenance_path": provenance_path,
        "embedded_metadata_keys": leaked,
        "metadata_status": metadata_status,
        "warning_metadata": override_warnings,
        "delivery_validation": {
            # The timeline lineage was already verified strictly above, so
            # reaching here means the pipeline itself ran clean.
            "pipeline_pass": True,
            "delivery_spec_pass": not override_warnings and not material_warnings,
        },
    }
