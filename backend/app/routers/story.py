"""
Story router - Brief/plot and Story Bible CRUD (characters, locations, styles).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, Location, Project, Style
from app.schemas import (
    CharacterCreate,
    CharacterResponse,
    CharacterUpdate,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    StoryResponse,
    StoryUpdate,
    StyleCreate,
    StyleResponse,
    StyleUpdate,
)
from app.services import revisions

router = APIRouter(prefix="/api/projects", tags=["story"])


# ---------------------------------------------------------------------------
# Brief and Plot
# ---------------------------------------------------------------------------

def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/story", response_model=StoryResponse)
def get_story(project_id: str, db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id)
    return StoryResponse(brief_text=project.brief_text, plot_text=project.plot_text)


@router.put("/{project_id}/story", response_model=StoryResponse)
def update_story(
    project_id: str, payload: StoryUpdate, db: Session = Depends(get_db)
):
    project = _get_project_or_404(db, project_id)
    if payload.brief_text is not None:
        project.brief_text = payload.brief_text
    if payload.plot_text is not None:
        project.plot_text = payload.plot_text
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    revisions.refresh_project(db, project_id)
    db.refresh(project)
    return StoryResponse(brief_text=project.brief_text, plot_text=project.plot_text)


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/characters",
    response_model=CharacterResponse,
    status_code=201,
)
def create_character(
    project_id: str, payload: CharacterCreate, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    character = Character(
        id=str(uuid.uuid4()),
        project_id=project_id,
        **payload.model_dump(),
    )
    db.add(character)
    db.commit()
    db.refresh(character)
    return character


@router.get("/{project_id}/characters", response_model=list[CharacterResponse])
def list_characters(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    return (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at)
        .all()
    )


@router.get(
    "/{project_id}/characters/{character_id}",
    response_model=CharacterResponse,
)
def get_character(
    project_id: str, character_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.put(
    "/{project_id}/characters/{character_id}",
    response_model=CharacterResponse,
)
def update_character(
    project_id: str,
    character_id: str,
    payload: CharacterUpdate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(character, key, value)
    character.updated_at = datetime.now(timezone.utc)
    db.commit()
    revisions.refresh_project(db, project_id)
    db.refresh(character)
    return character


@router.delete("/{project_id}/characters/{character_id}", status_code=204)
def delete_character(
    project_id: str, character_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    db.delete(character)
    db.commit()
    revisions.refresh_project(db, project_id)
    return None


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/locations",
    response_model=LocationResponse,
    status_code=201,
)
def create_location(
    project_id: str, payload: LocationCreate, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    location = Location(
        id=str(uuid.uuid4()),
        project_id=project_id,
        **payload.model_dump(),
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/{project_id}/locations", response_model=list[LocationResponse])
def list_locations(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    return (
        db.query(Location)
        .filter(Location.project_id == project_id)
        .order_by(Location.created_at)
        .all()
    )


@router.get(
    "/{project_id}/locations/{location_id}",
    response_model=LocationResponse,
)
def get_location(
    project_id: str, location_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    location = (
        db.query(Location)
        .filter(Location.id == location_id, Location.project_id == project_id)
        .first()
    )
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@router.put(
    "/{project_id}/locations/{location_id}",
    response_model=LocationResponse,
)
def update_location(
    project_id: str,
    location_id: str,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    location = (
        db.query(Location)
        .filter(Location.id == location_id, Location.project_id == project_id)
        .first()
    )
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(location, key, value)
    location.updated_at = datetime.now(timezone.utc)
    db.commit()
    revisions.refresh_project(db, project_id)
    db.refresh(location)
    return location


@router.delete("/{project_id}/locations/{location_id}", status_code=204)
def delete_location(
    project_id: str, location_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    location = (
        db.query(Location)
        .filter(Location.id == location_id, Location.project_id == project_id)
        .first()
    )
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    db.delete(location)
    db.commit()
    revisions.refresh_project(db, project_id)
    return None


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/styles",
    response_model=StyleResponse,
    status_code=201,
)
def create_style(
    project_id: str, payload: StyleCreate, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    style = Style(
        id=str(uuid.uuid4()),
        project_id=project_id,
        **payload.model_dump(),
    )
    db.add(style)
    db.commit()
    db.refresh(style)
    return style


@router.get("/{project_id}/styles", response_model=list[StyleResponse])
def list_styles(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    return (
        db.query(Style)
        .filter(Style.project_id == project_id)
        .order_by(Style.created_at)
        .all()
    )


@router.get(
    "/{project_id}/styles/{style_id}",
    response_model=StyleResponse,
)
def get_style(
    project_id: str, style_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    style = (
        db.query(Style)
        .filter(Style.id == style_id, Style.project_id == project_id)
        .first()
    )
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")
    return style


@router.put(
    "/{project_id}/styles/{style_id}",
    response_model=StyleResponse,
)
def update_style(
    project_id: str,
    style_id: str,
    payload: StyleUpdate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    style = (
        db.query(Style)
        .filter(Style.id == style_id, Style.project_id == project_id)
        .first()
    )
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(style, key, value)
    style.updated_at = datetime.now(timezone.utc)
    db.commit()
    revisions.refresh_project(db, project_id)
    db.refresh(style)
    return style


@router.delete("/{project_id}/styles/{style_id}", status_code=204)
def delete_style(
    project_id: str, style_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    style = (
        db.query(Style)
        .filter(Style.id == style_id, Style.project_id == project_id)
        .first()
    )
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")
    db.delete(style)
    db.commit()
    revisions.refresh_project(db, project_id)
    return None
