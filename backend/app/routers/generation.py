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
    Take,
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
    dialogue_fit,
    media_providers,
    motion_direction,
    prompt_context,
    revisions,
    scene_routing,
    shot_conditioning,
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


ELIGIBLE_GENERATION_STATUSES = {"Draft", "Ready", "Failed"}


def _status_issue(shot: Shot) -> str | None:
    if shot.status in ELIGIBLE_GENERATION_STATUSES:
        return None
    return (
        f"Shot status is '{shot.status}', expected "
        + ", ".join(sorted(ELIGIBLE_GENERATION_STATUSES))
    )


def _continuity_issues_by_shot(
    db: Session, project_id: str, shots: list[Shot]
) -> dict[str, dict[str, Any]]:
    bible_requirements = [
        loc.props or ""
        for loc in db.query(Location).filter(Location.project_id == project_id).all()
    ]
    bible_requirements.extend(
        value
        for style in db.query(Style).filter(Style.project_id == project_id).all()
        for value in (
            style.visual_keywords,
            style.lighting_rules,
            style.negative_constraints,
        )
        if value
    )
    findings = continuity.find_continuity_issues(
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
    return {finding["shot_id"]: finding for finding in findings}


def _validate_workflow_record(
    workflow: Workflow, provider
) -> tuple[str, list[str], list[str]]:
    """Validate one assigned workflow for both preflight and /generate."""
    errors: list[str] = []
    warnings: list[str] = []
    source_format = (workflow.source_format or "unknown").lower()
    if source_format != WorkflowFormat.API.value:
        errors.append(
            f"Workflow is {source_format}-format JSON, which ComfyUI cannot "
            "execute. Re-import it via Workflow -> Export (API) in ComfyUI."
        )
        workflow.validation_status = "unsupported_format"
        return source_format, errors, warnings

    try:
        workflow_data = workflow_registry.load_workflow_source(
            workflow.source_json_path
        )
    except (FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))
        workflow_data = None

    if workflow_data is not None:
        _valid, map_errors, map_warnings = workflow_registry.validate_mapping(
            workflow_data=workflow_data,
            parameter_mapping=workflow.parameter_mapping or {},
            output_mapping=workflow.output_mapping or [],
        )
        errors.extend(map_errors)
        warnings.extend(map_warnings)
        missing = [
            field
            for field in job_payload.REQUIRED_LOGICAL_FIELDS
            if field not in (workflow.parameter_mapping or {})
        ]
        if missing:
            message = f"Required logical field(s) not mapped: {', '.join(missing)}"
            if provider.requires_workflow_payload:
                errors.append(message)
            else:
                warnings.append(message + " (tolerated in mock mode)")

    workflow.validation_status = "valid" if not errors else "invalid"
    return source_format, errors, warnings


def _video_direction(shot: Shot) -> str:
    """What this shot tells a video model, from either shape of direction.

    The motion pair *is* the video prompt once it is set - the compiler builds
    the prompt from it and ignores `video_prompt`. A blocker that only looks at
    the old field refuses a shot that is fully directed, which is exactly what
    it did on the first beat of a production run.
    """
    composed = motion_direction.compose(
        subject_motion=shot.subject_motion or "",
        camera_motion=shot.camera_motion or "",
    )
    return composed or (shot.video_prompt or "").strip()



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
    continuity_by_shot = _continuity_issues_by_shot(db, project_id, shots)

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

        source_format, errors, check_warnings = _validate_workflow_record(
            workflow, provider
        )

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

        conditioning = shot_conditioning.resolve(db, project_id, shot)
        shot_conditioning.select_for_submission(
            conditioning,
            max_images=(
                shot_conditioning.workflow_capacity(db, plan.workflow_id)
                if plan.provider_id == media_providers.COMFYUI
                else None
            ),
            min_images=(
                shot_conditioning.workflow_minimum(db, plan.workflow_id)
                if plan.provider_id == media_providers.COMFYUI
                else None
            ),
        )
        shot_issues.extend(conditioning.problems)
        if (
            shot.generation_mode == "image-to-video"
            and not conditioning.submitted_images
        ):
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
        elif shot.generation_mode in ("video", "image-to-video") and not (
            _video_direction(shot)
        ):
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
            elif conditioning.images:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow and job_payload.REFERENCE_IMAGE not in (
                    workflow.parameter_mapping or {}
                ):
                    shot_issues.append(
                        "Reference-conditioned generation requires the "
                        "referenceImage workflow mapping"
                    )

        status_issue = _status_issue(shot)
        if status_issue:
            shot_issues.append(status_issue)

        if shot_issues:
            issues.append({
                "shot_id": shot.id,
                "scene_id": shot.scene_id,
                "shot_order": shot.order,
                "issues": shot_issues,
            })
        else:
            ready_count += 1

    # -- Scene routing advice ----------------------------------------------
    # Where a shot sits in its scene decides whether its composition has to be
    # invented or is already sitting in the previous clip's last frame, and
    # the fast route composes from the reference rather than the prompt. That
    # is a trade, not a fault, so it warns and never blocks - and it is
    # aggregated, because the same sentence twenty-three times is unreadable.
    advice_shots: dict[str, list[int]] = {}
    for shot in shots:
        for line in scene_routing.plan(db, project_id, shot).warnings:
            advice_shots.setdefault(line, []).append(shot.order or 0)
        # Four hundred seconds a shot is far too long to learn at the end that
        # the direction described only the camera. Advisory: a held frame is a
        # legitimate choice, it just should not be an accident.
        if (shot.generation_mode or "").lower() in ("video", "image-to-video"):
            for line in motion_direction.review(
                subject_motion=shot.subject_motion or "",
                camera_motion=shot.camera_motion or "",
            ):
                advice_shots.setdefault(line, []).append(shot.order or 0)
    # A script and a shot plan that disagree is knowable now, with no audio,
    # no provider and no money - and every cut so far has learned it at the
    # end instead, after forty minutes of generation.
    for problem in dialogue_fit.review(db, project_id):
        warnings.append("Narration: " + problem["message"])

    for line, orders in advice_shots.items():
        listed = ", ".join(str(order) for order in sorted(set(orders)))
        warnings.append(f"Shot {listed}: {line}")

    # -- Paid generation ---------------------------------------------------
    summary = generation_planning.summarise(list(plans.values()), db)
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
    if target_ids is not None:
        selected = [shot for shot in all_shots if shot.id in target_ids]
    else:
        selected = [
            shot for shot in all_shots
            if shot.status in ELIGIBLE_GENERATION_STATUSES
        ]

    # A shot that is already Queued or Running must not be queued again: that
    # would produce two takes for one request, and two charges for it on a
    # metered provider. Shot status alone is not enough, because it can drift
    # (a manual edit, a status reset) while the job is still in flight.
    busy = generation_runs.shots_with_active_jobs(db, [shot.id for shot in selected])
    if busy and (target_ids is not None or len(busy) == len(selected)):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(busy)} selected shot(s) already have a queued or "
                f"running generation job. Nothing was queued; wait for the "
                f"current run to finish, or cancel those jobs first."
            ),
        )
    if busy:
        # An implicit "generate all eligible" request has no caller-supplied
        # batch contract, so active shots are safely omitted from that sweep.
        selected = [shot for shot in selected if shot.id not in busy]

    # Nothing is queued until every metered shot in the selection has been
    # authorised. Confirming is one explicit flag on the request, not a
    # side-effect of clicking Generate, and it covers the whole selection so a
    # user cannot approve one image and be charged for twelve.
    plans = {shot.id: generation_planning.plan_shot(db, project, shot) for shot in selected}
    summary = generation_planning.summarise(list(plans.values()), db)
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
    references: dict[str, shot_conditioning.ShotConditioning] = {}
    blocked: list[str] = []
    continuity_by_shot = _continuity_issues_by_shot(db, project_id, selected)
    for shot in selected:
        plan = plans[shot.id]
        shot_blockers = list(plan.blockers)
        status_issue = _status_issue(shot)
        if status_issue:
            shot_blockers.append(status_issue)
        if shot.generation_mode == "image" and not (shot.image_prompt or "").strip():
            shot_blockers.append("Missing image prompt")
        elif shot.generation_mode in ("video", "image-to-video") and not (
            _video_direction(shot)
        ):
            shot_blockers.append("Missing video prompt")
        finding = continuity_by_shot.get(shot.id)
        if finding:
            shot_blockers.append(
                "recurring prop continuity missing " + ", ".join(finding["missing"])
            )
        conditioning = shot_conditioning.resolve(db, project_id, shot)
        shot_conditioning.select_for_submission(
            conditioning,
            max_images=(
                shot_conditioning.workflow_capacity(db, plan.workflow_id)
                if plan.provider_id == media_providers.COMFYUI
                else None
            ),
            min_images=(
                shot_conditioning.workflow_minimum(db, plan.workflow_id)
                if plan.provider_id == media_providers.COMFYUI
                else None
            ),
        )
        references[shot.id] = conditioning
        shot_blockers.extend(conditioning.problems)
        if (
            shot.generation_mode == "image-to-video"
            and not conditioning.submitted_images
        ):
            shot_blockers.append("Image-to-video requires a reference image.")
        if plan.provider_id == media_providers.COMFYUI and plan.workflow_id:
            workflow = db.query(Workflow).filter(Workflow.id == plan.workflow_id).first()
            if workflow is None:
                shot_blockers.append("Assigned workflow was not found.")
            else:
                _format, workflow_errors, _warnings = _validate_workflow_record(
                    workflow, queue_manager.provider
                )
                if workflow_errors:
                    shot_blockers.append(
                        "Assigned workflow mapping is invalid: "
                        + "; ".join(workflow_errors)
                    )
        if conditioning.images and plan.provider_id == media_providers.COMFYUI:
            workflow = (
                db.query(Workflow).filter(Workflow.id == plan.workflow_id).first()
                if plan.workflow_id
                else None
            )
            capacity = job_payload.reference_capacity(
                workflow.parameter_mapping if workflow else None
            )
            if not capacity:
                shot_blockers.append(
                    "Reference-conditioned generation requires the "
                    "referenceImage workflow mapping."
                )
            elif not conditioning.submitted_images:
                shot_blockers.append(
                    "None of this shot's conditioning images could be submitted "
                    "to the selected workflow."
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
        conditioning = references[shot.id]

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
        # The shared builder, not a copy of it. This was a copy, and the copy
        # fell behind: the motion fields reached the preview and the
        # regenerate path and never reached the prompt a generation actually
        # submitted. Nine clips came back with no movement described and
        # nothing reported a problem.
        shot_dict = prompt_context.shot_input(shot)

        compiled = compile_prompt(
            shot=shot_dict,
            scene=scene_dict,
            characters=characters,
            locations=locations,
            styles=styles,
        )

        # Determine seed
        if shot.seed_policy == "fixed":
            seed = shot.seed if shot.seed is not None else 42
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
            reference_image_ids=conditioning.reference_image_ids,
            reference_sha256s=conditioning.reference_sha256s,
            reference_provenance=shot_conditioning.provenance(conditioning),
            character_set_ids=conditioning.character_set_ids,
            character_set_sha256s=conditioning.character_set_sha256s,
            continuity_source_take_id=(
                conditioning.continuity_source_take_id or None
            ),
            continuity_source_sha256=conditioning.continuity_source_sha256,
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
        [generation_planning.plan_shot(db, project, shot) for shot in selected], db,
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

    # Give the shot back. "Generating" is not a state the queue accepts, so a
    # shot left in it after its only job was cancelled can never be generated
    # again through the API - not by Generate, not by Regenerate, not by
    # editing it. Found on the second beat of a production run, where the only
    # remedy was a database write.
    if not generation_runs.shots_with_active_jobs(
        db, [job.shot_id], exclude_job_id=job.id
    ):
        shot = db.query(Shot).filter(Shot.id == job.shot_id).first()
        if shot is not None and shot.status == "Generating":
            # A take nobody has judged yet is waiting on a person, not on the
            # queue. Anything else goes back to being generatable.
            pending = (
                db.query(Take)
                .filter(Take.shot_id == shot.id, Take.review_status == "Pending")
                .count()
            )
            shot.status = "NeedsReview" if pending else "Ready"

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
    job.submitted_at = None
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
