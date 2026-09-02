"""
Versioned prompt templates for the AI story tasks.

The template text is an artifact, not an implementation detail: a storyboard
generated last week can only be reproduced or explained if the exact wording
that produced it is identifiable. So every template carries a version, the
version travels with the request into the provenance record, and changing a
template's wording means bumping its version.

Nothing here talks to a provider. These functions turn project state into two
strings, which keeps them trivially testable and keeps provider modules free of
domain knowledge.
"""

import re
from typing import Any

PROMPT_VERSIONS: dict[str, str] = {
    "scene_decomposition": "1.0",
    "story_bible": "1.0",
    "shot_prompts": "1.1",
}

#: Shared preamble. Every task returns JSON only, and every task is told not to
#: invent the things the schema deliberately omits.
_JSON_DISCIPLINE = (
    "Reply with a single JSON object matching the provided schema exactly. "
    "No prose before or after it, no markdown fence. Every property in the "
    "schema must be present; use an empty string rather than null or a missing "
    "key when you have nothing to say."
)


def _project_context(project: dict[str, Any]) -> str:
    """The production constraints every task has to respect."""
    lines = [
        "PRODUCTION CONSTRAINTS",
        f"- Title: {project.get('title') or '(untitled)'}",
        f"- Objective: {project.get('objective') or '(not stated)'}",
        f"- Audience: {project.get('audience') or '(not stated)'}",
        f"- Content type: {project.get('content_type') or 'video'}",
        f"- Aspect ratio: {project.get('aspect_ratio') or '16:9'}",
        f"- Target resolution: {project.get('target_resolution') or '1920x1080'}",
        f"- Frame rate: {project.get('frame_rate') or 24} fps",
        f"- Target total duration: {project.get('target_duration_sec') or 0:g} seconds",
        f"- Language for dialogue and on-screen text: {project.get('language') or 'en'}",
    ]
    return "\n".join(lines)


def _story_bible_context(
    characters: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    styles: list[dict[str, Any]],
) -> str:
    """Existing bible entries, so the model reuses names instead of coining new ones."""
    if not (characters or locations or styles):
        return (
            "STORY BIBLE\n"
            "- Empty. Invent whatever characters and locations the plot needs, "
            "and name them consistently across scenes."
        )

    lines = ["STORY BIBLE (reuse these names exactly; do not rename or duplicate)"]
    for character in characters:
        lines.append(
            f"- Character '{character.get('name', '')}': "
            f"{character.get('role', '')}; {character.get('appearance', '')}; "
            f"wardrobe {character.get('clothing', '')}; "
            f"tokens: {character.get('prompt_tokens', '')}"
        )
    for location in locations:
        lines.append(
            f"- Location '{location.get('name', '')}': "
            f"{location.get('description', '')}; "
            f"lighting {location.get('lighting', '')}; "
            f"palette {location.get('palette', '')}"
        )
    for style in styles:
        lines.append(
            f"- Style: {style.get('medium', '')} / {style.get('genre', '')}; "
            f"look: {style.get('visual_keywords', '')}; "
            f"camera: {style.get('camera_language', '')}; "
            f"never show: {style.get('negative_constraints', '')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Task 1: brief/plot -> scenes and shots
# ---------------------------------------------------------------------------

SCENE_DECOMPOSITION_SYSTEM = (
    "You are a director and storyboard artist breaking a creative brief into a "
    "shot list that a text-to-image and text-to-video pipeline will generate "
    "literally.\n\n"
    "Work to these rules:\n"
    "- Every shot must be filmable from its own description alone. A generator "
    "sees one shot at a time and has no memory of the others, so never write "
    "'the same room as before' or 'she turns back'; restate the subject, the "
    "setting and the look in every shot.\n"
    "- Keep characters and locations visually identical between shots by "
    "repeating the same concrete descriptors, not by referring back.\n"
    "- Shot durations must sum to roughly the target duration, and each shot "
    "must be short enough for a single generated clip.\n"
    "- Choose generation_mode per shot: 'image' for a static frame, 'video' "
    "for motion generated from text, 'image-to-video' only when the shot "
    "should animate a still established by an earlier shot in the same scene.\n"
    "- video_prompt must be an empty string when generation_mode is 'image'.\n"
    "- Write prompts as descriptive phrases, not instructions to an assistant.\n\n"
    + _JSON_DISCIPLINE
)


def build_scene_decomposition_prompt(
    project: dict[str, Any],
    brief_text: str,
    plot_text: str,
    characters: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    styles: list[dict[str, Any]],
    scene_count: int,
    min_shots: int,
    max_shots: int,
    extra_guidance: str = "",
) -> str:
    """The user message for scene/shot decomposition."""
    parts = [
        _project_context(project),
        "",
        _story_bible_context(characters, locations, styles),
        "",
        "CREATIVE BRIEF",
        brief_text.strip() or "(none supplied)",
        "",
        "PLOT",
        plot_text.strip() or "(none supplied)",
        "",
        "REQUIRED STRUCTURE",
        f"- Produce exactly {scene_count} scenes.",
        f"- Produce between {min_shots} and {max_shots} shots in total across "
        f"all scenes.",
        "- Number scenes from 0 upward, and shots from 0 upward within each scene.",
        "- Set each scene's planned_duration_sec to the sum of its shots' durations.",
    ]
    if extra_guidance.strip():
        parts += ["", "ADDITIONAL DIRECTION FROM THE USER", extra_guidance.strip()]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Task 2: brief/plot -> story bible
# ---------------------------------------------------------------------------

STORY_BIBLE_SYSTEM = (
    "You are a production designer building the reference bible for a short "
    "film from its brief and plot.\n\n"
    "Work to these rules:\n"
    "- Describe only what a camera would see. 'Determined' is not a "
    "description; 'jaw set, shoulders squared' is.\n"
    "- Every character needs prompt_tokens: a short comma-separated list of "
    "concrete visual features repeated verbatim in every prompt that features "
    "them. This is the only mechanism holding their appearance steady across "
    "independently generated shots, so make it specific and unambiguous.\n"
    "- Extract only characters and locations the brief or plot actually "
    "implies. An empty array is a valid answer; invented extras are not.\n"
    "- negative_constraints should list what would break the piece's look, "
    "such as 'text overlays, watermarks, modern clothing'.\n\n"
    + _JSON_DISCIPLINE
)


def build_story_bible_prompt(
    project: dict[str, Any],
    brief_text: str,
    plot_text: str,
    existing_characters: list[dict[str, Any]],
    existing_locations: list[dict[str, Any]],
    existing_styles: list[dict[str, Any]],
    extra_guidance: str = "",
) -> str:
    """The user message for story bible extraction."""
    parts = [
        _project_context(project),
        "",
        _story_bible_context(existing_characters, existing_locations, existing_styles),
        "",
        "CREATIVE BRIEF",
        brief_text.strip() or "(none supplied)",
        "",
        "PLOT",
        plot_text.strip() or "(none supplied)",
        "",
        "TASK",
        "Return the characters, locations and single visual style this piece "
        "needs. Where an entry above already exists, return it again with the "
        "same name and any improvements folded in, rather than a near-duplicate "
        "under a different name.",
    ]
    if extra_guidance.strip():
        parts += ["", "ADDITIONAL DIRECTION FROM THE USER", extra_guidance.strip()]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Task 3: storyboard -> compiled image/video prompts
# ---------------------------------------------------------------------------

SHOT_PROMPTS_SYSTEM = (
    "You are compiling final generation prompts for a storyboard that is "
    "already locked. The scenes and shots are fixed; you are writing the text "
    "that goes to the image and video models.\n\n"
    "Work to these rules:\n"
    "- Do not change what happens in a shot. Describe the given shot better.\n"
    "- Fold in the story bible: a shot featuring a character must repeat that "
    "character's prompt_tokens verbatim, and a shot in a known location must "
    "repeat that location's descriptors.\n"
    "- Each prompt must stand alone. Never reference another shot.\n"
    "- Treat GLOBAL INVARIANTS as applying to every relevant shot. Treat "
    "SCENE-SPECIFIC DIRECTION as applying only to its named scene; never copy "
    "final-scene, opening-scene, or numbered-scene direction elsewhere.\n"
    "- image_prompt describes a single frame: subject, action, setting, "
    "framing, lens, lighting, look. No camera motion, no time passing.\n"
    "- video_prompt describes motion over the shot's duration: what moves and "
    "how the camera moves. Empty string for a still-only shot.\n"
    "- negative_prompt lists what must not appear, combining the shot's own "
    "exclusions with the style's negative constraints.\n"
    "- Return exactly one entry per shot given, in the same order, echoing "
    "each shot_id verbatim.\n\n"
    + _JSON_DISCIPLINE
)


_SCENE_SCOPE = re.compile(
    r"\b(?:in|for|during)\s+(?P<scope>(?:the\s+)?(?:final|last|first|opening)\s+scene|scene\s+\d+)\b",
    re.IGNORECASE,
)


def _scoped_guidance(extra_guidance: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Separate cross-shot invariants from explicitly scene-scoped clauses."""
    global_items: list[str] = []
    scene_items: list[tuple[str, str]] = []
    for clause in re.findall(r"[^.!?]+[.!?]?", extra_guidance.strip()):
        clause = clause.strip()
        if not clause:
            continue
        match = _SCENE_SCOPE.search(clause)
        if match is None:
            global_items.append(clause)
            continue
        direction = (clause[: match.start()] + clause[match.end() :]).strip(" ,.;")
        scope = re.sub(r"^the\s+", "", match.group("scope"), flags=re.IGNORECASE).lower()
        scene_items.append((scope, direction))
    return global_items, scene_items


def _shot_line(shot: dict[str, Any]) -> str:
    return (
        f"- shot_id={shot.get('id', '')} | scene='{shot.get('scene_title', '')}' "
        f"| order={shot.get('order', 0)} "
        f"| mode={shot.get('generation_mode', 'image')} "
        f"| duration={shot.get('planned_duration_sec', 0):g}s\n"
        f"    framing: {shot.get('shot_type', '')}, {shot.get('camera_angle', '')}, "
        f"{shot.get('camera_movement', '')}, {shot.get('lens_framing', '')}\n"
        f"    subject: {shot.get('subject', '')}\n"
        f"    action: {shot.get('action', '')}\n"
        f"    environment: {shot.get('environment', '')}\n"
        f"    dialogue: {shot.get('dialogue', '')}\n"
        f"    scene context: {shot.get('scene_summary', '')} "
        f"({shot.get('scene_time_of_day', '')}; {shot.get('scene_emotional_beat', '')})"
    )


def build_shot_prompts_prompt(
    project: dict[str, Any],
    shots: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    styles: list[dict[str, Any]],
    extra_guidance: str = "",
) -> str:
    """The user message for prompt compilation."""
    parts = [
        _project_context(project),
        "",
        _story_bible_context(characters, locations, styles),
        "",
        f"SHOTS TO COMPILE ({len(shots)})",
        "\n".join(_shot_line(shot) for shot in shots),
    ]
    if extra_guidance.strip():
        global_items, scene_items = _scoped_guidance(extra_guidance)
        if global_items:
            parts += ["", "GLOBAL INVARIANTS", "\n".join(global_items)]
        if scene_items:
            parts += [
                "",
                "SCENE-SPECIFIC DIRECTION",
                "\n".join(f"- {scope}: {direction}" for scope, direction in scene_items),
                "Never copy scene-specific direction into other scenes.",
            ]
    return "\n".join(parts)
