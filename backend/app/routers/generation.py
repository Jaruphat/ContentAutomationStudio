"""
Generation router - Queue management, job lifecycle, and preflight validation.
"""

import random
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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
    GenerationEstimate,
    GenerationJobResponse,
    GenerationRunSummary,
    PreflightResult,
    QueueStatus,
)
from app.services import (
    continuity,
    generation_planning,
    generation_runs,
    job_payload,
    media_providers,
    reference_bible,
    revisions,
    workflow_registry,
)
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
    """Compatibility wrapper around the canonical project parser."""
    return generation_planning.parse_resolution(value)


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
    revisions.refresh_project(db, project_id)
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

    # One plan per shot, shared with /generate and /generate/estimate so
    # preflight cannot approve a route the queue would not take.
    plans = {shot.id: generation_planning.plan_shot(db, project, shot) for shot in shots}

    # Story/Style Bible prose can carry explicit recurring-prop invariants.
    # Keep these findings shot-addressable so only failed shots need regeneration.
    bible_requirements = [
        loc.props or ""
        for loc in db.query(Location).filter(Location.project_id == project_id).all()
    ]
    bible_requirements.extend(
        value
        for style in db.query(Style).filter(Style.project_id == project_id).all()
        for value in (style.visual_keywords, style.lighting_rules, style.negative_constraints)
        if value
    )
    continuity_findings = continuity.find_continuity_issues(
        [
            {
                "id": shot.id,
                "subject": shot.subject,
                "action": shot.action,
                "environment": shot.environment,
                "image_prompt": shot.image_prompt,
                "video_prompt": shot.video_prompt,
            }
            for shot in shots
        ],
        bible_requirements,
    )
    continuity_by_shot = {
        finding["shot_id"]: finding for finding in continuity_findings
    }

    def _resolve_workflow_id(shot: Shot) -> str | None:
        # A shot generated through a hosted image API has no graph to validate.
        return plans[shot.id].workflow_id

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
    project_format_issue = generation_planning.aspect_resolution_issue(
        project.aspect_ratio, project.target_resolution
    )
    for shot in shots:
        shot_issues: list[str] = []
        if project_format_issue:
            shot_issues.append(project_format_issue)
        plan = plans[shot.id]

        _resolved_references, reference_problems = reference_bible.resolve_images(
            db, project_id, list(shot.reference_asset_ids or [])
        )
        shot_issues.extend(problem.message for problem in reference_problems)
        if shot.generation_mode == "image-to-video" and not shot.reference_asset_ids:
            shot_issues.append("Image-to-video requires a reference image")
        if shot.is_stale:
            shot_issues.append(
                "Shot is stale: its generated take predates the current content revision"
            )

        finding = continuity_by_shot.get(shot.id)
        if finding:
            shot_issues.append(
                "recurring prop continuity missing " + ", ".join(finding["missing"])
            )

        if shot.generation_mode == "image" and not shot.image_prompt:
            shot_issues.append("Missing image prompt")
        elif shot.generation_mode in ("video", "image-to-video") and not shot.video_prompt:
            shot_issues.append("Missing video prompt")

        # The plan reports a missing prompt too; it is already listed above,
        # and repeating it as a provider blocker would read as two faults.
        already_missing_prompt = bool(shot_issues)
        shot_issues.extend(
            blocker
            for blocker in plan.blockers
            if not (already_missing_prompt and "image prompt" in blocker)
        )

        if plan.provider_id == media_providers.COMFYUI:
            workflow_id = plan.workflow_id
            if not workflow_id:
                shot_issues.append("No workflow assigned (shot or project default)")
            elif not workflow_ok.get(workflow_id, False):
                shot_issues.append(
                    f"Assigned workflow '{workflow_id}' failed mapping validation"
                )
            elif shot.reference_asset_ids:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow and job_payload.REFERENCE_IMAGE not in (
                    workflow.parameter_mapping or {}
                ):
                    shot_issues.append(
                        "Reference-conditioned generation requires the "
                        "referenceImage workflow mapping"
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

    # -- Paid generation ---------------------------------------------------
    summary = generation_planning.summarise(list(plans.values()))
    if summary["paid_shot_count"]:
        total = summary["estimated_cost_usd"]
        amount = f"about ${total:.2f}" if total is not None else "an unpriced amount"
        unpriced = summary["unpriced_paid_shots"]
        warnings.append(
            f"{summary['paid_shot_count']} shot(s) are routed to a metered "
            f"provider and will cost {amount}"
            + (f", plus {unpriced} shot(s) with no published rate" if unpriced else "")
            + ". Generation must be confirmed explicitly before it runs."
        )

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
    project_format_issue = generation_planning.aspect_resolution_issue(
        project.aspect_ratio, project.target_resolution
    )
    if project_format_issue:
        raise HTTPException(status_code=409, detail=project_format_issue)
    revisions.refresh_project(db, project_id)
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

    selected = [
        shot
        for shot in all_shots
        if not (target_ids and shot.id not in target_ids)
        and shot.status in eligible_statuses
    ]

    # A shot that is already Queued or Running must not be queued again: that
    # would produce two takes for one request, and two charges for it on a
    # metered provider. Shot status alone is not enough, because it can drift
    # (a manual edit, a status reset) while the job is still in flight.
    busy = generation_runs.shots_with_active_jobs(db, [shot.id for shot in selected])
    if busy:
        remaining = [shot for shot in selected if shot.id not in busy]
        if not remaining:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{len(busy)} selected shot(s) already have a queued or "
                    f"running generation job. Wait for the current run to "
                    f"finish, or cancel those jobs first."
                ),
            )
        selected = remaining

    # Nothing is queued until every metered shot in the selection has been
    # authorised. Confirming is one explicit flag on the request, not a
    # side-effect of clicking Generate, and it covers the whole selection so a
    # user cannot approve one image and be charged for twelve.
    plans = {shot.id: generation_planning.plan_shot(db, project, shot) for shot in selected}
    summary = generation_planning.summarise(list(plans.values()))
    if summary["requires_confirmation"] and not payload.confirm_paid_generation:
        total = summary["estimated_cost_usd"]
        amount = f"about ${total:.2f}" if total is not None else "an unpriced amount"
        raise HTTPException(
            status_code=409,
            detail=(
                f"{summary['paid_shot_count']} of {summary['shot_count']} "
                f"selected shot(s) generate through a metered provider and "
                f"would cost {amount}. Re-send with confirm_paid_generation "
                f"set to true to authorise this run."
            ),
        )

    unconfigured = [
        plan for plan in plans.values()
        if plan.paid and not media_providers.is_configured(plan.provider_id)
    ]
    if unconfigured:
        env_names = sorted(
            media_providers.API_KEY_ENV.get(p.provider_id, "its credentials")
            for p in unconfigured
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(unconfigured)} selected shot(s) are routed to a provider "
                f"this machine is not configured for. Set "
                f"{', '.join(dict.fromkeys(env_names))} in your local .env and "
                f"restart the backend, or switch those shots back to local "
                f"ComfyUI."
            ),
        )

    created_jobs: list[GenerationJob] = []

    if not selected:
        # Nothing was eligible. A run that generated nothing is not a run, and
        # recording one would clutter the history with empty batches.
        return created_jobs

    # Every blocker in the selection is found before anything is created. A
    # caller reaching this endpoint directly gets the same gate the Generate
    # page enforces through preflight, and the batch is refused as a whole:
    # queueing the valid half of a run would charge for work the user cannot
    # use, and leave a run whose shot list does not describe it.
    references: dict[str, list[Any]] = {}
    blocked: list[str] = []
    for shot in selected:
        plan = plans[shot.id]
        shot_blockers = list(plan.blockers)
        resolved_references, reference_problems = reference_bible.resolve_images(
            db, project_id, list(shot.reference_asset_ids or [])
        )
        references[shot.id] = resolved_references
        shot_blockers.extend(problem.message for problem in reference_problems)
        if shot.generation_mode == "image-to-video" and not resolved_references:
            shot_blockers.append("Image-to-video requires a reference image.")
        if resolved_references and plan.provider_id == media_providers.COMFYUI:
            workflow = (
                db.query(Workflow).filter(Workflow.id == plan.workflow_id).first()
                if plan.workflow_id
                else None
            )
            if not workflow or job_payload.REFERENCE_IMAGE not in (
                workflow.parameter_mapping or {}
            ):
                shot_blockers.append(
                    "Reference-conditioned generation requires the "
                    "referenceImage workflow mapping."
                )
            elif len(resolved_references) != 1:
                shot_blockers.append(
                    "The selected workflow accepts exactly one reference image."
                )
        if shot_blockers:
            blocked.append(
                f"{generation_runs.shot_display_name(shot)}: "
                + " ".join(shot_blockers)
            )

    if blocked:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(blocked)} of {len(selected)} selected shot(s) cannot be "
                f"generated as configured, so nothing was queued. "
                + " | ".join(blocked)
            ),
        )

    # One press of Generate is one run, created before the first job so every
    # job it produces carries the same batch identity. It is flushed rather
    # than committed with the jobs below, so a shot that fails validation
    # cannot leave an empty run behind in the history.
    run = generation_runs.create_run(
        db,
        project_id,
        kind=generation_runs.KIND_BATCH,
        shot_ids=[shot.id for shot in selected],
    )

    for shot in selected:
        plan = plans[shot.id]
        workflow_id = plan.workflow_id
        workflow_version = plan.workflow_version
        # Already resolved and validated for the whole batch above.
        resolved_references = references[shot.id]

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
            job_payload.ASPECT_RATIO: generation_planning.comfyui_aspect_ratio(
                project.aspect_ratio
            ),
            job_payload.OUTPUT_PREFIX: f"{project_id[:8]}_{shot.id[:8]}",
        }
        if shot.generation_mode in ("video", "image-to-video"):
            frames = max(1, round(
                (shot.planned_duration_sec or 3.0) * (project.frame_rate or 24.0)
            ))
            parameter_map[job_payload.FRAMES] = frames

        request_params = dict(plan.request_params)
        if plan.paid:
            # Recorded on the job, so an audit can show the run was authorised
            # and what it was authorised to cost.
            request_params["paid_generation_confirmed"] = True
            request_params["cost_basis"] = plan.cost_basis

        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=shot.id,
            run_id=run.id,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            parameter_map=parameter_map,
            media_provider_id=plan.provider_id,
            media_model=plan.model,
            request_params=request_params,
            usage={},
            estimated_cost_usd=plan.estimated_cost_usd,
            provenance={},
            prompt_revision=shot.prompt_revision,
            prompt_sha256=shot.prompt_sha256,
            content_sha256=shot.content_sha256,
            reference_image_ids=[image.id for image in resolved_references],
            reference_sha256s=[image.sha256 for image in resolved_references],
            reference_provenance={
                "images": [
                    {
                        "image_id": image.id,
                        "sheet_id": image.sheet_id,
                        "file_path": image.file_path,
                        "sha256": image.sha256,
                        "mime_type": image.mime_type,
                        "width": image.width,
                        "height": image.height,
                    }
                    for image in resolved_references
                ]
            },
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


@router.post(
    "/api/projects/{project_id}/generate/estimate",
    response_model=GenerationEstimate,
)
def estimate_generation(
    project_id: str,
    payload: GenerateRequest,
    db: Session = Depends(get_db),
):
    """What the same request would generate, and what it would cost.

    Called before Generate so the user sees the provider, model and price of a
    run before authorising it. Creates nothing and calls no vendor API.
    """
    project = _get_project_or_404(db, project_id)
    all_shots = _get_project_shots(db, project_id)

    target_ids = set(payload.shot_ids) if payload.shot_ids else None
    eligible_statuses = {"Draft", "Ready", "Failed", "NeedsReview"}
    selected = [
        shot
        for shot in all_shots
        if not (target_ids and shot.id not in target_ids)
        and shot.status in eligible_statuses
    ]

    return generation_planning.summarise(
        [generation_planning.plan_shot(db, project, shot) for shot in selected]
    )


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/jobs",
    response_model=list[GenerationJobResponse],
)
def list_jobs(
    project_id: str,
    run_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Every job of a project, newest first.

    ``run_id`` and ``status`` narrow the list without changing its shape, so a
    client that knows nothing about runs keeps the response it always had.
    """
    _get_project_or_404(db, project_id)
    shots = _get_project_shots(db, project_id)
    shot_ids = [s.id for s in shots]
    if not shot_ids:
        return []
    query = db.query(GenerationJob).filter(GenerationJob.shot_id.in_(shot_ids))
    if run_id:
        query = query.filter(GenerationJob.run_id == run_id)
    if status:
        query = query.filter(GenerationJob.status == status)
    return query.order_by(GenerationJob.created_at.desc()).all()


# ---------------------------------------------------------------------------
# Generation runs
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/runs",
    response_model=list[GenerationRunSummary],
)
def list_generation_runs(
    project_id: str,
    status: str | None = Query(
        default=None,
        description=(
            "active | terminal | queued | running | completed | failed | cancelled"
        ),
    ),
    limit: int = Query(default=50, ge=1),
    db: Session = Depends(get_db),
):
    """Run history, newest first, with run-scoped counts on each entry."""
    _get_project_or_404(db, project_id)
    summaries = [
        generation_runs.summarise_run(db, run)
        for run in generation_runs.list_runs(db, project_id)
    ]
    if status:
        summaries = [
            summary
            for summary in summaries
            if generation_runs.matches_status_filter(summary, status)
        ]
    return summaries[:limit]


@router.get(
    "/api/projects/{project_id}/runs/current",
    response_model=GenerationRunSummary | None,
)
def get_current_generation_run(project_id: str, db: Session = Depends(get_db)):
    """The run the Generate page is about, or null before the first one."""
    _get_project_or_404(db, project_id)
    run = generation_runs.current_run(db, project_id)
    if run is None:
        return None
    return generation_runs.summarise_run(db, run)


@router.get("/api/runs/{run_id}", response_model=GenerationRunSummary)
def get_generation_run(
    run_id: str,
    status: str | None = Query(
        default=None, description="Include only jobs in this job status."
    ),
    db: Session = Depends(get_db),
):
    """One run. ``status`` filters the job list, never the counts."""
    run = generation_runs.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return generation_runs.summarise_run(db, run, job_status=status)


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

    if generation_runs.shots_with_active_jobs(
        db, [job.shot_id], exclude_job_id=job.id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot retry this job while another queued or running job "
                "exists for the same shot. Wait for it to finish, or cancel it first."
            ),
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

@router.get("/api/projects/{project_id}/queue/status", response_model=QueueStatus)
def get_queue_status(project_id: str, db: Session = Depends(get_db)):
    """Return the backend's authoritative project queue state without changing it."""
    _get_project_or_404(db, project_id)
    return queue_manager.get_queue_status(project_id)


@router.post("/api/projects/{project_id}/queue/pause", response_model=QueueStatus)
def pause_queue(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    project.queue_paused = True
    db.commit()
    queue_manager.pause(project_id)
    return queue_manager.get_queue_status(project_id)


@router.post("/api/projects/{project_id}/queue/resume", response_model=QueueStatus)
def resume_queue(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    project.queue_paused = False
    db.commit()
    queue_manager.resume(project_id)
    return queue_manager.get_queue_status(project_id)
