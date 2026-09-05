"""
Timeline router - Timeline manifest, auto-build, and render plan.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, TimelineItem
from app.schemas import (
    RenderedFilm,
    RenderPlan,
    RenderRequest,
    RenderResult,
    TimelineItemResponse,
    TimelineManifest,
    TimelineUpdateRequest,
)
from app import paths
from app.services import (
    media_probe,
    range_response,
    render_service,
    timeline_service,
)

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
def build_timeline(
    project_id: str,
    confirm_replace_with_empty: bool = False,
    db: Session = Depends(get_db),
):
    """
    Auto-build the timeline from approved takes, ordered by scene/shot order.
    Replaces any existing timeline items.

    A build that can place nothing will not overwrite an existing cut: that is
    the signature of a lineage or migration problem, not of an empty project.
    Pass ``confirm_replace_with_empty=true`` to clear the timeline deliberately.
    """
    _get_project_or_404(db, project_id)
    items_data = timeline_service.build_timeline_from_approved_takes(db, project_id)
    try:
        created = timeline_service.save_timeline_items(
            db,
            project_id,
            items_data,
            allow_empty_replacement=confirm_replace_with_empty,
        )
    except timeline_service.EmptyTimelineReplacementError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
def render_review(
    project_id: str,
    payload: RenderRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Render a review video from the current timeline using FFmpeg.

    Only approved takes are used. When FFmpeg is missing, the timeline is
    empty, or any referenced media file is absent, no video is produced and
    the response explains why - nothing is fabricated.
    """
    _get_project_or_404(db, project_id)
    try:
        result = render_service.render_review_video(
            db, project_id, narrate=bool(payload and payload.narrate),
        )
    except timeline_service.StaleTimelineError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RenderResult(**result)


# ---------------------------------------------------------------------------
# Watching the result
# ---------------------------------------------------------------------------

def _rendered_path(project_id: str) -> str:
    """Where a review render lands. One known place per project, so "is there
    a finished film?" is a question the page can ask on load rather than
    something only the response to a render ever knew."""
    return os.path.join(paths.exports_dir(project_id), "review.mp4")


@router.get("/render/latest", response_model=RenderedFilm)
def latest_render(project_id: str, db: Session = Depends(get_db)):
    """Describe this project's finished film, if it has one.

    Everything else in this application is reviewable in the browser except
    the one thing the pipeline exists to produce: the render returned an
    absolute path and the path was gone on the next reload.
    """
    _get_project_or_404(db, project_id)
    path = _rendered_path(project_id)
    if not os.path.isfile(path):
        return RenderedFilm(
            project_id=project_id,
            rendered=False,
            reason=(
                "This project has not been rendered yet. Build the timeline "
                "and press Render Review."
            ),
        )

    probe = media_probe.probe_media_file(path)
    modified = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)

    # A film older than the newest thing on the timeline is still worth
    # playing - it is what was made - but saying so is the difference between
    # reviewing the current cut and reviewing a previous one without noticing.
    items = db.query(TimelineItem).filter(TimelineItem.project_id == project_id).all()
    latest_item = max(
        (item.updated_at or item.created_at for item in items if
         (item.updated_at or item.created_at)),
        default=None,
    )
    stale = bool(
        latest_item
        and latest_item.replace(tzinfo=latest_item.tzinfo or timezone.utc)
        > modified
    )

    return RenderedFilm(
        project_id=project_id,
        rendered=True,
        url=f"/api/projects/{project_id}/render/file",
        size_bytes=os.path.getsize(path),
        duration_sec=float(probe.get("duration_sec") or 0.0),
        width=int(probe.get("width") or 0),
        height=int(probe.get("height") or 0),
        has_audio=bool(probe.get("has_audio")),
        rendered_at=modified.isoformat(),
        stale=stale,
    )


@router.get("/render/file")
def stream_render(project_id: str, request: Request, db: Session = Depends(get_db)):
    """Stream the finished film, seekably.

    Range support is the whole point: without it a browser can only play from
    the start, and nobody reviews three minutes of film without scrubbing it.
    The path is derived here, never taken from the request.
    """
    _get_project_or_404(db, project_id)
    path = _rendered_path(project_id)
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail=(
                "This project has no render yet. Build the timeline and press "
                "Render Review."
            ),
        )
    return range_response.serve(path, request.headers.get("range"))
