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
from app.schemas import GenerationJobResponse, TakeResponse, TakeReviewRequest
from app.services import job_payload

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
def regenerate_shot(shot_id: str, db: Session = Depends(get_db)):
    """
    Create a new generation job for a shot. This is used when all takes
    are rejected and the user wants new results.
    """
    shot = db.query(Shot).filter(Shot.id == shot_id).first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")

    # Find the most recent job for this shot to reuse workflow/parameters
    last_job = (
        db.query(GenerationJob)
        .filter(GenerationJob.shot_id == shot_id)
        .order_by(GenerationJob.created_at.desc())
        .first()
    )

    workflow_id = shot.workflow_preset_id
    workflow_version = ""
    parameter_map = {}

    if last_job:
        workflow_id = last_job.workflow_id or workflow_id
        workflow_version = last_job.workflow_version
        parameter_map = dict(last_job.parameter_map) if last_job.parameter_map else {}

    # Generate new seed for regeneration
    seed = random.randint(0, 2**31 - 1)
    parameter_map[job_payload.SEED] = seed

    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        workflow_id=workflow_id,
        workflow_version=workflow_version,
        parameter_map=parameter_map,
        seed=seed,
        status="Queued",
        attempts=0,
    )
    db.add(job)

    shot.status = "Generating"
    db.commit()
    db.refresh(job)

    return job
