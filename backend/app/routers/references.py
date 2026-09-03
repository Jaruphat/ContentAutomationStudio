"""
References router - the project's Visual Reference Bible.

Sheets are addressed under their project, so an id from another project simply
does not resolve here rather than being checked and then reported: the URL
itself carries the ownership constraint.

Uploads go through :mod:`app.services.reference_bible`, which validates the
bytes before anything is written. This module's job is to turn its refusals
into the right HTTP status, so a client can tell "wrong format" from "too
large" from "still in use" without parsing prose.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.schemas import (
    ReferenceImageResponse,
    ReferenceSheetCreate,
    ReferenceSheetResponse,
    ReferenceSheetUpdate,
)
from app.services import reference_bible, revisions

logger = logging.getLogger("cas.references")

router = APIRouter(
    prefix="/api/projects/{project_id}/references", tags=["references"]
)

#: How each refusal from the service layer is reported over HTTP.
_STATUS_FOR_CODE: dict[str, int] = {
    "invalid_kind": 422,
    "invalid_role": 422,
    "missing_name": 422,
    "empty_file": 422,
    "dimensions_out_of_range": 422,
    # The bytes are a real image container but do not decode as one whole
    # image: truncated, corrupt, or carrying a payload after the image ends.
    "malformed_image": 422,
    "image_too_large_to_decode": 422,
    "unsupported_media_type": 415,
    "file_too_large": 413,
    "reference_in_use": 409,
}


def _raise_for(exc: reference_bible.ReferenceBibleError) -> None:
    detail = str(exc)
    if exc.shot_ids:
        detail = f"{detail} Shots: {', '.join(exc.shot_ids)}."
    raise HTTPException(
        status_code=_STATUS_FOR_CODE.get(exc.code, 400), detail=detail
    )


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_sheet_or_404(db: Session, project_id: str, sheet_id: str):
    sheet = reference_bible.get_sheet(db, project_id, sheet_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail="Reference sheet not found")
    return sheet


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

@router.post("", response_model=ReferenceSheetResponse, status_code=201)
def create_reference_sheet(
    project_id: str,
    payload: ReferenceSheetCreate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    try:
        sheet = reference_bible.create_sheet(
            db, project_id=project_id, **payload.model_dump()
        )
    except reference_bible.ReferenceBibleError as exc:
        _raise_for(exc)
    return sheet


@router.get("", response_model=list[ReferenceSheetResponse])
def list_reference_sheets(project_id: str, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    return reference_bible.list_sheets(db, project_id)


@router.get("/{sheet_id}", response_model=ReferenceSheetResponse)
def get_reference_sheet(
    project_id: str, sheet_id: str, db: Session = Depends(get_db)
):
    _get_project_or_404(db, project_id)
    return _get_sheet_or_404(db, project_id, sheet_id)


@router.put("/{sheet_id}", response_model=ReferenceSheetResponse)
def update_reference_sheet(
    project_id: str,
    sheet_id: str,
    payload: ReferenceSheetUpdate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    sheet = _get_sheet_or_404(db, project_id, sheet_id)
    try:
        sheet = reference_bible.update_sheet(
            db, sheet, payload.model_dump(exclude_unset=True)
        )
    except reference_bible.ReferenceBibleError as exc:
        _raise_for(exc)
    # A changed identity invalidates exactly the shots that use this sheet.
    revisions.refresh_project(db, project_id)
    return sheet


@router.delete("/{sheet_id}", status_code=204)
def delete_reference_sheet(
    project_id: str,
    sheet_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    sheet = _get_sheet_or_404(db, project_id, sheet_id)
    try:
        reference_bible.delete_sheet(db, sheet, force=force)
    except reference_bible.ReferenceBibleError as exc:
        _raise_for(exc)
    revisions.refresh_project(db, project_id)
    return None


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

@router.post(
    "/{sheet_id}/images", response_model=ReferenceImageResponse, status_code=201
)
async def upload_reference_image(
    project_id: str,
    sheet_id: str,
    file: UploadFile = File(...),
    role: str = Form("canonical"),
    caption: str = Form(""),
    db: Session = Depends(get_db),
):
    """Attach a canonical image to a reference sheet.

    The uploaded filename is kept only as a label; the bytes are stored under a
    name derived from the new row's id, inside this project's reference
    directory. Nothing the client sends influences where the file lands.
    """
    _get_project_or_404(db, project_id)
    sheet = _get_sheet_or_404(db, project_id, sheet_id)

    data = await file.read()
    try:
        image = reference_bible.store_image(
            db,
            sheet=sheet,
            data=data,
            original_filename=file.filename or "",
            content_type=file.content_type or "",
            role=role,
            caption=caption,
        )
    except reference_bible.ReferenceBibleError as exc:
        _raise_for(exc)
    revisions.refresh_project(db, project_id)
    return image


@router.delete("/{sheet_id}/images/{image_id}", status_code=204)
def delete_reference_image(
    project_id: str,
    sheet_id: str,
    image_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    _get_project_or_404(db, project_id)
    _get_sheet_or_404(db, project_id, sheet_id)

    image = reference_bible.get_image(db, image_id)
    if image is None or image.sheet_id != sheet_id or image.project_id != project_id:
        raise HTTPException(status_code=404, detail="Reference image not found")

    try:
        reference_bible.delete_image(db, image, force=force)
    except reference_bible.ReferenceBibleError as exc:
        _raise_for(exc)
    revisions.refresh_project(db, project_id)
    return None
