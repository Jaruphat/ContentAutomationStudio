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

#: The Shot field a spoken line comes from. Named here because the narration
#: track reads the same one: a line must not be sayable but unshowable, or the
#: reverse, and a shared constant is what keeps that from drifting.
DIALOGUE_FIELD = "dialogue"

#: The Shot field an emphasis card comes from. A separate track doing a
#: different job: a subtitle carries everything said, an emphasis card carries
#: three to six words for a beat.
EMPHASIS_FIELD = "emphasis_text"
#: How long a card is held. It is a punch, not a lower third - held for the
#: whole shot it stops being emphasis and becomes furniture.
EMPHASIS_SECONDS = 1.8
#: Where a two-line card breaks, written by hand.
EMPHASIS_BREAK = "/"
#: Caps that catch a mistake rather than police a style. A pasted paragraph in
#: this field is not a long emphasis; it is a paragraph, and it covers the
#: frame.
EMPHASIS_MAX_WORDS = 8
EMPHASIS_MAX_LINES = 2

#: Below this the text stops being readable at all, so a very narrow canvas
#: gets a slightly overrunning line rather than an unreadable one.
MIN_RENDERED_FONT_SIZE = 14
#: Rough width of one character as a fraction of the font size, for a
#: proportional sans. Deliberately generous: a line that fits is worth more
#: than a line that exactly fills.
_CHAR_WIDTH_RATIO = 0.5

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


def _word_lines(text: str, width: int) -> list[str]:
    """Greedy word wrap. A word is never broken unless it is the whole line.

    There is no width at which cutting a word is the better choice: a reader
    with two seconds to take in a line cannot spend one of them reassembling
    "roo" and "ms". The single exception is a token wider than the line, where
    there is no break to prefer and the alternative is text running off the
    side of the frame.
    """
    lines: list[str] = []
    current: list[str] = []
    length = 0

    def flush() -> None:
        nonlocal current, length
        if current:
            lines.append(" ".join(current))
            current, length = [], 0

    for word in str(text).split():
        clusters = _graphemes(word)
        if len(clusters) > width:
            flush()
            while len(clusters) > width:
                lines.append("".join(clusters[:width]))
                clusters = clusters[width:]
            if not clusters:
                continue
            word = "".join(clusters)
        size = len(_graphemes(word))
        needed = size + (1 if current else 0)
        if current and length + needed > width:
            flush()
            current, length = [word], size
        else:
            current.append(word)
            length += needed
    flush()
    return lines


def _word_starts(clusters: list[str]) -> list[int]:
    """Offsets where a word begins, i.e. every place a cue may be divided."""
    return [
        index
        for index in range(1, len(clusters))
        if clusters[index - 1].isspace() and not clusters[index].isspace()
    ]


def _sentence_bonus(clusters: list[str], offset: int, width: int) -> float:
    """How much to prefer a break that follows the end of a sentence.

    "This house has seven rooms. / The plan shows six." reads; "This house has
    seven / rooms. The plan shows six." does not, even though the second is
    closer to an even division. A full stop is where the writer already broke
    the thought, so a break just after one is worth some imbalance.
    """
    for back in range(offset - 1, max(-1, offset - 4), -1):
        if clusters[back] in ".?!":
            return width / 2
    return 0.0


def _choose_cuts(clusters: list[str], starts: list[int], count: int) -> list[int]:
    """Pick `count - 1` break offsets, aiming at an even division."""
    cuts: list[int] = []
    total = len(clusters)
    width_hint = max(1, total // max(1, count))
    available = list(starts)
    for step in range(1, count):
        if not available:
            break
        target = total * step / count
        best = min(
            available,
            key=lambda offset: abs(offset - target)
            - _sentence_bonus(clusters, offset, width_hint),
        )
        cuts.append(best)
        available = [offset for offset in available if offset > best]
    return cuts


def _split_words(text: str, width: int) -> list[str]:
    """Divide text at word boundaries into chunks that each fit two lines.

    Slices the source rather than rejoining words, so the pieces concatenate
    back to exactly what was written - trailing spaces and all. Rejoining
    normalises whitespace, and a caption track that silently loses a space at
    every cue boundary is a caption track that no longer matches the script.
    """
    clusters = _graphemes(str(text))
    starts = _word_starts(clusters)
    count = max(1, -(-len(_word_lines(text, width)) // 2))
    while count <= len(starts) + 1:
        cuts = _choose_cuts(clusters, starts, count)
        edges = [0, *cuts, len(clusters)]
        chunks = [
            "".join(clusters[begin:end])
            for begin, end in zip(edges, edges[1:])
            if end > begin
        ]
        if chunks and all(len(_word_lines(chunk, width)) <= 2 for chunk in chunks):
            return chunks
        count += 1
    return [str(text)]


def _grapheme_chunks(text: str, capacity: int) -> list[str]:
    """Chunk by grapheme count, preferring a space inside the window.

    The fallback for writing that offers no word break to prefer. Thai runs
    without spaces, so a Thai cue longer than two lines can only be divided
    between grapheme clusters; refusing to divide it would leave one caption
    on screen for the length of the shot.
    """
    remaining = _graphemes(text)
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


def _split_text(text: str, width: int) -> list[str]:
    """Split source text into chunks that each fit two lines of `width`.

    Two lines is what a chunk is promised downstream, and the promise has to
    hold after wrapping rather than at a character count: a chunk of exactly
    twice the width only fits when a break happens to fall on the boundary,
    and when it did not, the wrapper cut a word in half.

    Applying this twice must give what applying it once gave. The renderers
    validate cues again on their way out, so a splitter that keeps finding new
    divisions would turn one caption into several between the timeline and the
    file.
    """
    words = str(text).split()
    if not words:
        return [str(text)] if str(text).strip() else []
    if all(len(_graphemes(word)) <= width for word in words):
        return _split_words(text, width)
    pieces = _grapheme_chunks(str(text), width * 2)
    if len(pieces) <= 1:
        return pieces
    divided: list[str] = []
    for piece in pieces:
        divided.extend(_split_text(piece, width))
    return divided


def _wrap_two_lines(text: str, width: int) -> str:
    """Wrap one bounded cue to at most two lines, breaking on words if it can.

    Two lines the writer wrote themselves are left as written when both
    already fit. Otherwise the words are wrapped, and only writing that offers
    no usable break inside the line - Thai, a URL - falls back to the
    grapheme cut. That cut never inserts a space, because a space inside a
    token turns one word into two.
    """
    source_lines = [
        " ".join(line.split())
        for line in str(text).replace("\r", "").split("\n")
        if line.strip()
    ]
    if len(source_lines) == 2 and all(
        len(_graphemes(line)) <= width for line in source_lines
    ):
        return "\n".join(source_lines)

    flat = " ".join(" ".join(source_lines).split())
    clusters = _graphemes(flat)
    if len(clusters) <= width:
        return flat

    lines = _word_lines(flat, width)
    if len(lines) == 2 and all(len(_graphemes(line)) <= width for line in lines):
        return "\n".join(lines)

    # No pair of word-broken lines fits. `_split_text` prevents that for
    # writing with usable breaks, so what arrives here has none.
    first = "".join(clusters[:width]).rstrip()
    second = "".join(clusters[width:]).strip()
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
        raw = (getattr(shot, DIALOGUE_FIELD, "") if shot is not None else "") or ""
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


def _emphasis_lines(raw: str) -> str:
    """Normalise one card's text, refusing what would cover the frame."""
    parts = [part.strip() for part in raw.split(EMPHASIS_BREAK)]
    lines = [part for part in parts if part]
    if len(lines) > EMPHASIS_MAX_LINES:
        raise ValueError(
            f"An emphasis card may be at most {EMPHASIS_MAX_LINES} lines; "
            f"'{raw}' has {len(lines)}. Use one '{EMPHASIS_BREAK}' at most."
        )
    words = sum(len(line.split()) for line in lines)
    if words > EMPHASIS_MAX_WORDS:
        raise ValueError(
            f"An emphasis card may be at most {EMPHASIS_MAX_WORDS} words; "
            f"this one has {words}. Long text here is not emphasis, it is a "
            f"paragraph across the frame - put it in the shot's dialogue "
            f"instead, where it becomes a subtitle."
        )
    return "\n".join(lines)


def build_emphasis_cues(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Cards from Shot.emphasis_text, timed to the cut rather than the clips.

    The same trap the dialogue track has: timing from source clip lengths
    while the cut uses planned lengths puts every later card in the wrong
    place. Both read the placed item's cumulative position instead.
    """
    manifest = get_timeline_manifest(db, project_id, strict_lineage=True)
    shot_ids = [item.get("shot_id") for item in manifest.get("items", [])]
    shots = {
        shot.id: shot
        for shot in db.query(Shot).filter(Shot.id.in_(shot_ids)).all()
    } if shot_ids else {}

    cues: list[dict[str, Any]] = []
    cursor = 0.0
    for item in manifest.get("items", []):
        duration = float(item["duration_sec"])
        start = cursor
        cursor += duration

        shot = shots.get(item.get("shot_id"))
        raw = (getattr(shot, EMPHASIS_FIELD, "") if shot is not None else "") or ""
        if not raw.strip():
            continue
        cues.append({
            "index": len(cues) + 1,
            "start_sec": start,
            # Never outlives its shot: on a one-second cut a card held for
            # 1.8s bleeds onto the next shot.
            "end_sec": start + min(EMPHASIS_SECONDS, duration),
            "text": _emphasis_lines(raw),
        })
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


#: How much larger a card is than the subtitle beneath it, and how far down
#: the frame it sits. A card that rendered identically to a subtitle would
#: make separating the two tracks pointless.
EMPHASIS_SIZE_RATIO = 1.7
EMPHASIS_VERTICAL_FRACTION = 0.28


def _emphasis_style(
    settings: SubtitleSettings, subtitle_size: int, height: int, margin: int
) -> str:
    """The card style: bigger, bolder, in the upper third, always centred."""
    size = max(MIN_RENDERED_FONT_SIZE, int(subtitle_size * EMPHASIS_SIZE_RATIO))
    vertical = max(1, int(height * EMPHASIS_VERTICAL_FRACTION))
    return (
        "Style: Emphasis,"
        f"{settings.font_family},{size},{_ass_color(settings.text_color)},"
        f"{_ass_color(settings.text_color)},{_ass_color(settings.outline_color)},"
        f"{_ass_color(settings.shadow_color, '80')},"
        # Always bold, never italic, always top-centre: it is a title card,
        # not a caption that inherits the subtitle's placement.
        "-1,0,0,0,100,100,0,0,"
        f"1,{max(settings.outline_width, 2)},{settings.shadow_depth},8,"
        f"{margin},{margin},{vertical},1\n"
    )


def render_ass(
    cues: list[dict[str, Any]],
    settings: SubtitleSettings,
    width: int,
    height: int,
    emphasis_cues: list[dict[str, Any]] | None = None,
) -> str:
    """Render deterministic UTF-8 ASS: the subtitle track, and the cards.

    One file with two styles rather than two files. Two burn-in passes would
    re-encode the picture twice for no reason, and two sidecars cannot be
    layered by the same filter.
    """
    horizontal_margin = max(1, round(width * 0.05))
    vertical_margin = max(
        1, round(height * 0.05), round(settings.vertical_margin * height / 1080)
    )
    # PlayResX is the real frame width, so the font size is in the frame's own
    # units: a size chosen against 1920 draws three times too wide on a 576
    # vertical cut and runs off both edges. The margin was already scaled to
    # the canvas; this scales the type to match, capping it at the largest
    # size a full line still fits inside.
    usable_width = max(1, width - 2 * horizontal_margin)
    fitting_size = int(
        usable_width / (settings.max_chars_per_line * _CHAR_WIDTH_RATIO)
    )
    font_size = max(MIN_RENDERED_FONT_SIZE, min(settings.font_size, fitting_size))
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
        f"{settings.font_family},{font_size},{_ass_color(settings.text_color)},"
        f"{_ass_color(settings.text_color)},{_ass_color(settings.outline_color)},"
        f"{_ass_color(back_color, back_alpha)},"
        f"{-1 if settings.bold else 0},{-1 if settings.italic else 0},0,0,100,100,0,0,"
        f"{border_style},{settings.outline_width},{settings.shadow_depth},{alignment},"
        f"{horizontal_margin},{horizontal_margin},{vertical_margin},1\n"
        + _emphasis_style(settings, font_size, height, horizontal_margin)
        + "\n[Events]\n"
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

    # The cards, on their own style and their own layer, so they sit over the
    # picture without displacing the subtitle track below them. The hand-written
    # break becomes ASS's own, which is the one thing that must survive.
    for cue in emphasis_cues or []:
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        events += (
            "Dialogue: 1,"
            f"{_ass_time(float(cue['start_sec']))},"
            f"{_ass_time(float(cue['end_sec']))},"
            f"Emphasis,,0,0,0,,{text.replace(chr(10), chr(92) + 'N')}\n"
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
    # The cards ride in the same file, on their own style. The burned-in track
    # is the only place they appear: a soft subtitle file is a transcript, and
    # a transcript carrying both a sentence and the three words punched out of
    # it has the same line twice.
    emphasis = build_emphasis_cues(db, project.id)
    width, height = _resolution(project.target_resolution)
    content = render_ass(cues, settings, width, height, emphasis_cues=emphasis)
    out_dir = paths.exports_dir(project.id)
    _ensure_export_dir(out_dir)
    path = os.path.join(out_dir, "subtitles.ass")
    encoded = content.encode("utf-8")
    _atomic_write(path, encoded)
    return {
        "path": path,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "cue_count": len(cues),
        "emphasis_count": len(emphasis),
    }


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
