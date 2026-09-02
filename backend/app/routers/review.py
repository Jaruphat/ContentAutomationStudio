"""
Review router - Take review, approval, rejection, and regeneration.
"""

import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GenerationJob, Project, Scene, Shot, Take
from app.schemas import (
    GenerationJobResponse,
    RegenerateRequest,
    TakeResponse,
    TakeReviewRequest,
)
from app.services import generation_planning, job_payload, media_providers

router = APIRouter(tags=["review"])


# ---------------------------------------------------------------------------
# List takes
# ---------------------------------------------------------------------------

@router.get(
    "/api/projects/{project_id}/takes",
    response_model=list[TakeResponse],
)
def list_project_takes(project_id: str, db: Session = Depends(get_db)):
    """List all takes for a project, across all shots."""
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

    return (
        db.query(Take)
        .filter(Take.shot_id.in_(shot_ids))
        .order_by(Take.created_at.desc())
        .all()
    )


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

    take.review_status = "Approved"
    take.approved_at = datetime.now(timezone.utc)
    if payload:
        if payload.rating is not None:
            take.rating = payload.rating
        if payload.notes:
            take.notes = payload.notes
    db.commit()
    db.refresh(take)

    # Update shot status to Approved if at least one take is approved
    shot = db.query(Shot).filter(Shot.id == take.shot_id).first()
    if shot:
        shot.status = "Approved"
        db.commit()

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

    # Reuse the previous job's compiled parameters so a regeneration differs
    # only by seed, but take routing from the current plan: the shot's provider
    # may have been changed since that job ran.
    last_job = (
        db.query(GenerationJob)
        .filter(GenerationJob.shot_id == shot_id)
        .order_by(GenerationJob.created_at.desc())
        .first()
    )

    parameter_map = (
        dict(last_job.parameter_map)
        if last_job and last_job.parameter_map
        else {}
    )

    # Generate new seed for regeneration
    seed = random.randint(0, 2**31 - 1)
    parameter_map[job_payload.SEED] = seed

    request_params = dict(plan.request_params)
    if plan.paid:
        request_params["paid_generation_confirmed"] = True
        request_params["cost_basis"] = plan.cost_basis

    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        workflow_id=plan.workflow_id,
        workflow_version=plan.workflow_version,
        parameter_map=parameter_map,
        media_provider_id=plan.provider_id,
        media_model=plan.model,
        request_params=request_params,
        usage={},
        estimated_cost_usd=plan.estimated_cost_usd,
        provenance={},
        seed=seed,
        status="Queued",
        attempts=0,
    )
    db.add(job)

    shot.status = "Generating"
    db.commit()
    db.refresh(job)

    return job
