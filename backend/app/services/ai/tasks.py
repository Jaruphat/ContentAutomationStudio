"""
The AI story tasks, from project state to persisted rows.

Three tasks, all the same shape: read the project and its story bible, render a
versioned prompt, ask a provider for schema-valid JSON, then either return the
draft or write it to the database.

Two rules run through all of them.

**Nothing is written until the response has validated.** The provider layer
only returns data that satisfies the task's JSON Schema, so by the time a
function here touches the ORM the shape is already guaranteed. What is still
checked here is everything the schema cannot express: that an echoed shot id
belongs to this project, that a character name matches a real bible entry, that
a duration adds up. A model that invents an id gets that entry dropped and a
warning, never a write to a row it was not given.

**Applying is opt-in and never silently destructive.** ``apply=False`` returns
the draft for review, which is the default the UI uses first. Replacing an
existing storyboard requires ``replace_existing=True``; without it a project
that already has scenes is refused rather than overwritten, because the scenes
may hold approved takes.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Character, Location, Project, Scene, Shot, Style
from app.services.ai.base import AIProvider, AIProviderError, StructuredRequest, StructuredResult
from app.services.ai.prompts import (
    PROMPT_VERSIONS,
    SCENE_DECOMPOSITION_SYSTEM,
    SHOT_PROMPTS_SYSTEM,
    STORY_BIBLE_SYSTEM,
    build_scene_decomposition_prompt,
    build_shot_prompts_prompt,
    build_story_bible_prompt,
)
from app.services.ai.task_schemas import SCHEMA_VERSIONS, TASK_SCHEMAS
from app.services.ai.validation import SchemaViolation, validate_object

logger = logging.getLogger("cas.ai.tasks")

#: Guard rails on what a single request may ask for. A storyboard far outside
#: this band would not fit one response and would be cut off mid-JSON.
MAX_SCENES = 20
MAX_SHOTS = 120
#: Compiling prompts for a very large storyboard in one call risks the same
#: truncation, so the caller is asked to select a subset instead.
MAX_SHOTS_PER_COMPILE = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AITaskError(RuntimeError):
    """A task could not be completed for a reason that is not the provider's.

    ``category`` mirrors :class:`AIProviderError` so the router has one mapping
    from category to HTTP status regardless of which layer failed.
    """

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category
        self.message = message


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class TaskOutcome:
    """What a task produced, and what it did with it."""

    task: str
    #: The validated model output, exactly as returned.
    data: dict[str, Any]
    provenance: dict[str, Any]
    #: True when the draft was written to the database.
    applied: bool = False
    #: Counts of what was created or updated. Empty when applied is False.
    summary: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    #: The model's own notes to the writer, lifted out of ``data``.
    notes: str = ""
    #: Durable audit identifiers populated by the HTTP orchestration layer.
    preview_revision_id: str = ""
    preview_sha256: str = ""
    applied_revision_id: str = ""
    applied_sha256: str = ""


def _provenance(result: StructuredResult, provider: AIProvider) -> dict[str, Any]:
    """Everything needed to explain or reproduce a generation.

    ``mock`` is carried explicitly rather than inferred from the provider id by
    the reader, so a stored or displayed record cannot be mistaken for authored
    output.
    """
    return {
        "source": "generated",
        "provider_id": result.provider_id,
        "model": result.model,
        "mock": getattr(provider, "id", "") == "mock",
        "prompt_version": result.prompt_version,
        "schema_version": result.schema_version,
        "attempts": result.attempts,
        "latency_ms": result.latency_ms,
        "usage": result.usage.as_dict(),
        "response_id": result.response_id,
        "generated_at": _utcnow().isoformat(),
    }


def _reviewed_draft(task: str, draft: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a draft the user is applying, and describe where it came from.

    The preview a user approves is applied verbatim rather than regenerated:
    asking the provider a second time would write something the user never
    saw, and would bill them twice for one decision. The draft still passes the
    task's JSON Schema - arriving over the wire earns it no trust - and its
    provenance is marked ``reviewed_draft`` so no record implies a generation
    that did not happen at apply time.
    """
    try:
        data = validate_object(dict(draft), TASK_SCHEMAS[task])
    except SchemaViolation as exc:
        raise AITaskError(
            "bad_request",
            f"The draft sent for '{task}' does not match the task schema and "
            f"was not applied: {exc}",
        ) from exc

    return data, {
        "source": "reviewed_draft",
        "provider_id": "",
        "model": "",
        "mock": False,
        "prompt_version": PROMPT_VERSIONS[task],
        "schema_version": SCHEMA_VERSIONS[task],
        "attempts": 0,
        "latency_ms": 0,
        "usage": {},
        "response_id": "",
        "generated_at": _utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Reading project state
# ---------------------------------------------------------------------------

def _project_context(project: Project) -> dict[str, Any]:
    return {
        "title": project.title,
        "objective": project.objective,
        "audience": project.audience,
        "content_type": project.content_type,
        "aspect_ratio": project.aspect_ratio,
        "target_resolution": project.target_resolution,
        "target_duration_sec": project.target_duration_sec,
        "frame_rate": project.frame_rate,
        "language": project.language,
    }


def _bible(db: Session, project_id: str) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]
]:
    """Characters, locations and styles as plain dicts for the templates."""
    characters = [
        {
            "id": c.id, "name": c.name, "role": c.role, "age_range": c.age_range,
            "appearance": c.appearance, "clothing": c.clothing,
            "color_palette": c.color_palette, "personality": c.personality,
            "prompt_tokens": c.prompt_tokens,
        }
        for c in db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at)
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
        .order_by(Location.created_at)
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
        .order_by(Style.created_at)
        .all()
    ]
    return characters, locations, styles


def _require_source_text(project: Project) -> tuple[str, str]:
    """The brief and plot, refusing when both are empty.

    Either one alone is enough - a brief with no plot is the common starting
    point - but with neither there is nothing to decompose, and a model asked
    to work from nothing invents a story that has no relationship to the
    project.
    """
    brief = (project.brief_text or "").strip()
    plot = (project.plot_text or "").strip()
    if not brief and not plot:
        raise AITaskError(
            "bad_request",
            "This project has neither a creative brief nor a plot. Write at "
            "least one on the Story page before generating.",
        )
    return brief, plot


# ---------------------------------------------------------------------------
# Task 1: story bible
# ---------------------------------------------------------------------------

async def generate_story_bible(
    db: Session,
    project: Project,
    #: None is allowed only when a reviewed draft is being applied: that path
    #: writes what the user already approved and calls no provider.
    provider: AIProvider | None,
    *,
    guidance: str = "",
    apply: bool = False,
    draft: dict[str, Any] | None = None,
) -> TaskOutcome:
    """Extract characters, locations and a visual style from brief and plot.

    Applying merges by name: an existing character keeps its id and gains the
    new detail, so scenes already referencing it stay valid.
    """
    if apply and draft is not None:
        data, provenance = _reviewed_draft("story_bible", draft)
        return TaskOutcome(
            task="story_bible",
            data=data,
            provenance=provenance,
            applied=True,
            summary=_apply_story_bible(db, project, data),
            notes=str(data.get("notes") or ""),
        )

    brief, plot = _require_source_text(project)
    characters, locations, styles = _bible(db, project.id)

    request = StructuredRequest(
        task="story_bible",
        system_prompt=STORY_BIBLE_SYSTEM,
        user_prompt=build_story_bible_prompt(
            _project_context(project), brief, plot,
            characters, locations, styles, guidance,
        ),
        schema_name="story_bible",
        json_schema=TASK_SCHEMAS["story_bible"],
        prompt_version=PROMPT_VERSIONS["story_bible"],
        schema_version=SCHEMA_VERSIONS["story_bible"],
        model=provider.model,
    )
    result = await provider.complete_structured(request)

    outcome = TaskOutcome(
        task="story_bible",
        data=result.data,
        provenance=_provenance(result, provider),
        warnings=list(result.warnings),
        notes=str(result.data.get("notes") or ""),
    )
    if apply:
        outcome.summary = _apply_story_bible(db, project, result.data)
        outcome.applied = True
    return outcome


def _apply_story_bible(
    db: Session, project: Project, data: dict[str, Any]
) -> dict[str, int]:
    """Merge a generated bible into the project, matching on name."""
    summary = {
        "characters_created": 0, "characters_updated": 0,
        "locations_created": 0, "locations_updated": 0,
        "styles_created": 0, "styles_updated": 0,
    }

    existing_characters = {
        c.name.strip().lower(): c
        for c in db.query(Character).filter(Character.project_id == project.id).all()
    }
    for entry in data.get("characters") or []:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        character = existing_characters.get(name.lower())
        if character is None:
            character = Character(id=str(uuid.uuid4()), project_id=project.id, name=name)
            db.add(character)
            existing_characters[name.lower()] = character
            summary["characters_created"] += 1
        else:
            summary["characters_updated"] += 1
        for column in (
            "role", "age_range", "appearance", "clothing", "color_palette",
            "personality", "prompt_tokens",
        ):
            value = str(entry.get(column) or "").strip()
            # An empty field in the response is "nothing to add", not "erase
            # what the user wrote".
            if value:
                setattr(character, column, value)
        character.updated_at = _utcnow()

    existing_locations = {
        loc.name.strip().lower(): loc
        for loc in db.query(Location).filter(Location.project_id == project.id).all()
    }
    for entry in data.get("locations") or []:
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        location = existing_locations.get(name.lower())
        if location is None:
            location = Location(id=str(uuid.uuid4()), project_id=project.id, name=name)
            db.add(location)
            existing_locations[name.lower()] = location
            summary["locations_created"] += 1
        else:
            summary["locations_updated"] += 1
        for column in (
            "description", "geography", "time_of_day", "palette", "lighting",
            "props",
        ):
            value = str(entry.get(column) or "").strip()
            if value:
                setattr(location, column, value)
        location.updated_at = _utcnow()

    style_entry = data.get("style") or {}
    if any(str(v or "").strip() for v in style_entry.values()):
        # The schema returns one style; the project holds a list. The first
        # existing row is the project's style, so it is updated rather than
        # accumulating a near-duplicate on every run.
        style = (
            db.query(Style)
            .filter(Style.project_id == project.id)
            .order_by(Style.created_at)
            .first()
        )
        if style is None:
            style = Style(id=str(uuid.uuid4()), project_id=project.id)
            db.add(style)
            summary["styles_created"] += 1
        else:
            summary["styles_updated"] += 1
        for column in (
            "medium", "genre", "visual_keywords", "camera_language", "palette",
            "lighting_rules", "negative_constraints",
        ):
            value = str(style_entry.get(column) or "").strip()
            if value:
                setattr(style, column, value)
        style.updated_at = _utcnow()

    project.updated_at = _utcnow()
    db.commit()
    return summary


# ---------------------------------------------------------------------------
# Task 2: scenes and shots
# ---------------------------------------------------------------------------

async def generate_storyboard(
    db: Session,
    project: Project,
    #: None is allowed only when a reviewed draft is being applied: that path
    #: writes what the user already approved and calls no provider.
    provider: AIProvider | None,
    *,
    scene_count: int = 3,
    min_shots: int = 9,
    max_shots: int = 15,
    guidance: str = "",
    apply: bool = False,
    replace_existing: bool = False,
    draft: dict[str, Any] | None = None,
) -> TaskOutcome:
    """Decompose the brief and plot into scenes and shots."""
    if not 1 <= scene_count <= MAX_SCENES:
        raise AITaskError(
            "bad_request",
            f"scene_count must be between 1 and {MAX_SCENES}, got {scene_count}.",
        )
    if min_shots < 1 or max_shots < min_shots or max_shots > MAX_SHOTS:
        raise AITaskError(
            "bad_request",
            f"Shot range must satisfy 1 <= min_shots <= max_shots <= "
            f"{MAX_SHOTS}, got {min_shots}-{max_shots}.",
        )

    brief, plot = _require_source_text(project)

    existing_scenes = (
        db.query(Scene).filter(Scene.project_id == project.id).count()
    )
    if apply and existing_scenes and not replace_existing:
        raise AITaskError(
            "conflict",
            f"This project already has {existing_scenes} scene(s). Generating "
            f"would discard them along with their shots, jobs and takes. "
            f"Re-run with replace_existing set to true to confirm, or preview "
            f"the draft without applying it.",
        )

    if apply and draft is not None:
        data, provenance = _reviewed_draft("scene_decomposition", draft)
        summary, apply_warnings = _apply_storyboard(
            db, project, data.get("scenes") or [], replace_existing,
        )
        return TaskOutcome(
            task="scene_decomposition",
            data=data,
            provenance=provenance,
            applied=True,
            summary=summary,
            warnings=apply_warnings,
            notes=str(data.get("notes") or ""),
        )

    characters, locations, styles = _bible(db, project.id)

    request = StructuredRequest(
        task="scene_decomposition",
        system_prompt=SCENE_DECOMPOSITION_SYSTEM,
        user_prompt=build_scene_decomposition_prompt(
            _project_context(project), brief, plot,
            characters, locations, styles,
            scene_count, min_shots, max_shots, guidance,
        ),
        schema_name="scene_decomposition",
        json_schema=TASK_SCHEMAS["scene_decomposition"],
        prompt_version=PROMPT_VERSIONS["scene_decomposition"],
        schema_version=SCHEMA_VERSIONS["scene_decomposition"],
        model=provider.model,
    )
    result = await provider.complete_structured(request)

    scenes = result.data.get("scenes") or []
    warnings = list(result.warnings)
    if len(scenes) != scene_count:
        warnings.append(
            f"Asked for {scene_count} scenes, the model returned {len(scenes)}."
        )
    shot_total = sum(len(scene.get("shots") or []) for scene in scenes)
    if not min_shots <= shot_total <= max_shots:
        warnings.append(
            f"Asked for {min_shots}-{max_shots} shots in total, the model "
            f"returned {shot_total}."
        )

    outcome = TaskOutcome(
        task="scene_decomposition",
        data=result.data,
        provenance=_provenance(result, provider),
        warnings=warnings,
        notes=str(result.data.get("notes") or ""),
    )
    if apply:
        summary, apply_warnings = _apply_storyboard(
            db, project, scenes, replace_existing,
        )
        outcome.summary = summary
        outcome.warnings.extend(apply_warnings)
        outcome.applied = True
    return outcome


def _apply_storyboard(
    db: Session,
    project: Project,
    scenes: list[dict[str, Any]],
    replace_existing: bool,
) -> tuple[dict[str, int], list[str]]:
    """Write generated scenes and shots, replacing the old ones when asked."""
    warnings: list[str] = []
    summary = {"scenes_deleted": 0, "scenes_created": 0, "shots_created": 0}

    if replace_existing:
        old = db.query(Scene).filter(Scene.project_id == project.id).all()
        summary["scenes_deleted"] = len(old)
        for scene in old:
            # Cascades to shots, and from shots to their jobs and takes.
            db.delete(scene)
        db.flush()

    characters = {
        c.name.strip().lower(): c.id
        for c in db.query(Character).filter(Character.project_id == project.id).all()
    }
    locations = {
        loc.name.strip().lower(): loc.id
        for loc in db.query(Location).filter(Location.project_id == project.id).all()
    }

    # Continue after any scenes that survived, so a non-replacing apply appends
    # rather than colliding on order.
    base_order = 0
    if not replace_existing:
        highest = (
            db.query(Scene.order)
            .filter(Scene.project_id == project.id)
            .order_by(Scene.order.desc())
            .first()
        )
        base_order = (highest[0] + 1) if highest else 0

    for scene_index, entry in enumerate(scenes):
        character_ids: list[str] = []
        for name in entry.get("character_names") or []:
            key = str(name).strip().lower()
            if key in characters:
                character_ids.append(characters[key])
            elif key:
                # Recorded, not created: inventing a bible entry from a bare
                # name would produce a character with no description, which is
                # worse for prompt compilation than no link at all.
                warnings.append(
                    f"Scene {scene_index + 1} references character '{name}', "
                    f"which is not in the story bible. The link was skipped; "
                    f"generate the story bible first to connect them."
                )

        location_name = str(entry.get("location_name") or "").strip()
        location_id = locations.get(location_name.lower())
        if location_name and location_id is None:
            warnings.append(
                f"Scene {scene_index + 1} references location "
                f"'{location_name}', which is not in the story bible. The link "
                f"was skipped."
            )

        shot_entries = entry.get("shots") or []
        # Durations are derived, so they are recomputed from the shots rather
        # than trusted: the model's own sum is frequently a few seconds out.
        shot_duration_total = sum(
            float(s.get("planned_duration_sec") or 0.0) for s in shot_entries
        )

        scene = Scene(
            id=str(uuid.uuid4()),
            project_id=project.id,
            order=base_order + scene_index,
            title=str(entry.get("title") or "").strip(),
            purpose=str(entry.get("purpose") or "").strip(),
            summary=str(entry.get("summary") or "").strip(),
            character_ids=character_ids,
            location_id=location_id,
            time_of_day=str(entry.get("time_of_day") or "").strip(),
            emotional_beat=str(entry.get("emotional_beat") or "").strip(),
            planned_duration_sec=shot_duration_total,
            status="Draft",
        )
        db.add(scene)
        db.flush()
        summary["scenes_created"] += 1

        for shot_index, shot_entry in enumerate(shot_entries):
            mode = str(shot_entry.get("generation_mode") or "image").strip()
            video_prompt = str(shot_entry.get("video_prompt") or "").strip()
            if mode == "image" and video_prompt:
                # The schema cannot express "empty when mode is image"; drop it
                # rather than carry motion text into a still.
                video_prompt = ""
            db.add(Shot(
                id=str(uuid.uuid4()),
                scene_id=scene.id,
                order=shot_index,
                shot_type=str(shot_entry.get("shot_type") or "").strip(),
                camera_angle=str(shot_entry.get("camera_angle") or "").strip(),
                camera_movement=str(shot_entry.get("camera_movement") or "").strip(),
                lens_framing=str(shot_entry.get("lens_framing") or "").strip(),
                subject=str(shot_entry.get("subject") or "").strip(),
                action=str(shot_entry.get("action") or "").strip(),
                environment=str(shot_entry.get("environment") or "").strip(),
                dialogue=str(shot_entry.get("dialogue") or "").strip(),
                planned_duration_sec=float(shot_entry.get("planned_duration_sec") or 0.0),
                generation_mode=mode,
                image_prompt=str(shot_entry.get("image_prompt") or "").strip(),
                video_prompt=video_prompt,
                negative_prompt=str(shot_entry.get("negative_prompt") or "").strip(),
                reference_asset_ids=[],
                seed_policy="random",
                status="Draft",
            ))
            summary["shots_created"] += 1

    project.updated_at = _utcnow()
    db.commit()
    return summary, warnings


# ---------------------------------------------------------------------------
# Task 3: prompt compilation
# ---------------------------------------------------------------------------

async def compile_shot_prompts(
    db: Session,
    project: Project,
    #: None is allowed only when a reviewed draft is being applied: that path
    #: writes what the user already approved and calls no provider.
    provider: AIProvider | None,
    *,
    shot_ids: list[str] | None = None,
    guidance: str = "",
    apply: bool = False,
    draft: dict[str, Any] | None = None,
) -> TaskOutcome:
    """Rewrite the image/video/negative prompts for a project's shots.

    ``shot_ids`` selects a subset; omitting it takes every shot in the project,
    in scene then shot order.
    """
    shots = _select_shots(db, project, shot_ids)
    if not shots:
        raise AITaskError(
            "bad_request",
            "This project has no shots to compile prompts for. Generate or add "
            "a storyboard first.",
        )
    if len(shots) > MAX_SHOTS_PER_COMPILE:
        raise AITaskError(
            "bad_request",
            f"{len(shots)} shots is more than one request can compile without "
            f"the response being truncated. Select at most "
            f"{MAX_SHOTS_PER_COMPILE} shots per run.",
        )

    if apply and draft is not None:
        data, provenance = _reviewed_draft("shot_prompts", draft)
        summary, apply_warnings = _apply_shot_prompts(
            db, project, shots, data.get("prompts") or [],
        )
        return TaskOutcome(
            task="shot_prompts",
            data=data,
            provenance=provenance,
            applied=True,
            summary=summary,
            warnings=apply_warnings,
            notes=str(data.get("notes") or ""),
        )

    characters, locations, styles = _bible(db, project.id)
    shot_payload = [_shot_for_prompt(shot, scene) for shot, scene in shots]

    request = StructuredRequest(
        task="shot_prompts",
        system_prompt=SHOT_PROMPTS_SYSTEM,
        user_prompt=build_shot_prompts_prompt(
            _project_context(project), shot_payload,
            characters, locations, styles, guidance,
        ),
        schema_name="shot_prompts",
        json_schema=TASK_SCHEMAS["shot_prompts"],
        prompt_version=PROMPT_VERSIONS["shot_prompts"],
        schema_version=SCHEMA_VERSIONS["shot_prompts"],
        model=provider.model,
    )
    result = await provider.complete_structured(request)

    outcome = TaskOutcome(
        task="shot_prompts",
        data=result.data,
        provenance=_provenance(result, provider),
        warnings=list(result.warnings),
        notes=str(result.data.get("notes") or ""),
    )
    if apply:
        summary, apply_warnings = _apply_shot_prompts(
            db, project, shots, result.data.get("prompts") or [],
        )
        outcome.summary = summary
        outcome.warnings.extend(apply_warnings)
        outcome.applied = True
    return outcome


def _select_shots(
    db: Session, project: Project, shot_ids: list[str] | None
) -> list[tuple[Shot, Scene]]:
    """The project's shots, optionally filtered, in storyboard order.

    Joining through Scene is what confines the selection to this project: an id
    from another project simply does not come back.
    """
    query = (
        db.query(Shot, Scene)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Scene.project_id == project.id)
    )
    if shot_ids:
        query = query.filter(Shot.id.in_(list(shot_ids)))
    return query.order_by(Scene.order, Shot.order).all()


def _shot_for_prompt(shot: Shot, scene: Scene) -> dict[str, Any]:
    return {
        "id": shot.id,
        "order": shot.order,
        "shot_type": shot.shot_type,
        "camera_angle": shot.camera_angle,
        "camera_movement": shot.camera_movement,
        "lens_framing": shot.lens_framing,
        "subject": shot.subject,
        "action": shot.action,
        "environment": shot.environment,
        "dialogue": shot.dialogue,
        "planned_duration_sec": shot.planned_duration_sec or 0.0,
        "generation_mode": shot.generation_mode,
        "scene_title": scene.title,
        "scene_summary": scene.summary,
        "scene_time_of_day": scene.time_of_day,
        "scene_emotional_beat": scene.emotional_beat,
    }


def _deduplicate_prompt_fragments(value: str) -> str:
    """Remove repeated comma/semicolon prompt fragments without reordering."""
    seen: set[str] = set()
    unique: list[str] = []
    for fragment in re.split(r"[,;]", value):
        cleaned = fragment.strip()
        key = " ".join(cleaned.casefold().split())
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return ", ".join(unique)


def _apply_shot_prompts(
    db: Session,
    project: Project,
    shots: list[tuple[Shot, Scene]],
    prompts: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str]]:
    """Write compiled prompts back, keyed by the shot id the model echoed."""
    warnings: list[str] = []
    summary = {"shots_updated": 0, "prompts_ignored": 0, "shots_missing": 0}

    by_id = {shot.id: shot for shot, _scene in shots}
    seen: set[str] = set()

    for entry in prompts:
        shot_id = str(entry.get("shot_id") or "").strip()
        shot = by_id.get(shot_id)
        if shot is None:
            # An id that was not in the request. Ignored rather than matched by
            # position: a shifted response would otherwise write every prompt
            # onto the wrong shot.
            summary["prompts_ignored"] += 1
            continue
        if shot_id in seen:
            summary["prompts_ignored"] += 1
            continue
        seen.add(shot_id)

        image_prompt = _deduplicate_prompt_fragments(
            str(entry.get("image_prompt") or "")
        )
        video_prompt = _deduplicate_prompt_fragments(
            str(entry.get("video_prompt") or "")
        )
        negative_prompt = _deduplicate_prompt_fragments(
            str(entry.get("negative_prompt") or "")
        )

        if image_prompt:
            shot.image_prompt = image_prompt
        if shot.generation_mode == "image":
            video_prompt = ""
        shot.video_prompt = video_prompt
        shot.negative_prompt = negative_prompt
        shot.updated_at = _utcnow()
        summary["shots_updated"] += 1

    missing = [shot.id for shot in by_id.values() if shot.id not in seen]
    summary["shots_missing"] = len(missing)
    if missing:
        warnings.append(
            f"{len(missing)} shot(s) came back with no prompt and were left "
            f"unchanged."
        )
    if summary["prompts_ignored"]:
        warnings.append(
            f"{summary['prompts_ignored']} returned prompt(s) named a shot id "
            f"that was not in the request and were ignored."
        )

    project.updated_at = _utcnow()
    db.commit()
    return summary, warnings


__all__ = [
    "AIProviderError",
    "AITaskError",
    "MAX_SCENES",
    "MAX_SHOTS",
    "MAX_SHOTS_PER_COMPILE",
    "TaskOutcome",
    "compile_shot_prompts",
    "generate_storyboard",
    "generate_story_bible",
]
