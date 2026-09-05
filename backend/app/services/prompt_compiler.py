"""
Prompt Compiler Service.

Compiles layered prompts
from Story Bible (characters, locations, styles)
combined with scene context and shot-level data, following PRD section 9.1.

Prompt layers:
  1. Global style prompt
  2. Character constraints
  3. Location constraints
  4. Scene context
  5. Shot camera/framing
  6. Action and expression
  7. Technical generation tokens
  8. Negative prompt
"""

from dataclasses import dataclass, field
from typing import Any

from app.services import motion_direction


@dataclass
class CompiledPrompt:
    """Result of prompt compilation with full layer breakdown."""

    positive_prompt: str
    negative_prompt: str
    layers: dict[str, str] = field(default_factory=dict)


def _join_nonempty(*parts: str) -> str:
    """Join non-empty strings with comma-space separator."""
    return ", ".join(p.strip() for p in parts if p and p.strip())


def _deduplicate_fragments(value: str) -> str:
    """Deduplicate comma/semicolon fragments, preserving first-seen order."""
    seen: set[str] = set()
    unique: list[str] = []
    for fragment in value.replace(";", ",").split(","):
        cleaned = fragment.strip()
        key = " ".join(cleaned.casefold().split())
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return ", ".join(unique)


def compile_prompt(
    shot: dict[str, Any],
    scene: dict[str, Any],
    characters: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    styles: list[dict[str, Any]],
) -> CompiledPrompt:
    """
    Build a layered prompt from Story Bible entities, scene context, and shot data.

    Parameters
    ----------
    shot : dict
        Shot record (from ORM or dict) with keys like shot_type, camera_angle,
        camera_movement, lens_framing, subject, action, environment,
        image_prompt, video_prompt, negative_prompt, generation_mode, etc.
    scene : dict
        Scene record with keys like summary, emotional_beat, time_of_day,
        character_ids, location_id.
    characters : list[dict]
        All characters for the project. The compiler filters by scene.character_ids.
    locations : list[dict]
        All locations for the project. The compiler matches scene.location_id.
    styles : list[dict]
        All style records for the project. All are merged into the global layer.

    Returns
    -------
    CompiledPrompt
        Contains the final positive_prompt, negative_prompt, and a dict of
        individual layers.
    """
    layers: dict[str, str] = {}

    # -----------------------------------------------------------------------
    # Layer 1: Global style prompt
    # -----------------------------------------------------------------------
    style_parts: list[str] = []
    for style in styles:
        medium = style.get("medium", "")
        genre = style.get("genre", "")
        visual_keywords = style.get("visual_keywords", "")
        camera_language = style.get("camera_language", "")
        palette = style.get("palette", "")
        lighting_rules = style.get("lighting_rules", "")
        combined = _join_nonempty(medium, genre, visual_keywords, camera_language, palette, lighting_rules)
        if combined:
            style_parts.append(combined)
    layers["global_style"] = ", ".join(style_parts)

    # -----------------------------------------------------------------------
    # Layer 2: Character constraints
    # -----------------------------------------------------------------------
    scene_character_ids = set(scene.get("character_ids", []) or [])
    char_parts: list[str] = []
    for char in characters:
        char_id = char.get("id", "")
        if scene_character_ids and char_id not in scene_character_ids:
            continue
        name = char.get("name", "")
        appearance = char.get("appearance", "")
        clothing = char.get("clothing", "")
        color_palette = char.get("color_palette", "")
        prompt_tokens = char.get("prompt_tokens", "")
        desc = _join_nonempty(name, appearance, clothing, color_palette, prompt_tokens)
        if desc:
            char_parts.append(desc)
    layers["character_constraints"] = "; ".join(char_parts)

    # -----------------------------------------------------------------------
    # Layer 3: Location constraints
    # -----------------------------------------------------------------------
    scene_location_id = scene.get("location_id", "")
    loc_parts: list[str] = []
    for loc in locations:
        if scene_location_id and loc.get("id", "") != scene_location_id:
            continue
        name = loc.get("name", "")
        description = loc.get("description", "")
        geography = loc.get("geography", "")
        time_of_day = loc.get("time_of_day", "")
        palette = loc.get("palette", "")
        lighting = loc.get("lighting", "")
        props = loc.get("props", "")
        desc = _join_nonempty(name, description, geography, time_of_day, palette, lighting, props)
        if desc:
            loc_parts.append(desc)
    layers["location_constraints"] = "; ".join(loc_parts)

    # -----------------------------------------------------------------------
    # Layer 4: Scene context
    # -----------------------------------------------------------------------
    scene_summary = scene.get("summary", "")
    emotional_beat = scene.get("emotional_beat", "")
    scene_time = scene.get("time_of_day", "")
    layers["scene_context"] = _join_nonempty(scene_summary, emotional_beat, scene_time)

    # -----------------------------------------------------------------------
    # Layer 5: Shot camera/framing
    # -----------------------------------------------------------------------
    shot_type = shot.get("shot_type", "")
    camera_angle = shot.get("camera_angle", "")
    camera_movement = shot.get("camera_movement", "")
    lens_framing = shot.get("lens_framing", "")
    layers["shot_camera"] = _join_nonempty(shot_type, camera_angle, camera_movement, lens_framing)

    # -----------------------------------------------------------------------
    # Layer 6: Action and expression
    # -----------------------------------------------------------------------
    subject = shot.get("subject", "")
    action = shot.get("action", "")
    environment = shot.get("environment", "")
    layers["action_expression"] = _join_nonempty(subject, action, environment)

    # -----------------------------------------------------------------------
    # Layer 7: Technical generation tokens
    # -----------------------------------------------------------------------
    # Use the generation-mode-specific prompt as the primary technical token.
    gen_mode = shot.get("generation_mode", "image")
    if gen_mode == "image":
        tech_prompt = shot.get("image_prompt", "")
    else:
        # What happens leads; how the camera behaves follows. Falls back to
        # the single video prompt so every shot written before these fields
        # existed compiles exactly as it did - an old project must not
        # regenerate into a different film.
        composed = motion_direction.compose(
            subject_motion=shot.get("subject_motion", "") or "",
            camera_motion=shot.get("camera_motion", "") or "",
        )
        tech_prompt = composed or shot.get("video_prompt", "")
    layers["technical_tokens"] = tech_prompt

    # -----------------------------------------------------------------------
    # Layer 8: Negative prompt (kept separate from positive)
    # -----------------------------------------------------------------------
    negative_parts: list[str] = []
    shot_negative = shot.get("negative_prompt", "")
    if shot_negative:
        negative_parts.append(shot_negative)
    for style in styles:
        neg = style.get("negative_constraints", "")
        if neg:
            negative_parts.append(neg)
    layers["negative_prompt"] = ", ".join(negative_parts)

    # -----------------------------------------------------------------------
    # Assemble final prompts
    # -----------------------------------------------------------------------
    positive_layers = [
        layers["global_style"],
        layers["character_constraints"],
        layers["location_constraints"],
        layers["scene_context"],
        layers["shot_camera"],
        layers["action_expression"],
        layers["technical_tokens"],
    ]
    positive_prompt = _deduplicate_fragments(
        ", ".join(part for part in positive_layers if part)
    )
    negative_prompt = _deduplicate_fragments(layers["negative_prompt"])

    return CompiledPrompt(
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        layers=layers,
    )
