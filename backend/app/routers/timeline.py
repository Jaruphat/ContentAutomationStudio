"""
Timeline router - Timeline manifest, auto-build, and render plan.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, TimelineItem
from app.schemas import (
    RenderPlan,
    RenderResult,
    TimelineItemResponse,
    TimelineManifest,
    TimelineUpdateRequest,
)
from app.services import render_service, timeline_service

router = APIRouter(prefix="/api/projects/{project_id}", tags=["timeline"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _responses(
    items: list[TimelineItem], manifest: dict
) -> list[TimelineItemResponse]:
    """Merge each stored row with the names and media the manifest resolved.

    The row itself only holds ids; the scene title, shot name and thumbnail
    come from the manifest, which already looked them up.
    """
    display = {
        entry["id"]: entry.get("display", {}) for entry in manifest.get("items", [])
    }
    return [
        TimelineItemResponse.model_validate(item).model_copy(
            update=display.get(item.id, {})
        )
        for item in items
    ]


@router.get("/timeline", response_model=TimelineManifest)
def get_timeline(project_id: str, db: Session = Depends(get_db)):
    """Return the current timeline manifest."""
    _get_project_or_404(db, project_id)
    try:
        manifest = timeline_service.get_timeline_manifest(
            db, project_id, strict_lineage=True
        )
    except timeline_service.StaleTimelineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    items = (
        db.query(TimelineItem)
        .filter(TimelineItem.project_id == project_id)
        .order_by(TimelineItem.order)
        .all()
    )
    return TimelineManifest(
        project_id=project_id,
        items=_responses(items, manifest),
        total_duration_sec=manifest["total_duration_sec"],
        item_count=manifest["item_count"],
        warnings=manifest["warnings"],
        delivery_validation=manifest["delivery_validation"],
        coverage=manifest["coverage"],
    )


@router.put("/timeline", response_model=TimelineManifest)
def update_timeline(
    project_id: str,
    payload: TimelineUpdateRequest,
    db: Session = Depends(get_db),
):
    """Replace the timeline with the provided items."""
    _get_project_or_404(db, project_id)
    items_data = [
        {
            "project_id": project_id,
            "shot_id": item.shot_id,
            "take_id": item.take_id,
            "order": item.order,
            "in_point_sec": item.in_point_sec,
            "out_point_sec": item.out_point_sec,
            "duration_sec": item.duration_sec,
            "transition_in": item.transition_in,
            "transition_out": item.transition_out,
        }
        for item in payload.items
    ]
    try:
        created = timeline_service.save_timeline_items(db, project_id, items_data)
        manifest = timeline_service.get_timeline_manifest(
            db, project_id, strict_lineage=True
        )
    except timeline_service.StaleTimelineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TimelineManifest(
        project_id=project_id,
        items=_responses(created, manifest),
        total_duration_sec=manifest["total_duration_sec"],
        item_count=len(created),
        warnings=manifest["warnings"],
        delivery_validation=manifest["delivery_validation"],
        coverage=manifest["coverage"],
    )


@router.post("/timeline/build", response_model=TimelineManifest)
def build_timeline(project_id: str, db: Session = Depends(get_db)):
    """
    Auto-build the timeline from approved takes, ordered by scene/shot order.
    Replaces any existing timeline items.
    """
    _get_project_or_404(db, project_id)
    items_data = timeline_service.build_timeline_from_approved_takes(db, project_id)
    created = timeline_service.save_timeline_items(db, project_id, items_data)
    manifest = timeline_service.get_timeline_manifest(
        db, project_id, strict_lineage=True
    )
    return TimelineManifest(
        project_id=project_id,
        items=_responses(created, manifest),
        total_duration_sec=manifest["total_duration_sec"],
        item_count=len(created),
        warnings=manifest["warnings"],
        delivery_validation=manifest["delivery_validation"],
        coverage=manifest["coverage"],
    )


@router.post("/render-plan", response_model=RenderPlan)
def generate_render_plan(project_id: str, db: Session = Depends(get_db)):
    """
    Generate an FFmpeg render plan from the current timeline.

    Does NOT execute FFmpeg. Returns the command list and any warnings.
    Real rendering requires FFmpeg installed and actual media files.
    """
    _get_project_or_404(db, project_id)
    try:
        plan = timeline_service.generate_render_plan(db, project_id)
    except timeline_service.StaleTimelineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RenderPlan(
        project_id=plan["project_id"],
        timeline_items=plan["timeline_items"],
        ffmpeg_available=plan["ffmpeg_available"],
        commands=plan["commands"],
        warnings=plan["warnings"],
        warning_metadata=plan["warning_metadata"],
        delivery_validation=plan["delivery_validation"],
    )


@router.post("/render", response_model=RenderResult)
def render_review(project_id: str, db: Session = Depends(get_db)):
    """
    Render a review video from the current timeline using FFmpeg.

    Only approved takes are used. When FFmpeg is missing, the timeline is
    empty, or any referenced media file is absent, no video is produced and
    the response explains why - nothing is fabricated.
    """
    _get_project_or_404(db, project_id)
    try:
        result = render_service.render_review_video(db, project_id)
    except timeline_service.StaleTimelineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RenderResult(**result)
