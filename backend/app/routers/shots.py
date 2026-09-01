"""
Shots router - Full CRUD for shots within a scene, with reorder.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Scene, Shot
from app.schemas import ShotCreate, ShotReorderRequest, ShotResponse, ShotUpdate

router = APIRouter(
    prefix="/api/projects/{project_id}/scenes/{scene_id}/shots",
    tags=["shots"],
)


def _get_scene_or_404(
    db: Session, project_id: str, scene_id: str
) -> Scene:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scene = (
        db.query(Scene)
        .filter(Scene.id == scene_id, Scene.project_id == project_id)
        .first()
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.post("", response_model=ShotResponse, status_code=201)
def create_shot(
    project_id: str,
    scene_id: str,
    payload: ShotCreate,
    db: Session = Depends(get_db),
):
    _get_scene_or_404(db, project_id, scene_id)

    # Auto-assign order if not provided or zero
    if payload.order == 0:
        max_order = (
            db.query(Shot.order)
            .filter(Shot.scene_id == scene_id)
            .order_by(Shot.order.desc())
            .first()
        )
        next_order = (max_order[0] + 1) if max_order else 1
    else:
        next_order = payload.order

    shot = Shot(
        id=str(uuid.uuid4()),
        scene_id=scene_id,
        **payload.model_dump(exclude={"order"}),
        order=next_order,
    )
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


@router.get("", response_model=list[ShotResponse])
def list_shots(
    project_id: str, scene_id: str, db: Session = Depends(get_db)
):
    _get_scene_or_404(db, project_id, scene_id)
    return (
        db.query(Shot)
        .filter(Shot.scene_id == scene_id)
        .order_by(Shot.order)
        .all()
    )


@router.get("/{shot_id}", response_model=ShotResponse)
def get_shot(
    project_id: str,
    scene_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
):
    _get_scene_or_404(db, project_id, scene_id)
    shot = (
        db.query(Shot)
        .filter(Shot.id == shot_id, Shot.scene_id == scene_id)
        .first()
    )
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    return shot


@router.put("/{shot_id}", response_model=ShotResponse)
def update_shot(
    project_id: str,
    scene_id: str,
    shot_id: str,
    payload: ShotUpdate,
    db: Session = Depends(get_db),
):
    _get_scene_or_404(db, project_id, scene_id)
    shot = (
        db.query(Shot)
        .filter(Shot.id == shot_id, Shot.scene_id == scene_id)
        .first()
    )
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(shot, key, value)
    shot.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(shot)
    return shot


@router.delete("/{shot_id}", status_code=204)
def delete_shot(
    project_id: str,
    scene_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
):
    _get_scene_or_404(db, project_id, scene_id)
    shot = (
        db.query(Shot)
        .filter(Shot.id == shot_id, Shot.scene_id == scene_id)
        .first()
    )
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    db.delete(shot)
    db.commit()
    return None


@router.put("", response_model=list[ShotResponse])
def reorder_shots(
    project_id: str,
    scene_id: str,
    payload: ShotReorderRequest,
    db: Session = Depends(get_db),
):
    """Bulk-update shot order values."""
    _get_scene_or_404(db, project_id, scene_id)

    for item in payload.shots:
        shot = (
            db.query(Shot)
            .filter(Shot.id == item.id, Shot.scene_id == scene_id)
            .first()
        )
        if shot:
            shot.order = item.order
            shot.updated_at = datetime.now(timezone.utc)

    db.commit()

    return (
        db.query(Shot)
        .filter(Shot.scene_id == scene_id)
        .order_by(Shot.order)
        .all()
    )
