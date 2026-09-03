"""
One place that turns a stored shot into a compiled prompt.

Queuing a job, estimating a revision digest and regenerating a shot all need
"what would this shot's prompt be right now?". They used to answer it
separately, which is how a regeneration ended up replaying a previous job's
parameter map instead of recompiling from the shot in front of it. Everything
now reads through :func:`compile_for_shot`, so there is exactly one answer.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import Character, Location, Scene, Shot, Style
from app.services.prompt_compiler import CompiledPrompt, compile_prompt


@dataclass
class ShotPromptContext:
    """A shot's compiled prompt plus the inputs it was compiled from."""

    compiled: CompiledPrompt
    scene: dict[str, Any]
    characters: list[dict[str, Any]]
    locations: list[dict[str, Any]]
    styles: list[dict[str, Any]]


def story_bible(db: Session, project_id: str) -> dict[str, list[dict[str, Any]]]:
    """The project's characters, locations and styles as compiler inputs."""
    characters = [
        {
            "id": c.id, "name": c.name, "role": c.role,
            "appearance": c.appearance, "clothing": c.clothing,
            "color_palette": c.color_palette, "prompt_tokens": c.prompt_tokens,
        }
        for c in db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at, Character.id)
        .all()
    ]
    locations = [
        {
            "id": loc.id, "name": loc.name, "description": loc.description,
            "geography": loc.geography, "time_of_day": loc.time_of_day,
            "palette": loc.palette, "lighting": loc.lighting, "props": loc.props,
        }
        for loc in db.query(Location)
        .filter(Location.project_id == project_id)
        .order_by(Location.created_at, Location.id)
        .all()
    ]
    styles = [
        {
            "id": s.id, "medium": s.medium, "genre": s.genre,
            "visual_keywords": s.visual_keywords,
            "camera_language": s.camera_language, "palette": s.palette,
            "lighting_rules": s.lighting_rules,
            "negative_constraints": s.negative_constraints,
        }
        for s in db.query(Style)
        .filter(Style.project_id == project_id)
        .order_by(Style.created_at, Style.id)
        .all()
    ]
    return {"characters": characters, "locations": locations, "styles": styles}


def scene_input(scene: Scene | None) -> dict[str, Any]:
    return {
        "id": scene.id if scene else "",
        "summary": scene.summary if scene else "",
        "emotional_beat": scene.emotional_beat if scene else "",
        "time_of_day": scene.time_of_day if scene else "",
        "character_ids": list(scene.character_ids or []) if scene else [],
        "location_id": scene.location_id if scene else None,
    }


def shot_input(shot: Shot) -> dict[str, Any]:
    return {
        "id": shot.id,
        "shot_type": shot.shot_type,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "lens_framing": shot.lens_framing,
        "subject": shot.subject,
        "action": shot.action,
        "environment": shot.environment,
        "generation_mode": shot.generation_mode,
        "image_prompt": shot.image_prompt,
        "video_prompt": shot.video_prompt,
        "negative_prompt": shot.negative_prompt,
    }


def compile_for_shot(
    db: Session,
    shot: Shot,
    *,
    scene: Scene | None = None,
    bible: dict[str, list[dict[str, Any]]] | None = None,
) -> ShotPromptContext:
    """Compile a shot's prompt from the project's current state.

    ``scene`` and ``bible`` are accepted so a caller looping over a whole
    project can load the Story Bible once instead of once per shot; omitting
    them is always correct, just slower.
    """
    if scene is None:
        scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
    if bible is None:
        project_id = scene.project_id if scene else ""
        bible = story_bible(db, project_id)

    scene_data = scene_input(scene)
    compiled = compile_prompt(
        shot=shot_input(shot),
        scene=scene_data,
        characters=bible["characters"],
        locations=bible["locations"],
        styles=bible["styles"],
    )
    return ShotPromptContext(
        compiled=compiled,
        scene=scene_data,
        characters=bible["characters"],
        locations=bible["locations"],
        styles=bible["styles"],
    )
