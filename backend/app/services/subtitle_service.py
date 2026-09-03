"""Validated project subtitle settings and deterministic sidecar generation."""

from __future__ import annotations

import hashlib
import html
import math
import os
import re
import tempfile
import unicodedata
from typing import Any, Literal

import regex
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app import paths
from app.models import Project, Shot
from app.services.generation_planning import parse_resolution
from app.services.timeline_service import get_timeline_manifest

SubtitleMode = Literal["off", "soft", "burn_in"]
SubtitlePreset = Literal["clean", "cinematic", "social_bold", "thai_friendly"]
SubtitlePosition = Literal["top", "middle", "bottom"]

FONT_FAMILIES = (
    "Segoe UI",
    "Leelawadee UI",
    "Tahoma",
    "Arial",
    "Noto Sans Thai",
)
PRESETS = ("clean", "cinematic", "social_bold", "thai_friendly")
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
BIDI_CONTROLS = frozenset(chr(value) for value in (
    0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
))


class SubtitleSidecarError(RuntimeError):
    """A subtitle sidecar could not be safely published or removed."""


class SubtitleSettings(BaseModel):
    """Closed, centrally validated style surface; no paths or filter syntax."""

    model_config = ConfigDict(extra="forbid")

    mode: SubtitleMode = "off"
    preset: SubtitlePreset = "clean"
    font_family: str = "Segoe UI"
    font_size: int = Field(default=52, ge=18, le=120)
    text_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    shadow_color: str = "#000000"
    background_color: str = "#000000"
    bold: bool = False
    italic: bool = False
    outline_width: int = Field(default=3, ge=0, le=10)
    shadow_depth: int = Field(default=2, ge=0, le=10)
    background_box: bool = False
    position: SubtitlePosition = "bottom"
    vertical_margin: int = Field(default=64, ge=0, le=400)
    max_chars_per_line: int = Field(default=36, ge=12, le=80)

    @field_validator("font_family")
    @classmethod
    def validate_font_family(cls, value: str) -> str:
        if value not in FONT_FAMILIES:
            raise ValueError(f"font_family must be one of: {', '.join(FONT_FAMILIES)}")
        return value

    @field_validator(
        "text_color", "outline_color", "shadow_color", "background_color"
    )
    @classmethod
    def validate_color(cls, value: str) -> str:
        if not COLOR_PATTERN.fullmatch(value):
            raise ValueError("colors must use #RRGGBB")
        return value.upper()


DEFAULT_SUBTITLE_SETTINGS = SubtitleSettings().model_dump()


def settings_for_project(project: Project) -> SubtitleSettings:
    """Return sanitized persisted settings, falling back safely for legacy rows."""
    try:
        return SubtitleSettings.model_validate(project.subtitle_settings or {})
    except (TypeError, ValueError):
        return SubtitleSettings()


def save_settings(project: Project, settings: SubtitleSettings) -> dict[str, Any]:
    sanitized = settings.model_dump()
    project.subtitle_settings = sanitized
    return sanitized


def _graphemes(text: str) -> list[str]:
    """Split text at Unicode extended-grapheme boundaries (UAX #29)."""
    return regex.findall(r"\X", str(text))


def _split_text(text: str, width: int) -> list[str]:
    """Split exact source text into chunks that each fit at most two lines."""
    remaining = _graphemes(text)
    capacity = width * 2
    chunks: list[str] = []
    while len(remaining) > capacity:
        cut = capacity
        for index in range(capacity, 0, -1):
            if remaining[index - 1].isspace():
                cut = index
                break
        chunks.append("".join(remaining[:cut]))
        remaining = remaining[cut:]
    if remaining:
        chunks.append("".join(remaining))
    return chunks


def _wrap_two_lines(text: str, width: int) -> str:
    """Wrap one bounded cue to at most two grapheme-safe lines."""
    source_lines = [
        " ".join(line.split())
        for line in str(text).replace("\r", "").split("\n")
        if line.strip()
    ]
    normalized = "\n".join(source_lines)
    if len(source_lines) == 2 and all(
        len(_graphemes(line)) <= width for line in source_lines
    ):
        return normalized
    normalized = " ".join(normalized.split())
    clusters = _graphemes(normalized)
    if len(clusters) <= width:
        return normalized
    # A whitespace break is useful only when *both* resulting lines remain
    # within the configured grapheme width. Otherwise use the hard safe cut.
    cut = width
    minimum_cut = max(1, len(clusters) - width)
    for index in range(min(width, len(clusters)), minimum_cut - 1, -1):
        if clusters[index - 1].isspace():
            cut = index
            break
    first = "".join(clusters[:cut]).strip()
    second = "".join(clusters[cut:]).strip()
    return f"{first}\n{second}" if second else first


def _split_cue(cue: dict[str, Any], width: int) -> list[dict[str, Any]]:
    chunks = _split_text(str(cue["text"]), width)
    if len(chunks) <= 1:
        return [dict(cue)]
    start = float(cue["start_sec"])
    end = float(cue["end_sec"])
    weights = [len(_graphemes(chunk)) for chunk in chunks]
    total = sum(weights)
    result: list[dict[str, Any]] = []
    consumed = 0
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        chunk_start = start if index == 0 else start + (end - start) * consumed / total
        consumed += weight
        chunk_end = end if index == len(chunks) - 1 else start + (end - start) * consumed / total
        result.append({**cue, "start_sec": chunk_start, "end_sec": chunk_end, "text": chunk})
    return result


def _validated_cues(
    cues: list[dict[str, Any]], width: int
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for source in cues:
        try:
            start = float(source["start_sec"])
            end = float(source["end_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "cue times must be finite, non-negative, and end must be after start"
            ) from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError(
                "cue times must be finite, non-negative, and end must be after start"
            )
        for cue in _split_cue({**source, "start_sec": start, "end_sec": end}, width):
            cue["index"] = len(validated) + 1
            validated.append(cue)
    return validated


def _require_serialized_duration(cues: list[dict[str, Any]], formatter: Any) -> None:
    """Reject intervals that collapse after ASS/SRT timestamp quantization."""
    for cue in cues:
        if formatter(float(cue["start_sec"])) == formatter(float(cue["end_sec"])):
            raise ValueError(
                "subtitle cue duration is too short for the output time precision"
            )


def build_subtitle_cues(
    db: Session, project_id: str, max_chars_per_line: int = 36
) -> list[dict[str, Any]]:
    """Build cues only from strict timeline placements and their Shot.dialogue."""
    # Validation here keeps callers outside the API from bypassing safe wrapping.
    SubtitleSettings(max_chars_per_line=max_chars_per_line)
    manifest = get_timeline_manifest(db, project_id, strict_lineage=True)
    shot_ids = [item.get("shot_id") for item in manifest.get("items", [])]
    shots = {
        shot.id: shot
        for shot in db.query(Shot).filter(Shot.id.in_(shot_ids)).all()
    } if shot_ids else {}
    cues: list[dict[str, Any]] = []
    timeline_cursor = 0.0
    for item in manifest.get("items", []):
        duration_sec = float(item["duration_sec"])
        cue_start = timeline_cursor
        cue_end = cue_start + duration_sec
        timeline_cursor = cue_end

        shot = shots.get(item.get("shot_id"))
        raw = (shot.dialogue if shot is not None else "") or ""
        normalized = raw.strip()
        if not normalized:
            continue
        # Timeline in/out points trim the source take; subtitle timing follows
        # the placed clip's cumulative output position instead.
        source_cue = {
            "index": 0,
            "start_sec": cue_start,
            "end_sec": cue_end,
            "text": normalized,
        }
        for cue in _validated_cues([source_cue], max_chars_per_line):
            cue["index"] = len(cues) + 1
            cues.append(cue)
    return cues


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(milliseconds, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _ass_color(color: str, alpha: str = "00") -> str:
    red, green, blue = color[1:3], color[3:5], color[5:7]
    return f"&H{alpha}{blue}{green}{red}"


def _escape_ass_text(text: str, width: int) -> str:
    wrapped = _wrap_two_lines(text, width)
    escaped = wrapped.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
    return escaped.replace("\n", r"\N")


def _sanitize_srt_text(text: str) -> str:
    """Make cue text inert in players that interpret SRT as HTML-like markup."""
    cleaned = "".join(
        character
        for character in str(text)
        if character not in BIDI_CONTROLS
        and (character in "\n\t" or unicodedata.category(character) != "Cc")
    )
    return html.escape(cleaned, quote=False)


def render_ass(
    cues: list[dict[str, Any]], settings: SubtitleSettings, width: int, height: int
) -> str:
    """Render deterministic UTF-8 ASS using a single validated style."""
    horizontal_margin = max(1, round(width * 0.05))
    vertical_margin = max(
        1, round(height * 0.05), round(settings.vertical_margin * height / 1080)
    )
    alignment = {"bottom": 2, "middle": 5, "top": 8}[settings.position]
    border_style = 3 if settings.background_box else 1
    back_alpha = "20" if settings.background_box else "80"
    back_color = (
        settings.background_color if settings.background_box else settings.shadow_color
    )
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Default,"
        f"{settings.font_family},{settings.font_size},{_ass_color(settings.text_color)},"
        f"{_ass_color(settings.text_color)},{_ass_color(settings.outline_color)},"
        f"{_ass_color(back_color, back_alpha)},"
        f"{-1 if settings.bold else 0},{-1 if settings.italic else 0},0,0,100,100,0,0,"
        f"{border_style},{settings.outline_width},{settings.shadow_depth},{alignment},"
        f"{horizontal_margin},{horizontal_margin},{vertical_margin},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    safe_cues = _validated_cues(cues, settings.max_chars_per_line)
    _require_serialized_duration(safe_cues, _ass_time)
    events = "".join(
        "Dialogue: 0,"
        f"{_ass_time(cue['start_sec'])},{_ass_time(cue['end_sec'])},"
        f"Default,,0,0,0,,{_escape_ass_text(cue['text'], settings.max_chars_per_line)}\n"
        for cue in safe_cues
    )
    return header + events


def render_srt(cues: list[dict[str, Any]], max_chars_per_line: int = 36) -> str:
    """Render portable plain-text SRT from the same canonical cue list."""
    safe_cues = _validated_cues(cues, max_chars_per_line)
    _require_serialized_duration(safe_cues, _srt_time)
    blocks = [
        f"{index}\n{_srt_time(cue['start_sec'])} --> {_srt_time(cue['end_sec'])}\n"
        f"{_wrap_two_lines(_sanitize_srt_text(cue['text']), max_chars_per_line)}"
        for index, cue in enumerate(safe_cues, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_ass_sidecar(db: Session, project: Project) -> dict[str, Any]:
    settings = settings_for_project(project)
    cues = build_subtitle_cues(db, project.id, settings.max_chars_per_line)
    width, height = _resolution(project.target_resolution)
    content = render_ass(cues, settings, width, height)
    out_dir = paths.exports_dir(project.id)
    _ensure_export_dir(out_dir)
    path = os.path.join(out_dir, "subtitles.ass")
    encoded = content.encode("utf-8")
    _atomic_write(path, encoded)
    return {"path": path, "sha256": hashlib.sha256(encoded).hexdigest(), "cue_count": len(cues)}


def write_srt_sidecar(db: Session, project: Project) -> dict[str, Any]:
    settings = settings_for_project(project)
    cues = build_subtitle_cues(db, project.id, settings.max_chars_per_line)
    content = render_srt(cues, settings.max_chars_per_line)
    out_dir = paths.exports_dir(project.id)
    _ensure_export_dir(out_dir)
    path = os.path.join(out_dir, "subtitles.srt")
    encoded = content.encode("utf-8")
    _atomic_write(path, encoded)
    return {"path": path, "sha256": hashlib.sha256(encoded).hexdigest(), "cue_count": len(cues)}


def _ensure_export_dir(path: str) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise SubtitleSidecarError(
            f"Could not prepare subtitle export directory {path}: {exc}"
        ) from exc


def _atomic_write(path: str, content: bytes) -> None:
    """Publish complete bytes with replace semantics and no orphaned temp file."""
    temporary = ""
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=os.path.dirname(path),
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise SubtitleSidecarError(f"Could not publish {path}: {exc}") from exc
    finally:
        if temporary:
            try:
                os.remove(temporary)
            except OSError:
                pass


def remove_stale_sidecars(project_id: str, keep: set[str] | None = None) -> None:
    """Remove subtitle formats that the current mode will not publish."""
    keep = keep or set()
    out_dir = paths.exports_dir(project_id)
    for filename in ("subtitles.ass", "subtitles.srt"):
        if filename in keep:
            continue
        path = os.path.join(out_dir, filename)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise SubtitleSidecarError(f"Could not remove stale {path}: {exc}") from exc


def ffmpeg_subtitles_filter(ass_path: str) -> str:
    """Quote our generated sidecar path for FFmpeg's subtitles filter only."""
    normalized = ass_path.replace("\\", "/")
    escaped = (
        normalized.replace("\\", "\\\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )
    return f"subtitles=filename='{escaped}'"


def _resolution(value: str) -> tuple[int, int]:
    return parse_resolution(value)
