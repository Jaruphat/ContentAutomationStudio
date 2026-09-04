"""API for extracting, selecting and clearing explicit continuity frames."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Scene, Shot, Take
from app.schemas import (
    ContinuityFrameExtractRequest,
    ContinuityFrameResponse,
    ContinuitySourceOption,
    ContinuitySourceUpdate,
    ShotContinuityStatus,
)
from app.services import continuity_frames, revisions, shot_conditioning

router = APIRouter(tags=["continuity-frames"])


def _project(db: Session, project_id: str) -> Project:
    value = db.query(Project).filter(Project.id == project_id).first()
    if value is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return value


def _shot(db: Session, project_id: str, scene_id: str, shot_id: str) -> Shot:
    _project(db, project_id)
    value = (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(
            Shot.id == shot_id,
            Shot.scene_id == scene_id,
            Scene.project_id == project_id,
        )
        .first()
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return value


def _take(db: Session, project_id: str, take_id: str) -> Take:
    _project(db, project_id)
    value = (
        db.query(Take)
        .join(Shot, Take.shot_id == Shot.id)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Take.id == take_id, Scene.project_id == project_id)
        .first()
    )
    if value is None:
        raise HTTPException(status_code=404, detail="Take not found")
    return value


def _error(exc: continuity_frames.ContinuityFrameError) -> HTTPException:
    status = 404 if exc.code in {"take_not_found", "project_missing"} else 409
    return HTTPException(status_code=status, detail=str(exc))


def _candidate(db: Session, frame) -> ContinuitySourceOption:
    take = db.query(Take).filter(Take.id == frame.take_id).first()
    source_shot = db.query(Shot).filter(Shot.id == frame.shot_id).first()
    usable = take is not None and (take.review_status or "") == "Approved"
    reason = ""
    if take is None:
        usable, reason = False, "The source take no longer exists."
    elif not usable:
        reason = "The source take is no longer approved."
    elif source_shot is not None and (
        revisions.take_lineage_state(take, source_shot) == revisions.LINEAGE_STALE
    ):
        usable, reason = False, "The source take is out of date."
    return ContinuitySourceOption(
        take_id=frame.take_id,
        shot_id=frame.shot_id,
        shot_label=(
            f"Shot {source_shot.order}" if source_shot is not None else "Deleted shot"
        ),
        scene_id=source_shot.scene_id if source_shot is not None else "",
        frame=ContinuityFrameResponse.model_validate(frame),
        usable=usable,
        reason=reason,
    )


def _status(db: Session, project_id: str, shot: Shot) -> ShotContinuityStatus:
    resolved = shot_conditioning.resolve(db, project_id, shot)
    frame = (
        continuity_frames.get_frame(db, shot.continuity_source_take_id)
        if shot.continuity_source_take_id
        else None
    )
    source_shot = None
    if frame is not None:
        source_shot = db.query(Shot).filter(Shot.id == frame.shot_id).first()
    return ShotContinuityStatus(
        shot_id=shot.id,
        mode=shot.continuity_source_mode or continuity_frames.MODE_NONE,
        source_take_id=shot.continuity_source_take_id,
        frame=ContinuityFrameResponse.model_validate(frame) if frame else None,
        source_shot_id=source_shot.id if source_shot else "",
        source_shot_label=f"Shot {source_shot.order}" if source_shot else "",
        problems=list(resolved.problems),
        candidates=[
            _candidate(db, candidate)
            for candidate in continuity_frames.candidates(db, project_id, shot)
        ],
    )


@router.post(
    "/api/projects/{project_id}/takes/{take_id}/continuity-frame",
    response_model=ContinuityFrameResponse,
    status_code=201,
)
def extract_continuity_frame(
    project_id: str,
    take_id: str,
    payload: ContinuityFrameExtractRequest,
    db: Session = Depends(get_db),
):
    take = _take(db, project_id, take_id)
    try:
        frame = continuity_frames.extract_frame(db, take, at_sec=payload.at_sec)
    except continuity_frames.ContinuityFrameError as exc:
        raise _error(exc) from exc
    revisions.refresh_project(db, project_id)
    return frame


@router.get(
    "/api/projects/{project_id}/takes/{take_id}/continuity-frame",
    response_model=ContinuityFrameResponse,
)
def get_continuity_frame(
    project_id: str, take_id: str, db: Session = Depends(get_db)
):
    _take(db, project_id, take_id)
    frame = continuity_frames.get_frame(db, take_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Continuity frame not found")
    return frame


_CONTINUITY_PATH = (
    "/api/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}/continuity"
)


@router.get(_CONTINUITY_PATH, response_model=ShotContinuityStatus)
def get_shot_continuity(
    project_id: str,
    scene_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
):
    return _status(db, project_id, _shot(db, project_id, scene_id, shot_id))


@router.put(_CONTINUITY_PATH, response_model=ShotContinuityStatus)
def bind_shot_continuity(
    project_id: str,
    scene_id: str,
    shot_id: str,
    payload: ContinuitySourceUpdate,
    db: Session = Depends(get_db),
):
    shot = _shot(db, project_id, scene_id, shot_id)
    try:
        if payload.source_take_id:
            continuity_frames.bind_source(db, project_id, shot, payload.source_take_id)
        else:
            continuity_frames.clear_source(db, shot)
    except continuity_frames.ContinuityFrameError as exc:
        raise _error(exc) from exc
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    return _status(db, project_id, shot)


@router.delete(_CONTINUITY_PATH, response_model=ShotContinuityStatus)
def clear_shot_continuity(
    project_id: str,
    scene_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
):
    shot = _shot(db, project_id, scene_id, shot_id)
    continuity_frames.clear_source(db, shot)
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    return _status(db, project_id, shot)
