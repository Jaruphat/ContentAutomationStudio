"""
Generation router - Queue management, job lifecycle, and preflight validation.
"""

import random
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Character,
    GenerationJob,
    Location,
    Project,
    Scene,
    Shot,
    Style,
    Workflow,
)
from app.schemas import (
    GenerateRequest,
    GenerationJobResponse,
    PreflightResult,
    QueueStatus,
)
from app.services.prompt_compiler import compile_prompt
from app.services.queue_manager import queue_manager

router = APIRouter(tags=["generation"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_project_shots(db: Session, project_id: str) -> list[Shot]:
    """Return all shots for a project, in scene/shot order."""
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )
    shots: list[Shot] = []
    for scene in scenes:
        scene_shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        shots.extend(scene_shots)
    return shots


# ---------------------------------------------------------------------------
# Preflight validation
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/preflight",
    response_model=PreflightResult,
)
def preflight_validation(project_id: str, db: Session = Depends(get_db)):
    """
    Run preflight checks before generation.

    Validates that shots have prompts, workflow assignments, and
    that referenced workflows exist and have valid mappings.
    """
    project = _get_project_or_404(db, project_id)
    shots = _get_project_shots(db, project_id)

    issues: list[dict[str, Any]] = []
    ready_count = 0

    for shot in shots:
        shot_issues: list[str] = []

        # Check prompt presence
        if shot.generation_mode == "image" and not shot.image_prompt:
            shot_issues.append("Missing image prompt")
        elif shot.generation_mode in ("video", "image-to-video") and not shot.video_prompt:
            shot_issues.append("Missing video prompt")

        # Check workflow assignment
        workflow_id = shot.workflow_preset_id
        if not workflow_id:
            # Try project defaults
            if shot.generation_mode == "image":
                workflow_id = project.default_image_workflow_id
            else:
                workflow_id = project.default_video_workflow_id

        if workflow_id:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                shot_issues.append(f"Referenced workflow '{workflow_id}' not found")
            elif workflow.validation_status == "invalid":
                shot_issues.append(f"Workflow '{workflow.name}' has invalid mapping")
        else:
            shot_issues.append("No workflow assigned (shot or project default)")

        # Check status
        if shot.status not in ("Ready", "Draft", "Failed"):
            shot_issues.append(f"Shot status is '{shot.status}', expected Ready or Draft")

        if shot_issues:
            issues.append({
                "shot_id": shot.id,
                "scene_id": shot.scene_id,
                "shot_order": shot.order,
                "issues": shot_issues,
            })
        else:
            ready_count += 1

    return PreflightResult(
        ready=len(issues) == 0 and len(shots) > 0,
        total_shots=len(shots),
        ready_shots=ready_count,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Generate (create jobs)
# ---------------------------------------------------------------------------

@router.post(
    "/api/projects/{project_id}/generate",
    response_model=list[GenerationJobResponse],
)
def start_generation(
    project_id: str,
    payload: GenerateRequest,
    db: Session = Depends(get_db),
):
    """
    Create generation jobs for ready shots. If shot_ids is provided, only
    those shots are queued. Otherwise all eligible shots are queued.
    """
    project = _get_project_or_404(db, project_id)
    all_shots = _get_project_shots(db, project_id)

    # Load Story Bible
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

    # Filter shots
    target_ids = set(payload.shot_ids) if payload.shot_ids else None
    eligible_statuses = {"Draft", "Ready", "Failed", "NeedsReview"}

    created_jobs: list[GenerationJob] = []

    for shot in all_shots:
        if target_ids and shot.id not in target_ids:
            continue
        if shot.status not in eligible_statuses:
            continue

        # Determine workflow
        workflow_id = shot.workflow_preset_id
        if not workflow_id:
            if shot.generation_mode == "image":
                workflow_id = project.default_image_workflow_id
            else:
                workflow_id = project.default_video_workflow_id

        workflow_version = ""
        if workflow_id:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow:
                workflow_version = workflow.version

        # Compile prompt
        scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
        scene_dict = {
            "id": scene.id if scene else "",
            "summary": scene.summary if scene else "",
            "emotional_beat": scene.emotional_beat if scene else "",
            "time_of_day": scene.time_of_day if scene else "",
            "character_ids": scene.character_ids if scene else [],
            "location_id": scene.location_id if scene else None,
        }
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

        # Determine seed
        if shot.seed_policy == "fixed":
            seed = 42
        elif shot.seed_policy == "random":
            seed = random.randint(0, 2**31 - 1)
        else:
            seed = random.randint(0, 2**31 - 1)

        parameter_map = {
            "positive_prompt": compiled.positive_prompt,
            "negative_prompt": compiled.negative_prompt,
            "seed": seed,
            "generation_mode": shot.generation_mode,
        }

        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=shot.id,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            parameter_map=parameter_map,
            seed=seed,
            status="Queued",
            attempts=0,
        )
        db.add(job)
        created_jobs.append(job)

        # Mark shot as generating
        shot.status = "Generating"

    db.commit()
    for job in created_jobs:
        db.refresh(job)

    return created_jobs


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/jobs",
    response_model=list[GenerationJobResponse],
)
def list_jobs(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    shots = _get_project_shots(db, project_id)
    shot_ids = [s.id for s in shots]
    if not shot_ids:
        return []
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.shot_id.in_(shot_ids))
        .order_by(GenerationJob.created_at.desc())
        .all()
    )


@router.get("/api/jobs/{job_id}", response_model=GenerationJobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs/{job_id}/cancel", response_model=GenerationJobResponse)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("Completed", "Cancelled"):
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel job in status '{job.status}'"
        )

    job.status = "Cancelled"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


@router.post("/api/jobs/{job_id}/retry", response_model=GenerationJobResponse)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in ("Failed", "Cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry Failed or Cancelled jobs, current: '{job.status}'",
        )

    job.status = "Queued"
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    job.comfyui_prompt_id = None
    db.commit()
    db.refresh(job)

    # Reset shot status
    shot = db.query(Shot).filter(Shot.id == job.shot_id).first()
    if shot:
        shot.status = "Generating"
        db.commit()

    return job


# ---------------------------------------------------------------------------
# Queue control
# ---------------------------------------------------------------------------

@router.post("/api/projects/{project_id}/queue/pause", response_model=QueueStatus)
def pause_queue(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    queue_manager.pause(project_id)
    return queue_manager.get_queue_status(project_id)


@router.post("/api/projects/{project_id}/queue/resume", response_model=QueueStatus)
def resume_queue(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    queue_manager.resume(project_id)
    return queue_manager.get_queue_status(project_id)
