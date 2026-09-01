"""
Exports router - Storyboard, prompts, manifest, and project archive exports.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.services import export_service

router = APIRouter(prefix="/api/projects/{project_id}/export", tags=["exports"])


def _get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/storyboard")
def export_storyboard(
    project_id: str,
    format: str = Query("json", pattern="^(json|csv|markdown)$"),
    db: Session = Depends(get_db),
):
    """
    Export the project storyboard in JSON, CSV, or Markdown format.
    """
    _get_project_or_404(db, project_id)

    if format == "json":
        data = export_service.export_storyboard_json(db, project_id)
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": f'attachment; filename="storyboard_{project_id}.json"'},
        )
    elif format == "csv":
        csv_content = export_service.export_storyboard_csv(db, project_id)
        return PlainTextResponse(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="storyboard_{project_id}.csv"'},
        )
    elif format == "markdown":
        md_content = export_service.export_storyboard_markdown(db, project_id)
        return PlainTextResponse(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="storyboard_{project_id}.md"'},
        )


@router.get("/prompts")
def export_prompts(project_id: str, db: Session = Depends(get_db)):
    """
    Export all compiled prompts for the project.
    """
    _get_project_or_404(db, project_id)
    data = export_service.export_prompts(db, project_id)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="prompts_{project_id}.json"'},
    )


@router.get("/manifest")
def export_manifest(project_id: str, db: Session = Depends(get_db)):
    """
    Export the generation manifest (all jobs with provenance).
    """
    _get_project_or_404(db, project_id)
    data = export_service.export_generation_manifest(db, project_id)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="manifest_{project_id}.json"'},
    )


@router.get("/timeline-manifest")
def export_timeline_manifest(project_id: str, db: Session = Depends(get_db)):
    """
    Export the timeline manifest.
    """
    _get_project_or_404(db, project_id)
    data = export_service.export_timeline_manifest(db, project_id)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="timeline_{project_id}.json"'},
    )


@router.get("/project-archive")
def export_project_archive(project_id: str, db: Session = Depends(get_db)):
    """
    Export the complete project metadata as a JSON archive.
    Includes project, story bible, scenes, shots, jobs, takes, and timeline.
    Does NOT include binary media files.
    """
    _get_project_or_404(db, project_id)
    data = export_service.export_project_archive(db, project_id)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f'attachment; filename="archive_{project_id}.json"'},
    )
