"""
Export Service.

Provides export functions for:
  - Storyboard (JSON / CSV / Markdown)
  - Prompt package (all compiled prompts)
  - Generation manifest (all jobs with provenance)
  - Timeline manifest
  - Project archive (complete metadata dump)
"""

import csv
import io
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Character,
    GenerationJob,
    Location,
    Project,
    Scene,
    Shot,
    Style,
    Take,
    TimelineItem,
)
from app.services.ai.authoring_revisions import project_audit
from app.services.prompt_compiler import compile_prompt

# ---------------------------------------------------------------------------
# Storyboard export
# ---------------------------------------------------------------------------

def _build_storyboard_data(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Build a flat list of shot records with scene context for export."""
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )

    rows: list[dict[str, Any]] = []
    for scene in scenes:
        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        for shot in shots:
            rows.append({
                "scene_order": scene.order,
                "scene_title": scene.title,
                "scene_summary": scene.summary,
                "shot_order": shot.order,
                "shot_id": shot.id,
                "shot_type": shot.shot_type,
                "camera_angle": shot.camera_angle,
                "camera_movement": shot.camera_movement,
                "lens_framing": shot.lens_framing,
                "subject": shot.subject,
                "action": shot.action,
                "environment": shot.environment,
                "dialogue": shot.dialogue,
                "planned_duration_sec": shot.planned_duration_sec,
                "generation_mode": shot.generation_mode,
                "image_provider_id": shot.image_provider_id or "comfyui",
                "image_model": shot.image_model or "workflow",
                "image_prompt": shot.image_prompt,
                "video_prompt": shot.video_prompt,
                "negative_prompt": shot.negative_prompt,
                "status": shot.status,
            })
    return rows


def export_storyboard_json(db: Session, project_id: str) -> dict[str, Any]:
    """Export storyboard as JSON."""
    project = db.query(Project).filter(Project.id == project_id).first()
    rows = _build_storyboard_data(db, project_id)
    return {
        "project_id": project_id,
        "project_title": project.title if project else "",
        "shot_count": len(rows),
        "shots": rows,
    }


def export_storyboard_csv(db: Session, project_id: str) -> str:
    """Export storyboard as CSV string."""
    rows = _build_storyboard_data(db, project_id)
    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def export_storyboard_markdown(db: Session, project_id: str) -> str:
    """Export storyboard as Markdown table."""
    project = db.query(Project).filter(Project.id == project_id).first()
    rows = _build_storyboard_data(db, project_id)

    lines: list[str] = []
    lines.append(f"# Storyboard: {project.title if project else project_id}")
    lines.append("")

    if not rows:
        lines.append("_No shots defined._")
        return "\n".join(lines)

    # Table header
    headers = [
        "Scene", "Shot", "Type", "Camera", "Subject",
        "Action", "Duration", "Mode", "Status",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for row in rows:
        cells = [
            f"S{row['scene_order']}: {row['scene_title']}",
            str(row["shot_order"]),
            row["shot_type"],
            f"{row['camera_angle']} {row['camera_movement']}".strip(),
            row["subject"][:50],
            row["action"][:50],
            f"{row['planned_duration_sec']:.1f}s",
            row["generation_mode"],
            row["status"],
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")

    # Detailed prompt section
    lines.append("## Prompts")
    lines.append("")
    for row in rows:
        lines.append(f"### Scene {row['scene_order']} - Shot {row['shot_order']}")
        lines.append("")
        if row["image_prompt"]:
            lines.append(f"**Image Prompt:** {row['image_prompt']}")
            lines.append("")
        if row["video_prompt"]:
            lines.append(f"**Video Prompt:** {row['video_prompt']}")
            lines.append("")
        if row["negative_prompt"]:
            lines.append(f"**Negative:** {row['negative_prompt']}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt package export
# ---------------------------------------------------------------------------

def export_prompts(db: Session, project_id: str) -> dict[str, Any]:
    """
    Export all compiled prompts for a project.

    Compiles each shot's prompt using the full Story Bible context.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"project_id": project_id, "error": "Project not found"}

    characters = [
        {
            "id": c.id, "name": c.name, "role": c.role,
            "appearance": c.appearance, "clothing": c.clothing,
            "color_palette": c.color_palette, "prompt_tokens": c.prompt_tokens,
        }
        for c in db.query(Character).filter(Character.project_id == project_id).all()
    ]
    locations = [
        {
            "id": loc.id, "name": loc.name, "description": loc.description,
            "geography": loc.geography, "time_of_day": loc.time_of_day,
            "palette": loc.palette, "lighting": loc.lighting, "props": loc.props,
        }
        for loc in db.query(Location).filter(Location.project_id == project_id).all()
    ]
    styles = [
        {
            "id": s.id, "medium": s.medium, "genre": s.genre,
            "visual_keywords": s.visual_keywords, "camera_language": s.camera_language,
            "palette": s.palette, "lighting_rules": s.lighting_rules,
            "negative_constraints": s.negative_constraints,
        }
        for s in db.query(Style).filter(Style.project_id == project_id).all()
    ]

    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )

    prompt_entries: list[dict[str, Any]] = []

    for scene in scenes:
        scene_dict = {
            "id": scene.id, "summary": scene.summary,
            "emotional_beat": scene.emotional_beat,
            "time_of_day": scene.time_of_day,
            "character_ids": scene.character_ids or [],
            "location_id": scene.location_id,
        }

        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        for shot in shots:
            shot_dict = {
                "id": shot.id, "shot_type": shot.shot_type,
                "camera_angle": shot.camera_angle,
                "camera_movement": shot.camera_movement,
                "lens_framing": shot.lens_framing,
                "subject": shot.subject, "action": shot.action,
                "environment": shot.environment,
                "generation_mode": shot.generation_mode,
                "image_prompt": shot.image_prompt,
                "video_prompt": shot.video_prompt,
                "negative_prompt": shot.negative_prompt,
            }

            compiled = compile_prompt(
                shot=shot_dict,
                scene=scene_dict,
                characters=characters,
                locations=locations,
                styles=styles,
            )

            prompt_entries.append({
                "scene_order": scene.order,
                "scene_title": scene.title,
                "shot_order": shot.order,
                "shot_id": shot.id,
                "generation_mode": shot.generation_mode,
                "positive_prompt": compiled.positive_prompt,
                "negative_prompt": compiled.negative_prompt,
                "layers": compiled.layers,
            })

    return {
        "project_id": project_id,
        "project_title": project.title,
        "prompt_count": len(prompt_entries),
        "prompts": prompt_entries,
    }


# ---------------------------------------------------------------------------
# Delivery status shared by the exports that describe delivered media
# ---------------------------------------------------------------------------

def _delivery_status(db: Session, project_id: str) -> dict[str, Any]:
    """The lineage and waiver state of the current cut.

    Every export that describes delivered media repeats this, so a stale
    lineage or a waived delivery cannot be read as a clean one just because
    the reader opened a different file than the timeline manifest itself.
    This reuses the timeline manifest's own strict check rather than
    recomputing it, so the two can never disagree.
    """
    from app.services.timeline_service import StaleTimelineError, get_timeline_manifest

    try:
        manifest = get_timeline_manifest(db, project_id, strict_lineage=True)
    except StaleTimelineError as exc:
        return {
            "warnings": [{
                "code": "stale_timeline_lineage",
                "message": str(exc),
            }],
            "delivery_validation": {
                "pipeline_pass": False,
                "delivery_spec_pass": False,
            },
        }
    return {
        "warnings": manifest["warnings"],
        "delivery_validation": manifest["delivery_validation"],
    }


# ---------------------------------------------------------------------------
# Generation manifest export
# ---------------------------------------------------------------------------

def export_generation_manifest(db: Session, project_id: str) -> dict[str, Any]:
    """
    Export all generation jobs and their provenance for a project.
    """
    delivery = _delivery_status(db, project_id)
    scenes = db.query(Scene).filter(Scene.project_id == project_id).all()
    scene_ids = [s.id for s in scenes]

    if not scene_ids:
        return {"project_id": project_id, "jobs": [], **delivery}

    shots = db.query(Shot).filter(Shot.scene_id.in_(scene_ids)).all()
    shot_ids = [s.id for s in shots]

    if not shot_ids:
        return {"project_id": project_id, "jobs": [], **delivery}

    jobs = (
        db.query(GenerationJob)
        .filter(GenerationJob.shot_id.in_(shot_ids))
        .order_by(GenerationJob.created_at)
        .all()
    )

    job_entries: list[dict[str, Any]] = []
    for job in jobs:
        takes = db.query(Take).filter(Take.job_id == job.id).all()
        job_entries.append({
            "job_id": job.id,
            "shot_id": job.shot_id,
            "workflow_id": job.workflow_id,
            "workflow_version": job.workflow_version,
            # Provenance: the exact graph submitted and the hash of the
            # registered source it came from (PRD FR-11, NFR-10).
            "workflow_snapshot_path": job.workflow_snapshot_path or "",
            "workflow_sha256": job.workflow_sha256 or "",
            # Which vendor ran it, on what model, with what parameters and at
            # what cost. A ComfyUI job and an OpenAI job are both fully
            # described here, so the export explains itself without the reader
            # having to know which one produced the media.
            "media_provider_id": job.media_provider_id or "comfyui",
            "media_model": job.media_model or "workflow",
            "request_params": job.request_params or {},
            "usage": job.usage or {},
            "estimated_cost_usd": job.estimated_cost_usd,
            "provenance": job.provenance or {},
            "seed": job.seed,
            "status": job.status,
            "attempts": job.attempts,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "outputs": job.outputs,
            "submitted_at": job.submitted_at.isoformat() if job.submitted_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "takes": [
                {
                    "take_id": t.id,
                    "file_path": t.file_path,
                    "media_provider_id": t.media_provider_id or "comfyui",
                    "media_model": t.media_model or "workflow",
                    "request_params": t.request_params or {},
                    "usage": t.usage or {},
                    "estimated_cost_usd": t.estimated_cost_usd,
                    "provenance": t.provenance or {},
                    "review_status": t.review_status,
                    "rating": t.rating,
                    "notes": t.notes,
                    # A take accepted under a waiver has to say so wherever it
                    # is exported, not only on the timeline manifest.
                    "lineage": t.lineage or {},
                }
                for t in takes
            ],
        })

    return {
        "project_id": project_id,
        "job_count": len(job_entries),
        "jobs": job_entries,
        **delivery,
    }


# ---------------------------------------------------------------------------
# Timeline manifest export
# ---------------------------------------------------------------------------

def export_timeline_manifest(db: Session, project_id: str) -> dict[str, Any]:
    """Export timeline manifest as a standalone JSON document."""
    from app.services.timeline_service import get_timeline_manifest
    return get_timeline_manifest(db, project_id, strict_lineage=True)


# ---------------------------------------------------------------------------
# Project archive export
# ---------------------------------------------------------------------------

def export_project_archive(db: Session, project_id: str) -> dict[str, Any]:
    """
    Export the complete project metadata as a single JSON archive.

    Includes: project, story bible, scenes, shots, jobs, takes, timeline.
    Does NOT include binary media files.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": f"Project {project_id} not found"}

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    locations = db.query(Location).filter(Location.project_id == project_id).all()
    styles = db.query(Style).filter(Style.project_id == project_id).all()
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )
    timeline_items = (
        db.query(TimelineItem)
        .filter(TimelineItem.project_id == project_id)
        .order_by(TimelineItem.order)
        .all()
    )

    archive: dict[str, Any] = {
        "project": {
            "id": project.id,
            "title": project.title,
            "objective": project.objective,
            "audience": project.audience,
            "content_type": project.content_type,
            "aspect_ratio": project.aspect_ratio,
            "target_resolution": project.target_resolution,
            "target_duration_sec": project.target_duration_sec,
            "frame_rate": project.frame_rate,
            "language": project.language,
            "status": project.status,
            "brief_text": project.brief_text,
            "plot_text": project.plot_text,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        },
        "story_bible": {
            "characters": [
                {
                    "id": c.id, "name": c.name, "role": c.role,
                    "age_range": c.age_range, "appearance": c.appearance,
                    "clothing": c.clothing, "color_palette": c.color_palette,
                    "personality": c.personality, "prompt_tokens": c.prompt_tokens,
                }
                for c in characters
            ],
            "locations": [
                {
                    "id": loc.id, "name": loc.name,
                    "description": loc.description, "geography": loc.geography,
                    "time_of_day": loc.time_of_day, "palette": loc.palette,
                    "lighting": loc.lighting, "props": loc.props,
                }
                for loc in locations
            ],
            "styles": [
                {
                    "id": s.id, "medium": s.medium, "genre": s.genre,
                    "visual_keywords": s.visual_keywords,
                    "camera_language": s.camera_language,
                    "palette": s.palette, "lighting_rules": s.lighting_rules,
                    "negative_constraints": s.negative_constraints,
                }
                for s in styles
            ],
        },
        "ai_authoring_audit": project_audit(db, project),
        **_delivery_status(db, project_id),
        "scenes": [],
        "timeline": [
            {
                "id": ti.id, "shot_id": ti.shot_id, "take_id": ti.take_id,
                "order": ti.order, "in_point_sec": ti.in_point_sec,
                "out_point_sec": ti.out_point_sec, "duration_sec": ti.duration_sec,
                "transition_in": ti.transition_in,
                "transition_out": ti.transition_out,
            }
            for ti in timeline_items
        ],
    }

    for scene in scenes:
        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        shot_data: list[dict[str, Any]] = []
        for shot in shots:
            jobs = (
                db.query(GenerationJob)
                .filter(GenerationJob.shot_id == shot.id)
                .order_by(GenerationJob.created_at)
                .all()
            )
            takes = (
                db.query(Take)
                .filter(Take.shot_id == shot.id)
                .order_by(Take.created_at)
                .all()
            )

            shot_data.append({
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
                "planned_duration_sec": shot.planned_duration_sec,
                "generation_mode": shot.generation_mode,
                "image_prompt": shot.image_prompt,
                "video_prompt": shot.video_prompt,
                "negative_prompt": shot.negative_prompt,
                "status": shot.status,
                "jobs": [
                    {
                        "id": j.id,
                        "workflow_id": j.workflow_id,
                        "media_provider_id": j.media_provider_id or "comfyui",
                        "media_model": j.media_model or "workflow",
                        "estimated_cost_usd": j.estimated_cost_usd,
                        "seed": j.seed,
                        "status": j.status,
                        "attempts": j.attempts,
                        "outputs": j.outputs,
                    }
                    for j in jobs
                ],
                "takes": [
                    {
                        "id": t.id,
                        "job_id": t.job_id,
                        "file_path": t.file_path,
                        "media_provider_id": t.media_provider_id or "comfyui",
                        "media_model": t.media_model or "workflow",
                        "request_params": t.request_params or {},
                        "usage": t.usage or {},
                        "estimated_cost_usd": t.estimated_cost_usd,
                        "provenance": t.provenance or {},
                        "review_status": t.review_status,
                        "rating": t.rating,
                        "notes": t.notes,
                        "lineage": t.lineage or {},
                    }
                    for t in takes
                ],
            })

        archive["scenes"].append({
            "id": scene.id,
            "order": scene.order,
            "title": scene.title,
            "purpose": scene.purpose,
            "summary": scene.summary,
            "character_ids": scene.character_ids,
            "location_id": scene.location_id,
            "time_of_day": scene.time_of_day,
            "emotional_beat": scene.emotional_beat,
            "planned_duration_sec": scene.planned_duration_sec,
            "status": scene.status,
            "shots": shot_data,
        })

    return archive
