"""
Scenes router - Full CRUD for scenes within a project, with reorder.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Scene
from app.schemas import (
    SceneCreate,
    SceneReorderRequest,
    SceneResponse,
    SceneUpdate,
    StoryboardSequenceRequest,
    StoryboardSequenceResult,
)
from app.services import revisions, storyboard_sequence

router = APIRouter(prefix="/api/projects/{project_id}/scenes", tags=["scenes"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=SceneResponse, status_code=201)
def create_scene(
    project_id: str, payload: SceneCreate, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)

    # Auto-assign order if not provided or zero
    if payload.order == 0:
        max_order = (
            db.query(Scene.order)
            .filter(Scene.project_id == project_id)
            .order_by(Scene.order.desc())
            .first()
        )
        next_order = (max_order[0] + 1) if max_order else 1
    else:
        next_order = payload.order

    scene = Scene(
        id=str(uuid.uuid4()),
        project_id=project_id,
        **payload.model_dump(exclude={"order"}),
        order=next_order,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


@router.get("", response_model=list[SceneResponse])
def list_scenes(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    return (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )


@router.get("/{scene_id}", response_model=SceneResponse)
def get_scene(
    project_id: str, scene_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    scene = (
        db.query(Scene)
        .filter(Scene.id == scene_id, Scene.project_id == project_id)
        .first()
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.put("/{scene_id}", response_model=SceneResponse)
def update_scene(
    project_id: str,
    scene_id: str,
    payload: SceneUpdate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    scene = (
        db.query(Scene)
        .filter(Scene.id == scene_id, Scene.project_id == project_id)
        .first()
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(scene, key, value)
    scene.updated_at = datetime.now(timezone.utc)
    db.commit()
    revisions.refresh_project(db, project_id)
    db.refresh(scene)
    return scene


@router.delete("/{scene_id}", status_code=204)
def delete_scene(
    project_id: str, scene_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    scene = (
        db.query(Scene)
        .filter(Scene.id == scene_id, Scene.project_id == project_id)
        .first()
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    db.delete(scene)
    db.commit()
    return None


@router.put("", response_model=list[SceneResponse])
def reorder_scenes(
    project_id: str,
    payload: SceneReorderRequest,
    db: Session = Depends(get_db),
):
    """Bulk-update scene order values."""
    _get_project_or_404(db, project_id)

    for item in payload.scenes:
        scene = (
            db.query(Scene)
            .filter(Scene.id == item.id, Scene.project_id == project_id)
            .first()
        )
        if scene:
            scene.order = item.order
            scene.updated_at = datetime.now(timezone.utc)

    db.commit()

    return (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )


@router.get("/{scene_id}/storyboard-sequence/estimate")
def estimate_storyboard_sequence(
    project_id: str, scene_id: str, db: Session = Depends(get_db),
):
    """What drawing this scene as a hosted sequence would cost."""
    project = _get_project_or_404(db, project_id)
    scene = db.query(Scene).filter(
        Scene.id == scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return storyboard_sequence.estimate_scene(db, project, scene)


@router.post(
    "/{scene_id}/storyboard-sequence", response_model=StoryboardSequenceResult,
)
def draw_storyboard_sequence(
    project_id: str,
    scene_id: str,
    payload: StoryboardSequenceRequest,
    db: Session = Depends(get_db),
):
    """Draw every shot in this scene as one chained hosted sequence.

    Each frame becomes a Pending take of its own shot. Nothing is approved and
    nothing already generated is replaced - the frames arrive to be reviewed
    beside whatever the shot already has.
    """
    project = _get_project_or_404(db, project_id)
    scene = db.query(Scene).filter(
        Scene.id == scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    try:
        result = storyboard_sequence.draw_scene(
            db, project, scene,
            client=storyboard_sequence.HostedAstra(),
            confirmed=payload.confirm_paid_generation,
            extra_guidance=payload.extra_guidance,
        )
    except storyboard_sequence.SequenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StoryboardSequenceResult(
        scene_id=result.scene_id,
        frames_drawn=result.frames_drawn,
        take_ids=result.take_ids,
        failures=result.failures,
        last_response_id=result.last_response_id,
    )
