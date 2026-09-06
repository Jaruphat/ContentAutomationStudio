"""Everything needed to upload, in one place, with the gate in front of it.

The pipeline used to end at a rendered MP4 and a pile of manifests. Uploading
meant finding the file, writing a title somewhere else, remembering the series
label, copying hashtags out of a document and grabbing a thumbnail by
scrubbing. Every one of those is a place to publish the wrong thing.

Two rules make this worth having rather than a folder of conventions. Not ready
is the default and every blocker is named - a package that reports ready when
it is not is worse than none, because it is believed. And nothing is invented:
a missing title is a missing title, never the project's working name quietly
promoted into the world.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import paths
from app.database import get_db
from app.models import Project, QualityReview, TimelineItem
from app.schemas import PublishFieldsRequest, PublishPackage
from app.services import media_probe, quality_gate, render_identity

router = APIRouter(tags=["publishing"])


def _project(db: Session, project_id: str) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put(
    "/api/projects/{project_id}/publish", response_model=PublishPackage
)
def set_publish_fields(
    project_id: str,
    payload: PublishFieldsRequest,
    db: Session = Depends(get_db),
):
    """Set the title, series label, description and hashtags."""
    project = _project(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(project, field, value)
    db.commit()
    return build_package(db, project)


@router.get(
    "/api/projects/{project_id}/publish-package", response_model=PublishPackage
)
def get_publish_package(project_id: str, db: Session = Depends(get_db)):
    return build_package(db, _project(db, project_id))


def build_package(db: Session, project: Project) -> PublishPackage:
    """Assemble the package and decide, out loud, whether it can go out."""
    blockers: list[str] = []
    warnings: list[str] = []

    video_path = os.path.join(paths.exports_dir(project.id), "review.mp4")
    has_render = os.path.isfile(video_path)
    if not has_render:
        blockers.append(
            "There is no render for this episode. Build the timeline and "
            "press Render Review."
        )

    review = (
        db.query(QualityReview)
        .filter(QualityReview.project_id == project.id)
        .order_by(QualityReview.created_at.desc(), QualityReview.id.desc())
        .first()
    )
    if review is None:
        blockers.append(
            "This episode has not passed a quality review. Score it against "
            "the rubric before publishing."
        )
    elif not review.passed:
        # Carry the shortfalls forward rather than saying only that something
        # fell short: "not good enough" changes nothing on its own.
        result = quality_gate.evaluate(
            dict(review.scores or {}),
            ai_tell=bool(review.ai_tell),
            ai_tell_causes=review.ai_tell_causes or "recorded",
        )
        blockers.extend(result.reasons)

    reviewed_render = bool(review and review.render_sha256 and has_render
        and review.render_sha256 == render_identity.render_sha256(project.id))
    if review and review.passed and not reviewed_render:
        blockers.append(
            "The quality review does not identify this video. Render the current "
            "cut, watch it, and record a new quality review."
        )

    if has_render:
        modified = datetime.fromtimestamp(os.path.getmtime(video_path), tz=timezone.utc)
        items = db.query(TimelineItem).filter(TimelineItem.project_id == project.id).all()
        if any((item.updated_at or item.created_at).replace(tzinfo=timezone.utc) > modified
               for item in items if item.updated_at or item.created_at):
            blockers.append("The timeline changed after this video was rendered. Render and review the current cut.")

    if not (project.publish_title or "").strip():
        warnings.append(
            "No publish title. The project's working title is not used for "
            "this - name the episode as it should appear."
        )
    if not (project.pillar or "").strip():
        warnings.append(
            "No pillar recorded, so this episode cannot be compared against "
            "the others afterwards - and afterwards is too late to record it."
        )

    probe = media_probe.probe_media_file(video_path) if has_render else {}
    if has_render and not (probe.get("duration_sec", 0) > 0
                           and probe.get("width", 0) > 0 and probe.get("height", 0) > 0):
        blockers.append("The rendered file is not a readable video. Render the timeline again.")
    subtitle_path = os.path.join(paths.exports_dir(project.id), "subtitles.srt")

    return PublishPackage(
        project_id=project.id,
        ready=not blockers,
        blockers=blockers,
        warnings=warnings,
        publish_title=project.publish_title or "",
        series_label=project.series_label or "",
        publish_description=project.publish_description or "",
        publish_hashtags=project.publish_hashtags or "",
        pillar=project.pillar or "",
        hook_type=project.hook_type or "",
        ending_type=project.ending_type or "",
        premise=project.premise or "",
        video_url=(
            f"/api/projects/{project.id}/render/file" if has_render else ""
        ),
        video_path=video_path if has_render else "",
        duration_sec=float(probe.get("duration_sec") or 0.0),
        width=int(probe.get("width") or 0),
        height=int(probe.get("height") or 0),
        subtitle_path=subtitle_path if os.path.isfile(subtitle_path) else "",
        quality_passed=bool(review and review.passed and reviewed_render),
    )
