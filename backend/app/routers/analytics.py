"""Recording what the audience did, and reading it against what we chose.

Numbers are entered per episode and kept per capture: one snapshot cannot tell
a video that died at 200 views from one on its way to 20,000. The comparison
uses each episode's most recent capture, so two snapshots of one episode never
count as two episodes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models import EpisodeAnalytics, Project
from app.database import get_db
from app.schemas import (
    AnalyticsCaptureRequest,
    AnalyticsCaptureResponse,
    ChannelAnalyticsReport,
)
from app.services import analytics, channels

router = APIRouter(tags=["analytics"])

#: The measured fields carried from a capture row into a comparison.
_METRIC_FIELDS = (
    *analytics.COUNT_FIELDS,
    *analytics.PERCENT_FIELDS,
    "avg_view_duration_sec",
)


def _project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/api/projects/{project_id}/analytics",
    response_model=AnalyticsCaptureResponse,
    status_code=201,
)
def record_analytics(
    project_id: str,
    payload: AnalyticsCaptureRequest,
    db: Session = Depends(get_db),
):
    """Record one capture of the platform's numbers for this episode."""
    _project(db, project_id)
    values = payload.model_dump()
    try:
        analytics.validate_capture(values)
    except analytics.AnalyticsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    capture = EpisodeAnalytics(project_id=project_id, **values)
    db.add(capture)
    db.commit()
    db.refresh(capture)
    return capture


@router.get(
    "/api/projects/{project_id}/analytics",
    response_model=list[AnalyticsCaptureResponse],
)
def list_analytics(project_id: str, db: Session = Depends(get_db)):
    """Every capture, newest first. A number is only readable as a movement."""
    _project(db, project_id)
    return (
        db.query(EpisodeAnalytics)
        .filter(EpisodeAnalytics.project_id == project_id)
        .order_by(EpisodeAnalytics.captured_at.desc(), EpisodeAnalytics.id.desc())
        .all()
    )


@router.get(
    "/api/channels/{channel_id}/analytics",
    response_model=ChannelAnalyticsReport,
)
def compare_channel(channel_id: str, db: Session = Depends(get_db)):
    """Group this channel's measured episodes by the choices that varied.

    An episode with no capture is counted as unmeasured, never as zero:
    counting an unpublished episode as zero retention drags its group down and
    buries the format that was working.
    """
    channel = channels.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    episodes = channels.list_episodes(db, channel)
    measured: list[dict] = []
    unmeasured = 0
    for project in episodes:
        capture = (
            db.query(EpisodeAnalytics)
            .filter(EpisodeAnalytics.project_id == project.id)
            .order_by(
                EpisodeAnalytics.captured_at.desc(), EpisodeAnalytics.id.desc()
            )
            .first()
        )
        if capture is None:
            unmeasured += 1
            continue
        row = {
            "project_id": project.id,
            "title": project.title,
            "pillar": project.pillar or "",
            "hook_type": project.hook_type or "",
            "ending_type": project.ending_type or "",
            "captured_at": capture.captured_at,
        }
        row.update({field: getattr(capture, field) for field in _METRIC_FIELDS})
        measured.append(row)

    return analytics.build_report(measured, unmeasured)
