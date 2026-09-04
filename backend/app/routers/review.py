"""
Review router - Take review, approval, rejection, and regeneration.
"""

import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GenerationJob, Project, Scene, Shot, Take, Workflow
from app.schemas import (
    GenerationEstimate,
    GenerationJobResponse,
    RegenerateRequest,
    TakeResponse,
    TakeReviewRequest,
)
from app.services import (
    generation_planning,
    generation_runs,
    job_payload,
    media_providers,
    prompt_context,
    revisions,
    shot_conditioning,
    workflow_registry,
)

router = APIRouter(tags=["review"])


# ---------------------------------------------------------------------------
# List takes
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/takes",
    response_model=list[TakeResponse],
)
def list_project_takes(
    project_id: str,
    run: str | None = Query(
        default=None,
        description="Only takes produced by this generation run.",
    ),
    db: Session = Depends(get_db),
):
    """List all takes for a project, across all shots.

    ``run`` narrows the list to one press of Generate, which is how Review is
    reached from the Generate page. Takes carry the run they came from, so the
    filter needs no join through a job row that a deleted shot may have taken
    with it. Omitting ``run`` keeps the whole-project response unchanged.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    scenes = db.query(Scene).filter(Scene.project_id == project_id).all()
    shot_ids: list[str] = []
    for scene in scenes:
        shots = db.query(Shot).filter(Shot.scene_id == scene.id).all()
        shot_ids.extend(s.id for s in shots)

    if not shot_ids:
        return []

    query = db.query(Take).filter(Take.shot_id.in_(shot_ids))
    if run:
        query = query.filter(Take.run_id == run)
    return query.order_by(Take.created_at.desc()).all()


@router.get(
    "/api/shots/{shot_id}/takes",
    response_model=list[TakeResponse],
)
def list_shot_takes(shot_id: str, db: Session = Depends(get_db)):
    """List all takes for a specific shot."""
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    return (
        db.query(Take)
        .filter(Take.shot_id == shot_id)
        .order_by(Take.created_at.desc())
        .all()
    )


@router.get("/api/takes/{take_id}", response_model=TakeResponse)
def get_take(take_id: str, db: Session = Depends(get_db)):
    """Fetch a single take by id, for the inspector panel."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    return take


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------

@router.post("/api/takes/{take_id}/approve", response_model=TakeResponse)
def approve_take(
    take_id: str,
    payload: TakeReviewRequest = None,
    db: Session = Depends(get_db),
):
    """Approve a take. Optionally set rating and notes."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")

    if take.review_status == "Approved":
        raise HTTPException(status_code=400, detail="Take is already approved")

    # Approving is what marks a shot delivered, so the take has to still be of
    # the shot as it stands. Revisions are recomputed first rather than trusted
    # from the last write: the shot may have been edited in another tab since
    # this take was listed, and an approval decided on stale pixels would
    # otherwise promote content nobody reviewed.
    shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    scene = (
        db.query(Scene).filter(Scene.id == shot.scene_id).first() if shot else None
    )
    if scene:
        revisions.refresh_project(db, scene.project_id)
        db.refresh(shot)
    if shot and revisions.take_lineage_state(take, shot) == revisions.LINEAGE_STALE:
        raise HTTPException(
            status_code=409,
            detail=(
                "This take is out of date: the shot changed after it was "
                "generated, so approving it would mark content that no longer "
                "matches the brief as delivered. Regenerate the shot, then "
                "approve the new take."
            ),
        )

    take.review_status = "Approved"
    take.approved_at = datetime.now(timezone.utc)
    if payload:
        if payload.rating is not None:
            take.rating = payload.rating
        if payload.notes:
            take.notes = payload.notes

    # Update shot status to Approved if at least one take is approved
    if shot:
        shot.status = "Approved"
    db.commit()
    db.refresh(take)

    return take


@router.post("/api/takes/{take_id}/reject", response_model=TakeResponse)
def reject_take(
    take_id: str,
    payload: TakeReviewRequest = None,
    db: Session = Depends(get_db),
):
    """Reject a take. Optionally set rating and notes."""
    take = db.query(Take).filter(Take.id == take_id).first()
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")

    take.review_status = "Rejected"
    if payload:
        if payload.rating is not None:
            take.rating = payload.rating
        if payload.notes:
            take.notes = payload.notes
    db.commit()
    db.refresh(take)

    # Check if all takes for this shot are rejected -> mark shot as Failed
    shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    if shot:
        remaining_pending = (
            db.query(Take)
            .filter(
                Take.shot_id == take.shot_id,
                Take.review_status.in_(["Pending", "Approved"]),
            )
            .count()
        )
        if remaining_pending == 0:
            shot.status = "NeedsReview"
            db.commit()

    return take


# ---------------------------------------------------------------------------
# Regenerate
# ---------------------------------------------------------------------------

@router.get(
    "/api/shots/{shot_id}/regenerate/estimate",
    response_model=GenerationEstimate,
)
def estimate_regeneration(shot_id: str, db: Session = Depends(get_db)):
    """Price the next regeneration from the shot's current routing plan.

    Unlike the batch estimate, this intentionally includes approved shots: an
    approved take can be regenerated, and its historical provider/model must
    not determine whether the next request needs paid confirmation.
    """
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
    project = (
        db.query(Project).filter(Project.id == scene.project_id).first()
        if scene
        else None
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Shot is not attached to a project")
    return generation_planning.summarise(
        [generation_planning.plan_shot(db, project, shot)]
    )


@router.post(
    "/api/shots/{shot_id}/regenerate",
    response_model=GenerationJobResponse,
)
def regenerate_shot(
    shot_id: str,
    payload: RegenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Create a new generation job for a shot. This is used when all takes
    are rejected and the user wants new results.

    Routing and the paid-generation gate are the same as a project-wide
    Generate: regenerating a shot that is routed to a metered provider costs
    money too, so it needs the same explicit confirmation.
    """
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")

    scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
    project = (
        db.query(Project).filter(Project.id == scene.project_id).first()
        if scene
        else None
    )
    if project is None:
        raise HTTPException(
            status_code=404, detail="Shot is not attached to a project"
        )

    # A shot that is already Queued or Running must not be queued again. A
    # rejected take invites an immediate Regenerate, so this is the easiest way
    # to end up with two jobs -- and on a metered provider two charges -- for
    # one decision. Checked before anything is created, so a refusal leaves no
    # orphan run behind in the history.
    if generation_runs.shots_with_active_jobs(db, [shot_id]):
        raise HTTPException(
            status_code=409,
            detail=(
                "This shot already has a queued or running generation job. "
                "Wait for it to finish, or cancel it first."
            ),
        )

    revisions.refresh_project(db, project.id)
    plan = generation_planning.plan_shot(db, project, shot)
    confirmed = bool(payload and payload.confirm_paid_generation)
    if plan.paid and not confirmed:
        amount = (
            f"about ${plan.estimated_cost_usd:.2f}"
            if plan.estimated_cost_usd is not None
            else "an unpriced amount"
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"This shot regenerates through {plan.provider_id}, which is "
                f"metered, and would cost {amount}. Re-send with "
                f"confirm_paid_generation set to true to authorise it."
            ),
        )
    if plan.paid and not media_providers.is_configured(plan.provider_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{plan.provider_id} is selected for this shot but "
                f"{media_providers.API_KEY_ENV[plan.provider_id]} is not set on "
                f"this machine. Add it to your local .env and restart the "
                f"backend, or switch the shot back to local ComfyUI."
            ),
        )

    if plan.blockers:
        raise HTTPException(status_code=409, detail=" ".join(plan.blockers))

    conditioning = shot_conditioning.resolve(db, project.id, shot)
    if conditioning.problems:
        raise HTTPException(
            status_code=409,
            detail=" ".join(conditioning.problems),
        )
    if shot.generation_mode == "image-to-video" and not conditioning.images:
        raise HTTPException(
            status_code=409, detail="Image-to-video requires a reference image."
        )
    workflow = None
    if plan.provider_id == media_providers.COMFYUI and plan.workflow_id:
        workflow = db.query(Workflow).filter(Workflow.id == plan.workflow_id).first()
        if workflow is None:
            raise HTTPException(status_code=409, detail="Assigned workflow was not found.")
        try:
            workflow_data = workflow_registry.load_workflow_source(
                workflow.source_json_path
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot validate assigned workflow mapping: {exc}",
            ) from exc
        valid, mapping_errors, _warnings = workflow_registry.validate_mapping(
            workflow_data=workflow_data,
            parameter_mapping=workflow.parameter_mapping or {},
            output_mapping=workflow.output_mapping or [],
        )
        missing = [
            field
            for field in job_payload.REQUIRED_LOGICAL_FIELDS
            if field not in (workflow.parameter_mapping or {})
        ]
        if not valid or missing:
            details = list(mapping_errors)
            details.extend(f"Unmapped required field: {field}" for field in missing)
            raise HTTPException(
                status_code=409,
                detail="Assigned workflow mapping is invalid: " + "; ".join(details),
            )
    if conditioning.images and plan.provider_id == media_providers.COMFYUI:
        if not workflow or job_payload.REFERENCE_IMAGE not in (
            workflow.parameter_mapping or {}
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Reference-conditioned generation requires the "
                    "referenceImage workflow mapping."
                ),
            )
        if len(conditioning.images) != 1:
            raise HTTPException(
                status_code=409,
                detail="The selected workflow accepts exactly one reference image.",
            )

    compiled = prompt_context.compile_for_shot(db, shot).compiled

    # Generate new seed for regeneration
    seed = random.randint(0, 2**31 - 1)
    width, height = generation_planning.parse_resolution(project.target_resolution)
    parameter_map = {
        job_payload.POSITIVE_PROMPT: compiled.positive_prompt,
        job_payload.NEGATIVE_PROMPT: compiled.negative_prompt,
        job_payload.SEED: seed,
        job_payload.WIDTH: width,
        job_payload.HEIGHT: height,
        job_payload.ASPECT_RATIO: generation_planning.comfyui_aspect_ratio(
            project.aspect_ratio
        ),
        job_payload.OUTPUT_PREFIX: f"{project.id[:8]}_{shot.id[:8]}",
    }
    if shot.generation_mode in ("video", "image-to-video"):
        parameter_map[job_payload.FRAMES] = max(
            1,
            round(
                (shot.planned_duration_sec or 3.0)
                * (project.frame_rate or 24.0)
            ),
        )

    request_params = dict(plan.request_params)
    if plan.paid:
        request_params["paid_generation_confirmed"] = True
        request_params["cost_basis"] = plan.cost_basis

    run = generation_runs.create_run(
        db,
        project.id,
        kind=generation_runs.KIND_REGENERATION,
        shot_ids=[shot.id],
    )
    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        run_id=run.id,
        workflow_id=plan.workflow_id,
        workflow_version=plan.workflow_version,
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
        continuity_source_take_id=conditioning.continuity_source_take_id or None,
        continuity_source_sha256=conditioning.continuity_source_sha256,
        seed=seed,
        status="Queued",
        attempts=0,
    )
    db.add(job)

    shot.status = "Generating"
    db.commit()
    db.refresh(job)

    return job
