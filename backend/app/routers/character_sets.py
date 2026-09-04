"""Character-set CRUD, version generation, gallery and approval API."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, Project
from app.schemas import (
    CharacterSetCreate,
    CharacterSetGenerateRequest,
    CharacterSetResponse,
    CharacterSetUpdate,
    CharacterSetVersionCreate,
    CharacterSetVersionResponse,
)
from app.services import (
    character_set_generation,
    character_sets,
    media_providers,
    revisions,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/character-sets",
    tags=["character-sets"],
)


def _project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _character_set(db: Session, project_id: str, set_id: str):
    _project(db, project_id)
    value = character_sets.get_set(db, project_id, set_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Character set not found")
    return value


def _version(db: Session, project_id: str, set_id: str, version_id: str):
    character_set = _character_set(db, project_id, set_id)
    value = character_sets.get_version(db, character_set, version_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Character set version not found")
    return character_set, value


def _validate_character(db: Session, project_id: str, character_id: str | None) -> None:
    if not character_id:
        return
    character = db.query(Character).filter(Character.id == character_id).first()
    if character is None or character.project_id != project_id:
        raise HTTPException(
            status_code=400,
            detail="The selected character belongs to another project or no longer exists.",
        )


def _set_response(db: Session, value) -> CharacterSetResponse:
    response = CharacterSetResponse.model_validate(value)
    return response.model_copy(
        update={
            "approved_version_is_current": character_sets.approved_version_is_current(
                db, value
            )
        }
    )


def _service_error(exc: character_sets.CharacterSetError) -> HTTPException:
    status = 409
    if exc.code in {"missing_name", "invalid_slot", "no_slots"}:
        status = 422
    detail = str(exc)
    if exc.shot_ids:
        detail += " Affected shots: " + ", ".join(exc.shot_ids)
    return HTTPException(status_code=status, detail=detail)


@router.post("", response_model=CharacterSetResponse, status_code=201)
def create_character_set(
    project_id: str,
    payload: CharacterSetCreate,
    db: Session = Depends(get_db),
):
    _project(db, project_id)
    _validate_character(db, project_id, payload.character_id)
    try:
        value = character_sets.create_set(
            db, project_id=project_id, **payload.model_dump()
        )
    except character_sets.CharacterSetError as exc:
        raise _service_error(exc) from exc
    return _set_response(db, value)


@router.get("", response_model=list[CharacterSetResponse])
def list_character_sets(project_id: str, db: Session = Depends(get_db)):
    _project(db, project_id)
    return [_set_response(db, value) for value in character_sets.list_sets(db, project_id)]


@router.get("/{set_id}", response_model=CharacterSetResponse)
def get_character_set(project_id: str, set_id: str, db: Session = Depends(get_db)):
    return _set_response(db, _character_set(db, project_id, set_id))


@router.put("/{set_id}", response_model=CharacterSetResponse)
def update_character_set(
    project_id: str,
    set_id: str,
    payload: CharacterSetUpdate,
    db: Session = Depends(get_db),
):
    value = _character_set(db, project_id, set_id)
    changes = payload.model_dump(exclude_unset=True)
    if "character_id" in changes:
        _validate_character(db, project_id, changes["character_id"])
    try:
        value = character_sets.update_set(db, value, changes)
    except character_sets.CharacterSetError as exc:
        raise _service_error(exc) from exc
    return _set_response(db, value)


@router.delete("/{set_id}", status_code=204)
def delete_character_set(
    project_id: str,
    set_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    value = _character_set(db, project_id, set_id)
    try:
        detached = character_sets.delete_set(db, value, force=force)
    except character_sets.CharacterSetError as exc:
        raise _service_error(exc) from exc
    if detached:
        revisions.refresh_project(db, project_id)
    return Response(status_code=204)


@router.post("/{set_id}/versions", response_model=CharacterSetVersionResponse, status_code=201)
def create_character_set_version(
    project_id: str,
    set_id: str,
    payload: CharacterSetVersionCreate,
    db: Session = Depends(get_db),
):
    value = _character_set(db, project_id, set_id)
    try:
        return character_sets.create_version(
            db, value, slots=payload.slots, notes=payload.notes
        )
    except character_sets.CharacterSetError as exc:
        raise _service_error(exc) from exc


@router.get("/{set_id}/versions/{version_id}", response_model=CharacterSetVersionResponse)
def get_character_set_version(
    project_id: str,
    set_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    _character_set_value, version = _version(db, project_id, set_id, version_id)
    return version


@router.post(
    "/{set_id}/versions/{version_id}/generate",
    response_model=CharacterSetVersionResponse,
)
async def generate_character_set_version(
    project_id: str,
    set_id: str,
    version_id: str,
    payload: CharacterSetGenerateRequest,
    db: Session = Depends(get_db),
):
    project = _project(db, project_id)
    _character_set_value, version = _version(db, project_id, set_id, version_id)
    provider_id = (payload.provider_id or media_providers.COMFYUI).strip().lower()
    if provider_id not in {media_providers.COMFYUI, media_providers.OPENAI}:
        raise HTTPException(status_code=422, detail=f"Unknown media provider '{provider_id}'.")
    if media_providers.is_paid(provider_id) and not payload.confirm_paid_generation:
        raise HTTPException(
            status_code=409,
            detail=(
                "Character-set generation uses a metered provider. Re-send with "
                "confirm_paid_generation set to true to authorise it."
            ),
        )
    if not media_providers.is_configured(provider_id):
        env_name = media_providers.API_KEY_ENV.get(provider_id, "provider credentials")
        raise HTTPException(
            status_code=409,
            detail=f"This provider is not configured. Set {env_name} and restart.",
        )
    workflow_id = payload.workflow_id
    if provider_id == media_providers.COMFYUI and not workflow_id:
        workflow_id = project.default_image_workflow_id
    model = payload.model or media_providers.resolve_model(provider_id, payload.model)
    provider = media_providers.get_provider(provider_id)
    try:
        return await character_set_generation.generate_version(
            db,
            version,
            provider=provider,
            provider_id=provider_id,
            model=model,
            workflow_id=workflow_id,
            seed=payload.seed,
            width=payload.width,
            height=payload.height,
        )
    except character_set_generation.CharacterSetGenerationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{set_id}/versions/{version_id}/approve",
    response_model=CharacterSetVersionResponse,
)
def approve_character_set_version(
    project_id: str,
    set_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    _character_set_value, version = _version(db, project_id, set_id, version_id)
    try:
        version = character_sets.approve_version(db, version)
    except character_sets.CharacterSetError as exc:
        raise _service_error(exc) from exc
    revisions.refresh_project(db, project_id)
    return version


@router.post(
    "/{set_id}/versions/{version_id}/unapprove",
    response_model=CharacterSetVersionResponse,
)
def unapprove_character_set_version(
    project_id: str,
    set_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    _character_set_value, version = _version(db, project_id, set_id, version_id)
    version = character_sets.unapprove_version(db, version)
    revisions.refresh_project(db, project_id)
    return version
