"""The publish gate: one scorecard per episode, kept.

Take review answers "is this shot usable". This answers the decision that is
actually made once - does this episode go out - and records the answer so nine
pilots can be compared rather than remembered.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, QualityReview
from app.schemas import (
    QualityReviewRequest,
    QualityReviewResponse,
    QualityRubricEntry,
)
from app.services import quality_gate, render_identity

router = APIRouter(tags=["quality"])


def _project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _as_response(
    project_id: str, review: QualityReview | None
) -> QualityReviewResponse:
    if review is None:
        return QualityReviewResponse(project_id=project_id, reviewed=False)
    # Re-derived rather than stored: the sentences a person reads should come
    # from one place. The stored shortfalls are what it failed on at the time,
    # which is the part that must not move when the targets are revised.
    result = quality_gate.evaluate(
        dict(review.scores or {}),
        ai_tell=bool(review.ai_tell),
        # A stored card already passed the cause requirement; the placeholder
        # keeps re-evaluation from refusing a record that exists.
        ai_tell_causes=review.ai_tell_causes or "recorded",
    )
    return QualityReviewResponse(
        project_id=project_id,
        reviewed=True,
        passed=bool(review.passed),
        scores=dict(review.scores or {}),
        ai_tell=bool(review.ai_tell),
        ai_tell_causes=review.ai_tell_causes or "",
        shortfalls=list(review.shortfalls or []),
        reasons=result.reasons,
        notes=review.notes or "",
        reviewer=review.reviewer or "",
        created_at=review.created_at,
    )


@router.get("/api/quality-rubric", response_model=list[QualityRubricEntry])
def get_rubric():
    """The rubric as data, so the reviewer's form has one source."""
    return quality_gate.describe_rubric()


@router.post(
    "/api/projects/{project_id}/quality-review",
    response_model=QualityReviewResponse,
    status_code=201,
)
def record_quality_review(
    project_id: str,
    payload: QualityReviewRequest,
    db: Session = Depends(get_db),
):
    """Score an episode against the rubric.

    A refused card records nothing: half a scorecard is worse than none,
    because it reads as a review that happened.
    """
    _project(db, project_id)
    try:
        result = quality_gate.evaluate(
            dict(payload.scores),
            ai_tell=payload.ai_tell,
            ai_tell_causes=payload.ai_tell_causes,
        )
    except quality_gate.QualityGateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    review = QualityReview(
        project_id=project_id,
        render_sha256=render_identity.render_sha256(project_id),
        scores=dict(payload.scores),
        ai_tell=payload.ai_tell,
        ai_tell_causes=payload.ai_tell_causes,
        passed=result.passed,
        shortfalls=result.shortfalls,
        notes=payload.notes,
        reviewer=payload.reviewer,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return _as_response(project_id, review)


@router.get(
    "/api/projects/{project_id}/quality-review",
    response_model=QualityReviewResponse,
)
def get_quality_review(project_id: str, db: Session = Depends(get_db)):
    """The most recent card, or the honest absence of one.

    Never reviewed is a normal state on the way to publishing, so it answers
    200 with ``reviewed: false`` rather than showing somebody a 404.
    """
    _project(db, project_id)
    review = (
        db.query(QualityReview)
        .filter(QualityReview.project_id == project_id)
        .order_by(QualityReview.created_at.desc(), QualityReview.id.desc())
        .first()
    )
    return _as_response(project_id, review)


@router.get(
    "/api/projects/{project_id}/quality-review/history",
    response_model=list[QualityReviewResponse],
)
def get_quality_review_history(project_id: str, db: Session = Depends(get_db)):
    """Every card, newest first. The change between two is the useful part."""
    _project(db, project_id)
    reviews = (
        db.query(QualityReview)
        .filter(QualityReview.project_id == project_id)
        .order_by(QualityReview.created_at.desc(), QualityReview.id.desc())
        .all()
    )
    return [_as_response(project_id, review) for review in reviews]
