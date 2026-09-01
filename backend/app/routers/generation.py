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
from app.services import job_payload, workflow_registry
from app.services.workflow_format import WorkflowFormat
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


def _parse_resolution(value: str) -> tuple[int, int]:
    """Parse a 'WIDTHxHEIGHT' project resolution, falling back to 1920x1080."""
    try:
        width_str, height_str = str(value).lower().split("x", 1)
        return int(width_str), int(height_str)
    except (ValueError, AttributeError):
        return 1920, 1080


# ---------------------------------------------------------------------------
# Preflight validation
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/preflight",
    response_model=PreflightResult,
)
async def preflight_validation(project_id: str, db: Session = Depends(get_db)):
    """
    Run preflight checks before generation (PRD section 10.3).

    Per shot: prompt present, a workflow resolvable from the shot or the
    project default, and an eligible status.
    Per referenced workflow: the source JSON still parses and every mapped
    node/field still exists in it, plus the fields required to drive a real
    generation are mapped.
    Plus: whether the configured ComfyUI provider is reachable.
    """
    project = _get_project_or_404(db, project_id)
    shots = _get_project_shots(db, project_id)

    issues: list[dict[str, Any]] = []
    warnings: list[str] = []
    ready_count = 0

    # -- Provider reachability ------------------------------------------
    provider = queue_manager.provider
    health = await provider.check_health()
    if health.mock:
        warnings.append(
            "ComfyUI provider is in mock mode. Generated takes are deterministic "
            "placeholders, not real renders. Set COMFYUI_PROVIDER=real to use a "
            "live instance."
        )
    elif not health.online:
        warnings.append(
            f"ComfyUI is not reachable: {health.error or 'unknown error'}. "
            f"Jobs will fail until the instance is online."
        )

    # -- Workflow mapping validation ------------------------------------
    # Validate each distinct referenced workflow once rather than per shot.
    workflow_checks: list[dict[str, Any]] = []
    workflow_ok: dict[str, bool] = {}

    def _resolve_workflow_id(shot: Shot) -> str | None:
        if shot.workflow_preset_id:
            return shot.workflow_preset_id
        if shot.generation_mode == "image":
            return project.default_image_workflow_id
        return project.default_video_workflow_id

    referenced_ids = {
        wid for wid in (_resolve_workflow_id(s) for s in shots) if wid
    }

    for workflow_id in sorted(referenced_ids):
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if workflow is None:
            workflow_checks.append({
                "workflow_id": workflow_id,
                "name": "",
                "valid": False,
                "source_format": "unknown",
                "errors": ["Workflow record not found"],
                "warnings": [],
            })
            workflow_ok[workflow_id] = False
            continue

        errors: list[str] = []
        check_warnings: list[str] = []

        # An editor/UI graph fails for a reason no amount of mapping fixes, so
        # it is reported as such and not re-checked as a mapping problem.
        source_format = (workflow.source_format or "unknown").lower()
        if source_format != WorkflowFormat.API.value:
            workflow_ok[workflow_id] = False
            workflow_checks.append({
                "workflow_id": workflow_id,
                "name": workflow.name,
                "valid": False,
                "source_format": source_format,
                "errors": [
                    f"Workflow is {source_format}-format JSON, which ComfyUI "
                    f"cannot execute. Re-import it via Workflow -> Export (API) "
                    f"in ComfyUI."
                ],
                "warnings": [],
            })
            workflow.validation_status = "unsupported_format"
            continue

        try:
            workflow_data = workflow_registry.load_workflow_source(
                workflow.source_json_path
            )
        except (FileNotFoundError, ValueError) as exc:
            errors.append(str(exc))
            workflow_data = None

        if workflow_data is not None:
            valid, map_errors, map_warnings = workflow_registry.validate_mapping(
                workflow_data=workflow_data,
                parameter_mapping=workflow.parameter_mapping or {},
                output_mapping=workflow.output_mapping or [],
            )
            errors.extend(map_errors)
            check_warnings.extend(map_warnings)

            mapping = workflow.parameter_mapping or {}
            missing = [
                f for f in job_payload.REQUIRED_LOGICAL_FIELDS if f not in mapping
            ]
            if missing:
                message = (
                    f"Required logical field(s) not mapped: {', '.join(missing)}"
                )
                # Only blocking for a real instance; the mock does not execute
                # the graph, so an unmapped field cannot break it.
                if provider.requires_workflow_payload:
                    errors.append(message)
                else:
                    check_warnings.append(message + " (tolerated in mock mode)")

        is_ok = not errors
        workflow_ok[workflow_id] = is_ok
        workflow_checks.append({
            "workflow_id": workflow_id,
            "name": workflow.name,
            "valid": is_ok,
            "source_format": source_format,
            "errors": errors,
            "warnings": check_warnings,
        })

        # Keep the stored validation status in step with what we just checked.
        workflow.validation_status = "valid" if is_ok else "invalid"

    db.commit()

    # -- Per-shot checks -------------------------------------------------
    for shot in shots:
        shot_issues: list[str] = []

        if shot.generation_mode == "image" and not shot.image_prompt:
            shot_issues.append("Missing image prompt")
        elif shot.generation_mode in ("video", "image-to-video") and not shot.video_prompt:
            shot_issues.append("Missing video prompt")

        workflow_id = _resolve_workflow_id(shot)
        if not workflow_id:
            shot_issues.append("No workflow assigned (shot or project default)")
        elif not workflow_ok.get(workflow_id, False):
            shot_issues.append(
                f"Assigned workflow '{workflow_id}' failed mapping validation"
            )

        if shot.status not in ("Ready", "Draft", "Failed"):
            shot_issues.append(
                f"Shot status is '{shot.status}', expected Ready, Draft or Failed"
            )

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
        workflow_checks=workflow_checks,
        warnings=warnings,
        comfyui_online=health.online,
        comfyui_mock=health.mock,
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

        # Keys are the canonical logical field names shared with a workflow's
        # parameter_mapping, so the payload builder can line the two up.
        width, height = _parse_resolution(project.target_resolution)
        parameter_map = {
            job_payload.POSITIVE_PROMPT: compiled.positive_prompt,
            job_payload.NEGATIVE_PROMPT: compiled.negative_prompt,
            job_payload.SEED: seed,
            job_payload.WIDTH: width,
            job_payload.HEIGHT: height,
            job_payload.OUTPUT_PREFIX: f"{project_id[:8]}_{shot.id[:8]}",
        }
        if shot.generation_mode in ("video", "image-to-video"):
            frames = max(1, round(
                (shot.planned_duration_sec or 3.0) * (project.frame_rate or 24.0)
            ))
            parameter_map[job_payload.FRAMES] = frames

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
