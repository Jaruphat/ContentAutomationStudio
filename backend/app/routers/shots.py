"""
Shots router - Full CRUD for shots within a scene, with reorder.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CharacterSet, Project, Scene, Shot, Take, TimelineItem
from app.schemas import (
    ShotCreate,
    ShotReorderRequest,
    ShotResponse,
    ShotRoute,
    ShotUpdate,
)
from app.services import reference_bible, revisions, scene_routing, shot_route

router = APIRouter(
    prefix="/api/projects/{project_id}/scenes/{scene_id}/shots",
    tags=["shots"],
)


def _check_references(
    db: Session, project_id: str, reference_asset_ids: list[str] | None
) -> None:
    """Refuse a shot that names a reference it cannot actually be generated from.

    Catching this at the write boundary is what keeps the failure cheap: an
    unknown or foreign reference id saved here would only surface at generation
    time, after a batch had already been authorised.
    """
    if not reference_asset_ids:
        return
    _resolved, problems = reference_bible.resolve_images(
        db, project_id, list(reference_asset_ids)
    )
    if problems:
        raise HTTPException(
            status_code=400,
            detail=" ".join(problem.message for problem in problems),
        )


def _check_character_sets(
    db: Session, project_id: str, character_set_ids: list[str] | None
) -> None:
    """All bound sets must exist in this project; duplicate bindings are invalid."""
    ids = [str(value) for value in (character_set_ids or []) if value]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="A character set can be bound once.")
    if not ids:
        return
    found = {
        value.id: value
        for value in db.query(CharacterSet).filter(CharacterSet.id.in_(ids)).all()
    }
    if any(found[value].project_id != project_id for value in ids if value in found):
        raise HTTPException(
            status_code=400,
            detail="A selected character set belongs to another project.",
        )
    if any(value not in found for value in ids):
        raise HTTPException(status_code=400, detail="A selected character set no longer exists.")


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
    _check_references(db, project_id, payload.reference_asset_ids)
    _check_character_sets(db, project_id, payload.character_set_ids)

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
    revisions.refresh_project(db, project_id)
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

    changes = payload.model_dump(exclude_unset=True)
    if "reference_asset_ids" in changes:
        _check_references(db, project_id, changes["reference_asset_ids"])
    if "character_set_ids" in changes:
        _check_character_sets(db, project_id, changes["character_set_ids"])

    previous_audio = (shot.audio_mode or "native", shot.audio_gain_db or 0.0)
    for key, value in changes.items():
        setattr(shot, key, value)
    shot.updated_at = datetime.now(timezone.utc)
    if previous_audio != (shot.audio_mode or "native", shot.audio_gain_db or 0.0):
        # Audio changes require a new mix, but not a new generated take.
        # Reuse the cut's freshness marker so Timeline and Publish agree.
        take_ids = db.query(Take.id).filter(Take.shot_id == shot.id).subquery()
        db.query(TimelineItem).filter(
            TimelineItem.project_id == project_id,
            (TimelineItem.shot_id == shot.id)
            | TimelineItem.take_id.in_(db.query(take_ids.c.id)),
        ).update({TimelineItem.updated_at: shot.updated_at}, synchronize_session=False)
    db.commit()
    revisions.refresh_project(db, project_id)
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


@router.get("/{shot_id}/route", response_model=ShotRoute)
def get_shot_route(
    project_id: str,
    scene_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
):
    """Name the route this shot will take, and what it will be given.

    Its own endpoint rather than a field on every shot: naming a route means
    reading the workflow behind it, and a storyboard listing forty shots
    should not pay for forty of those. The inspector asks about the one shot
    somebody is looking at.
    """
    _get_scene_or_404(db, project_id, scene_id)
    shot = (
        db.query(Shot)
        .filter(Shot.id == shot_id, Shot.scene_id == scene_id)
        .first()
    )
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    described = shot_route.describe(db, project_id, shot)
    # The scene plan is folded in here rather than fetched separately so the
    # route and the advice about it cannot be computed against two different
    # states of the same shot.
    planned = scene_routing.plan(db, project_id, shot)
    described.update(
        scene_role=planned.role,
        role_inferred=planned.inferred,
        pipeline=planned.pipeline,
        recommended_pipeline=planned.recommended_pipeline,
        role_summary=planned.summary,
        advice=planned.warnings,
    )
    return ShotRoute(**described)
