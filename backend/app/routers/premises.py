"""Premises: what to make next, screened before it costs an hour of rendering.

Kept against a channel because the rubric is the channel's - what counts as
repeatable for a mystery series is not what counts for a what-if series - and
because the point of scoring is what happens next: a chosen premise becomes an
episode without anybody retyping the pillar and hook, which is where they
quietly stop matching.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Premise
from app.schemas import (
    PremiseCreate,
    PremiseRejectRequest,
    PremiseResponse,
    PremiseRubricEntry,
    ProjectResponse,
)
from app.services import channels, premises

router = APIRouter(tags=["premises"])


def _channel(db: Session, channel_id: str):
    value = channels.get_channel(db, channel_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return value


def _premise(db: Session, channel_id: str, premise_id: str) -> Premise:
    value = (
        db.query(Premise)
        .filter(Premise.id == premise_id, Premise.channel_id == channel_id)
        .first()
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Premise not found")
    return value


@router.get("/api/premise-rubric", response_model=list[PremiseRubricEntry])
def get_rubric():
    """The weighted rubric, so the form and the scoring share one source."""
    return premises.describe_rubric()


@router.post(
    "/api/channels/{channel_id}/premises",
    response_model=PremiseResponse,
    status_code=201,
)
def create_premise(
    channel_id: str, payload: PremiseCreate, db: Session = Depends(get_db)
):
    """Screen and score one candidate.

    The one-strange-thing gate runs before the scores, because a premise that
    cannot name it does not become a better film with better production - and
    rejecting it here costs a minute instead of an hour of rendering.
    """
    channel = _channel(db, channel_id)
    try:
        strange = premises.validate_one_strange_thing(payload.one_strange_thing)
        channels.validate_vocabulary(
            pillars=list(channel.pillars or []),
            hooks=list(channel.hooks or []),
            pillar=payload.pillar,
            hook_type=payload.hook_type,
        )
        result = premises.score(dict(payload.scores))
    except (premises.PremiseError, channels.ChannelError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    premise = Premise(
        channel_id=channel_id,
        title=payload.title.strip(),
        logline=payload.logline,
        one_strange_thing=strange,
        pillar=payload.pillar,
        hook_type=payload.hook_type,
        scores=dict(payload.scores),
        total=result.total,
        status=premises.STATUS_CANDIDATE,
    )
    db.add(premise)
    db.commit()
    db.refresh(premise)
    return premise


@router.get(
    "/api/channels/{channel_id}/premises", response_model=list[PremiseResponse]
)
def list_premises(channel_id: str, db: Session = Depends(get_db)):
    """Ranked, best first. Rejections stay in the list: the record of what was
    considered is what stops the same idea being re-proposed every month."""
    _channel(db, channel_id)
    return (
        db.query(Premise)
        .filter(Premise.channel_id == channel_id)
        .order_by(Premise.total.desc(), Premise.created_at.desc())
        .all()
    )


@router.post(
    "/api/channels/{channel_id}/premises/{premise_id}/start",
    response_model=ProjectResponse,
    status_code=201,
)
def start_from_premise(
    channel_id: str, premise_id: str, db: Session = Depends(get_db)
):
    """Turn a chosen premise into an episode, carrying its vocabulary."""
    channel = _channel(db, channel_id)
    premise = _premise(db, channel_id, premise_id)
    if premise.project_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This premise is already in production as episode "
                f"{premise.project_id}. Two episodes of one idea is how a "
                f"channel publishes the same short with two titles."
            ),
        )
    try:
        project = channels.start_episode(db, channel, {
            "title": premise.title,
            "premise": premise.logline or premise.one_strange_thing,
            "pillar": premise.pillar,
            "hook_type": premise.hook_type,
        })
    except channels.ChannelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    premise.project_id = project.id
    premise.status = premises.STATUS_IN_PRODUCTION
    db.commit()
    return project


@router.post(
    "/api/channels/{channel_id}/premises/{premise_id}/reject",
    response_model=PremiseResponse,
)
def reject_premise(
    channel_id: str,
    premise_id: str,
    payload: PremiseRejectRequest,
    db: Session = Depends(get_db),
):
    """Mark a candidate rejected, with the reason. Never deleted."""
    _channel(db, channel_id)
    premise = _premise(db, channel_id, premise_id)
    premise.status = premises.STATUS_REJECTED
    premise.rejection_reason = payload.reason
    db.commit()
    db.refresh(premise)
    return premise
