"""
Projects router - Full CRUD for projects.
"""

import shutil
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import paths
from app.database import get_db
from app.models import GenerationJob, GenerationRun, Project, Take, Workflow
from app.schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services import generation_planning, revisions
from app.services.subtitle_service import SubtitleSettings, save_settings, settings_for_project

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _runnable_default_workflow(db: Session, purpose: str) -> str | None:
    """Pick the newest general-purpose local workflow for a new project."""
    candidates = (
        db.query(Workflow)
        .filter(
            Workflow.purpose == purpose,
            Workflow.source_format == "api",
            Workflow.validation_status == "valid",
        )
        .order_by(Workflow.updated_at.desc(), Workflow.created_at.desc())
        .all()
    )
    for workflow in candidates:
        mapping = workflow.parameter_mapping or {}
        if purpose == "image" and "referenceImage" in mapping:
            continue
        if workflow.output_mapping:
            return workflow.id
    return None


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    values = payload.model_dump()
    if "aspect_ratio" in payload.model_fields_set and "target_resolution" not in (
        payload.model_fields_set
    ):
        values["target_resolution"] = generation_planning.default_resolution(
            values["aspect_ratio"]
        )
    if not values["default_image_workflow_id"]:
        values["default_image_workflow_id"] = _runnable_default_workflow(db, "image")
    if not values["default_video_workflow_id"]:
        values["default_video_workflow_id"] = _runnable_default_workflow(
            db, "text-to-video"
        )
    project = Project(
        id=str(uuid.uuid4()),
        **values,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "aspect_ratio" in update_data and "target_resolution" not in update_data:
        update_data["target_resolution"] = generation_planning.default_resolution(
            update_data["aspect_ratio"]
        )
    for key, value in update_data.items():
        setattr(project, key, value)

    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    revisions.refresh_project(db, project_id)
    db.refresh(project)
    return project


@router.get("/{project_id}/subtitles", response_model=SubtitleSettings)
def get_subtitle_settings(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return settings_for_project(project)


@router.put("/{project_id}/subtitles", response_model=SubtitleSettings)
def update_subtitle_settings(
    project_id: str, payload: SubtitleSettings, db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    save_settings(project, payload)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return settings_for_project(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Runs are not ORM children of Project, so SQLite without PRAGMA
    # foreign_keys would otherwise leave them orphaned. Detach their job/take
    # links before deleting the runs; the normal project cascade removes those
    # jobs and takes moments later, while this ordering also works when foreign
    # key enforcement is enabled.
    run_ids = [
        row[0]
        for row in db.query(GenerationRun.id).filter(
            GenerationRun.project_id == project_id
        ).all()
    ]
    if run_ids:
        db.query(GenerationJob).filter(GenerationJob.run_id.in_(run_ids)).update(
            {GenerationJob.run_id: None}, synchronize_session=False
        )
        db.query(Take).filter(Take.run_id.in_(run_ids)).update(
            {Take.run_id: None}, synchronize_session=False
        )
        db.query(GenerationRun).filter(GenerationRun.id.in_(run_ids)).delete(
            synchronize_session=False
        )
    db.delete(project)
    db.commit()

    # The reference images are rows *and* files. Deleting the project takes the
    # rows with it through the ORM cascade; the bytes would otherwise be left
    # behind with nothing pointing at them.
    shutil.rmtree(paths.references_root(project_id), ignore_errors=True)
    return None
