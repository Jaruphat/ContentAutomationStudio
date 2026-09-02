"""
JSON Schemas for the AI-authored parts of a project.

These are the contract between the model and the database. Every schema is
written to satisfy OpenAI's strict structured-output rules - every object sets
``additionalProperties: false`` and lists every property in ``required`` - so
the same document can be handed to a vendor that enforces it server-side and to
the local validator, with no second, looser variant to drift out of sync.

Fields map onto the ORM deliberately: a scene here is a ``Scene`` row and a shot
is a ``Shot`` row. Anything the model should not invent - ids, timestamps,
status, workflow bindings - is absent, so a malicious or confused response
cannot reach those columns.

Bump ``SCHEMA_VERSIONS`` whenever a shape changes; the version is recorded with
every generation so an old artifact stays interpretable.
"""

from typing import Any

SCHEMA_VERSIONS: dict[str, str] = {
    "scene_decomposition": "1.0",
    "story_bible": "1.0",
    "shot_prompts": "1.0",
}

#: Enumerations kept narrow so the model returns values the rest of the app
#: already understands rather than free text that needs mapping later.
GENERATION_MODES = ["image", "video", "image-to-video"]


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    """A strict-mode object: closed, with every property required."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Scene / shot decomposition
# ---------------------------------------------------------------------------

SHOT_PROPERTIES: dict[str, Any] = {
    "order": {
        "type": "integer",
        "description": "Zero-based position of this shot within its scene.",
    },
    "shot_type": _string(
        "Framing, e.g. 'wide shot', 'medium close-up', 'over-the-shoulder'."
    ),
    "camera_angle": _string("e.g. 'eye level', 'low angle', 'high angle'."),
    "camera_movement": _string("e.g. 'static', 'slow push in', 'handheld pan left'."),
    "lens_framing": _string("e.g. '35mm, shallow depth of field'."),
    "subject": _string("Who or what the shot is of."),
    "action": _string("What happens during the shot, in one or two sentences."),
    "environment": _string("The visible setting, lighting and atmosphere."),
    "dialogue": _string("Spoken line, or an empty string when the shot is silent."),
    "planned_duration_sec": {
        "type": "number",
        "description": "Intended on-screen duration in seconds.",
    },
    "generation_mode": {
        "type": "string",
        "enum": GENERATION_MODES,
        "description": (
            "'image' for a still, 'video' for text-to-video, 'image-to-video' "
            "when the shot should animate a still from an earlier shot."
        ),
    },
    "image_prompt": _string(
        "Self-contained still-image prompt for this shot: subject, action, "
        "setting, framing, lens and lighting. No negatives, no camera motion."
    ),
    "video_prompt": _string(
        "Self-contained motion prompt: what moves, how the camera moves, and "
        "over what span. Empty string when generation_mode is 'image'."
    ),
    "negative_prompt": _string(
        "What must not appear. Empty string when there is nothing to exclude."
    ),
}

SCENE_PROPERTIES: dict[str, Any] = {
    "order": {"type": "integer", "description": "Zero-based scene position."},
    "title": _string("Short scene title."),
    "purpose": _string("What this scene accomplishes in the story."),
    "summary": _string("What happens in the scene, in two or three sentences."),
    "time_of_day": _string("e.g. 'golden hour', 'night', 'overcast morning'."),
    "emotional_beat": _string("The emotional turn this scene delivers."),
    "planned_duration_sec": {
        "type": "number",
        "description": "Sum of the scene's shot durations, in seconds.",
    },
    "character_names": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Names of characters appearing in this scene. Must match names "
            "given in the story bible section of the request."
        ),
    },
    "location_name": _string(
        "Name of the location, matching the story bible where one applies."
    ),
    "shots": {
        "type": "array",
        "items": _object(SHOT_PROPERTIES),
        "description": "The shots that make up this scene, in order.",
    },
}

SCENE_DECOMPOSITION_SCHEMA: dict[str, Any] = _object({
    "scenes": {
        "type": "array",
        "items": _object(SCENE_PROPERTIES),
        "description": "The scenes, in narrative order.",
    },
    "notes": _string(
        "Anything the writer should know: assumptions made, ambiguities in the "
        "brief, or an empty string."
    ),
})


# ---------------------------------------------------------------------------
# Story bible extraction
# ---------------------------------------------------------------------------

CHARACTER_PROPERTIES: dict[str, Any] = {
    "name": _string("Character name, used to reference them from scenes."),
    "role": _string("Their role in the story, e.g. 'protagonist'."),
    "age_range": _string("e.g. 'late 20s'."),
    "appearance": _string("Physical description stable across every shot."),
    "clothing": _string("Wardrobe, stable across the piece unless the plot changes it."),
    "color_palette": _string("Colours associated with this character."),
    "personality": _string("Temperament, in a phrase or two."),
    "prompt_tokens": _string(
        "Comma-separated visual tokens repeated in every prompt featuring this "
        "character, to hold their appearance consistent between shots."
    ),
}

LOCATION_PROPERTIES: dict[str, Any] = {
    "name": _string("Location name, used to reference it from scenes."),
    "description": _string("What the place looks like."),
    "geography": _string("Where it sits and what surrounds it."),
    "time_of_day": _string("Default time of day for this location."),
    "palette": _string("Dominant colours."),
    "lighting": _string("Characteristic lighting."),
    "props": _string("Recurring objects that should stay consistent."),
}

STYLE_PROPERTIES: dict[str, Any] = {
    "medium": _string("e.g. 'live-action cinematography', '3D animation'."),
    "genre": _string("e.g. 'documentary realism', 'noir thriller'."),
    "visual_keywords": _string("Comma-separated look tokens applied to every shot."),
    "camera_language": _string("The piece's camera grammar."),
    "palette": _string("Overall colour palette."),
    "lighting_rules": _string("Lighting conventions held across the piece."),
    "negative_constraints": _string(
        "Comma-separated things that must never appear in any shot."
    ),
}

STORY_BIBLE_SCHEMA: dict[str, Any] = _object({
    "characters": {
        "type": "array",
        "items": _object(CHARACTER_PROPERTIES),
        "description": "Characters the brief and plot imply. May be empty.",
    },
    "locations": {
        "type": "array",
        "items": _object(LOCATION_PROPERTIES),
        "description": "Locations the brief and plot imply. May be empty.",
    },
    "style": _object(STYLE_PROPERTIES),
    "notes": _string("Assumptions or ambiguities, or an empty string."),
})


# ---------------------------------------------------------------------------
# Shot prompt compilation
# ---------------------------------------------------------------------------

SHOT_PROMPT_PROPERTIES: dict[str, Any] = {
    "shot_id": _string(
        "The id given for this shot in the request. Copy it exactly; do not "
        "invent ids and do not reorder."
    ),
    "image_prompt": _string("Compiled still-image prompt for this shot."),
    "video_prompt": _string(
        "Compiled motion prompt, or an empty string for a still-only shot."
    ),
    "negative_prompt": _string("What must not appear, or an empty string."),
    "rationale": _string(
        "One sentence on how the story bible shaped this prompt, for the "
        "reviewer. Not sent to the image model."
    ),
}

SHOT_PROMPTS_SCHEMA: dict[str, Any] = _object({
    "prompts": {
        "type": "array",
        "items": _object(SHOT_PROMPT_PROPERTIES),
        "description": "One entry per shot in the request, same order.",
    },
    "notes": _string("Anything the writer should know, or an empty string."),
})


TASK_SCHEMAS: dict[str, dict[str, Any]] = {
    "scene_decomposition": SCENE_DECOMPOSITION_SCHEMA,
    "story_bible": STORY_BIBLE_SCHEMA,
    "shot_prompts": SHOT_PROMPTS_SCHEMA,
}
