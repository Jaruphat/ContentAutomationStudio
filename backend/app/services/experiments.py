"""Freeze one shot's effective inputs into an independent experiment project."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app import paths
from app.models import Project, ReferenceImage, ReferenceSheet, Scene, Shot
from app.services import generation_planning, prompt_context, reference_bible, revisions, shot_conditioning


def create_from_shot(db: Session, shot: Shot) -> Project:
    scene = db.get(Scene, shot.scene_id)
    project = db.get(Project, scene.project_id) if scene else None
    if project is None:
        raise ValueError("The source shot has no project")
    plan = generation_planning.plan_shot(db, project, shot)
    resolved = shot_conditioning.resolve(db, project.id, shot)
    if plan.provider_id == "comfyui":
        resolved = shot_conditioning.select_for_submission(
            resolved,
            max_images=shot_conditioning.workflow_capacity(db, plan.workflow_id),
            min_images=shot_conditioning.workflow_minimum(db, plan.workflow_id),
        )
    if resolved.problems:
        raise ValueError("Resolve the source inputs before copying: " + " ".join(resolved.problems))
    if resolved.end_frame:
        raise ValueError("This shot has a landing-frame binding. Create an experiment from a shot without that binding; it cannot be silently dropped.")
    context = prompt_context.compile_for_shot(db, shot)
    # Read and verify everything before creating rows or files. The copied
    # images must have their own bytes: changing/deleting the source cannot
    # invalidate the experimental project's references later.
    inputs = []
    for entry in resolved.submitted_images:
        source = entry.image
        if not paths.is_within_data_dir(source.file_path):
            raise ValueError("A source reference is outside the application's data directory")
        data = Path(source.file_path).read_bytes()
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise ValueError("A source reference has changed on disk; re-import it before experimenting")
        inputs.append((source, data))
    target = Project(
        id=str(uuid.uuid4()), title=f"Experiment — {shot.shot_type or scene.title or project.title}",
        objective="Compare generation settings using a frozen copy of one shot's inputs.",
        aspect_ratio=project.aspect_ratio, target_resolution=project.target_resolution,
        frame_rate=project.frame_rate, target_duration_sec=shot.planned_duration_sec,
        language=project.language, default_image_workflow_id=plan.workflow_id,
        default_video_workflow_id=plan.workflow_id, status="Draft",
        brief_text=json.dumps({"experiment_source": {"project_id": project.id,
            "shot_id": shot.id, "prompt_revision": shot.prompt_revision,
            "content_sha256": shot.content_sha256}}, indent=2),
    )
    created_files: list[Path] = []
    try:
        db.add(target)
        sheet = ReferenceSheet(id=str(uuid.uuid4()), project_id=target.id,
                               kind="location", name="Frozen generation inputs", revision=1)
        db.add(sheet)
        sheet.content_sha256 = reference_bible.sheet_content_digest(sheet)
        refs = []
        for source, data in inputs:
            iid = str(uuid.uuid4())
            name = iid + Path(source.file_path).suffix.lower()
            dest = Path(paths.references_dir(target.id)) / name
            dest.write_bytes(data)
            created_files.append(dest)
            image = ReferenceImage(id=iid, project_id=target.id, sheet_id=sheet.id,
                role="canonical", original_filename=source.original_filename,
                stored_filename=name, file_path=str(dest), mime_type=source.mime_type,
                size_bytes=len(data), width=source.width, height=source.height, sha256=source.sha256,
                caption=source.caption, provenance={"source": "experiment_copy",
                    "source_project_id": project.id, "source_image_id": source.id,
                    "sha256": source.sha256})
            db.add(image)
            refs.append(iid)
        new_scene = Scene(id=str(uuid.uuid4()), project_id=target.id, order=1,
                          title=shot.shot_type or scene.title or "Experiment")
        db.add(new_scene)
        new_shot = Shot(id=str(uuid.uuid4()), scene_id=new_scene.id, order=1,
            generation_mode=shot.generation_mode, planned_duration_sec=shot.planned_duration_sec,
            image_prompt=context.compiled.positive_prompt if shot.generation_mode == "image" else "",
            video_prompt=context.compiled.positive_prompt if shot.generation_mode != "image" else "",
            negative_prompt=context.compiled.negative_prompt, reference_asset_ids=refs,
            workflow_preset_id=plan.workflow_id, image_provider_id=plan.provider_id,
            image_model=plan.model, seed_policy="fixed", seed=shot.seed if shot.seed is not None else 42,
            dialogue=shot.dialogue, status="Draft")
        db.add(new_shot)
        db.flush()
        digest = revisions.shot_digest(db, new_shot)
        revisions.apply_digest(new_shot, digest)
        db.commit()
        db.refresh(target)
        return target
    except Exception:
        db.rollback()
        for file in created_files:
            file.unlink(missing_ok=True)
        raise
