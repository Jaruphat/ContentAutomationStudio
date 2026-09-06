"""Sound cues: a sound, a place in the cut, and a level.

Uploaded audio lands inside the project's own runtime directory, because the
render and the media endpoint both refuse to touch anything outside it - a
path from a request must never become a path the server reads.
"""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import paths
from app.database import get_db
from app.models import Project, SoundCue
from app.schemas import SoundCueCreate, SoundCueResponse, SoundCueUpload
from app.services import sound_cues

router = APIRouter(prefix="/api/projects/{project_id}/sound-cues", tags=["sound"])

#: What a cue may be. Deliberately narrow: these are decoded by FFmpeg into
#: the delivered programme, so the list is what has been tried.
AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def _project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/upload", response_model=SoundCueUpload, status_code=201)
async def upload_sound(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Store one audio file for this project and return the path a cue uses.

    The uploaded filename is kept only as a label; the bytes land under a name
    this application chose, inside this project's directory. Nothing the
    client sends decides where the file goes.
    """
    _project(db, project_id)
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{extension or 'that file'}' is not an audio format this "
                f"renderer has been used with. Use one of: "
                f"{', '.join(AUDIO_EXTENSIONS)}."
            ),
        )
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio files are limited to {MAX_UPLOAD_BYTES // (1 << 20)} MB.",
        )

    directory = os.path.join(paths.exports_dir(project_id), "audio")
    os.makedirs(directory, exist_ok=True)
    stored = os.path.join(directory, f"{uuid.uuid4()}{extension}")
    with open(stored, "wb") as handle:
        handle.write(data)
    return SoundCueUpload(
        file_path=stored,
        original_filename=file.filename or "",
        size_bytes=len(data),
    )


@router.post("", response_model=SoundCueResponse, status_code=201)
def create_sound_cue(
    project_id: str,
    payload: SoundCueCreate,
    db: Session = Depends(get_db),
):
    """Attach a sound to a moment inside a shot."""
    _project(db, project_id)
    try:
        cue = sound_cues.create_cue(
            db, project_id,
            shot_id=payload.shot_id,
            file_path=payload.file_path,
            offset_sec=payload.offset_sec,
            gain_db=payload.gain_db,
            label=payload.label,
        )
    except sound_cues.SoundCueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return cue


@router.get("", response_model=list[dict])
def list_sound_cues(project_id: str, db: Session = Depends(get_db)):
    """Every cue with the moment it currently lands at.

    Resolved against the cut as it stands rather than stored, so re-editing
    the film moves the sounds with it and the list says where they went.
    """
    _project(db, project_id)
    return sound_cues.resolve_cues(db, project_id)


@router.delete("/{cue_id}", status_code=204)
def delete_sound_cue(project_id: str, cue_id: str, db: Session = Depends(get_db)):
    _project(db, project_id)
    cue = (
        db.query(SoundCue)
        .filter(SoundCue.id == cue_id, SoundCue.project_id == project_id)
        .first()
    )
    if cue is None:
        raise HTTPException(status_code=404, detail="Sound cue not found")
    sound_cues.delete_cue(db, cue)
