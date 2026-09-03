"""
Content revisions and selective staleness.

Every shot carries a digest of everything a generation of it would depend on:
its own fields, its scene, the Story Bible entries that actually reach it, and
the reference images it is conditioned on. When that digest moves, the shot's
``prompt_revision`` advances - and if the shot had already been generated, it
becomes *stale*: its approved take no longer matches the brief it would be
delivered under.

Two properties matter and are tested directly:

* **Selective.** A shot whose digest did not move is left completely alone -
  same revision, same status, same approved takes. Editing one character must
  not invalidate the scenes it does not appear in.
* **Non-destructive.** Staleness is a flag, never a deletion. Approved takes
  from every revision are kept as history; the timeline decides what to place.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Project, ReferenceImage, ReferenceSheet, Scene, Shot
from app.services import prompt_context

logger = logging.getLogger("cas.revisions")


@dataclass
class ShotDigest:
    """What a shot would currently be generated from."""

    prompt_sha256: str
    content_sha256: str
    positive_prompt: str = ""
    negative_prompt: str = ""
    reference_image_ids: list[str] = field(default_factory=list)
    reference_sha256s: list[str] = field(default_factory=list)


def _sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _reference_fingerprint(
    db: Session, project_id: str, reference_ids: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Resolve a shot's references into (ids, image hashes, sheet digests).

    Rows are read directly rather than through ``reference_bible.resolve_images``
    because a digest must not depend on whether the file happens to be readable
    right now: a missing file is a preflight blocker, not a content change.
    Unknown ids are still folded in as a sentinel, so a shot pointing at a
    deleted reference is visibly different from one pointing at nothing.
    """
    if not reference_ids:
        return [], [], []

    found = {
        image.id: image
        for image in db.query(ReferenceImage)
        .filter(ReferenceImage.id.in_(reference_ids))
        .all()
    }
    sheet_ids = {
        image.sheet_id for image in found.values() if image.project_id == project_id
    }
    sheets = (
        {
            sheet.id: sheet
            for sheet in db.query(ReferenceSheet)
            .filter(ReferenceSheet.id.in_(sheet_ids))
            .all()
        }
        if sheet_ids
        else {}
    )

    ids: list[str] = []
    hashes: list[str] = []
    sheet_digests: list[str] = []
    for reference_id in reference_ids:
        image = found.get(reference_id)
        if image is None or image.project_id != project_id:
            ids.append(reference_id)
            hashes.append("")
            sheet_digests.append("unresolved")
            continue
        ids.append(image.id)
        hashes.append(image.sha256 or "")
        sheet = sheets.get(image.sheet_id)
        sheet_digests.append(sheet.content_sha256 if sheet else "")
    return ids, hashes, sheet_digests


def shot_digest(
    db: Session,
    shot: Shot,
    *,
    scene: Scene | None = None,
    bible: dict[str, list[dict[str, Any]]] | None = None,
    project_id: str = "",
) -> ShotDigest:
    """Everything about a shot that a generation would depend on, hashed."""
    context = prompt_context.compile_for_shot(db, shot, scene=scene, bible=bible)
    if not project_id:
        resolved_scene = scene or db.query(Scene).filter(
            Scene.id == shot.scene_id
        ).first()
        project_id = resolved_scene.project_id if resolved_scene else ""

    prompt_sha256 = _sha256({
        "positive": context.compiled.positive_prompt,
        "negative": context.compiled.negative_prompt,
    })

    reference_ids, reference_hashes, sheet_digests = _reference_fingerprint(
        db, project_id, list(shot.reference_asset_ids or [])
    )
    project = db.query(Project).filter(Project.id == project_id).first()

    content_sha256 = _sha256({
        "prompt": prompt_sha256,
        # Routing and duration change what is produced, but never appear in the
        # prompt text, so they are hashed alongside it.
        "generation_mode": shot.generation_mode or "image",
        "planned_duration_sec": float(shot.planned_duration_sec or 0.0),
        "workflow_preset_id": shot.workflow_preset_id or "",
        "image_provider_id": shot.image_provider_id or "",
        "image_model": shot.image_model or "",
        "aspect_ratio": project.aspect_ratio if project else "",
        "target_resolution": project.target_resolution if project else "",
        "frame_rate": float(project.frame_rate or 0.0) if project else 0.0,
        "default_image_workflow_id": (
            project.default_image_workflow_id if project else ""
        ),
        "default_video_workflow_id": (
            project.default_video_workflow_id if project else ""
        ),
        "reference_image_ids": reference_ids,
        "reference_sha256s": reference_hashes,
        "reference_sheet_sha256s": sheet_digests,
    })

    return ShotDigest(
        prompt_sha256=prompt_sha256,
        content_sha256=content_sha256,
        positive_prompt=context.compiled.positive_prompt,
        negative_prompt=context.compiled.negative_prompt,
        reference_image_ids=reference_ids,
        reference_sha256s=reference_hashes,
    )


def apply_digest(shot: Shot, digest: ShotDigest) -> bool:
    """Store a digest on a shot, advancing its revision if it moved.

    Returns True when the revision advanced. The first digest a shot ever gets
    is recorded without advancing: a shot created a moment ago is at revision 1,
    not revision 2.
    """
    if digest.content_sha256 == shot.content_sha256:
        # Keep the derived fields fresh even when the digest is unchanged, so a
        # database written before these columns existed backfills quietly.
        shot.prompt_sha256 = digest.prompt_sha256
        shot.reference_sha256s = list(digest.reference_sha256s)
        return False

    if shot.content_sha256:
        shot.prompt_revision = (shot.prompt_revision or 1) + 1
    elif not shot.prompt_revision:
        shot.prompt_revision = 1

    shot.content_sha256 = digest.content_sha256
    shot.prompt_sha256 = digest.prompt_sha256
    shot.reference_sha256s = list(digest.reference_sha256s)
    return True


def _sync_staleness(shot: Shot) -> None:
    """A shot is stale exactly when what it produced is not what it now is."""
    shot.is_stale = bool(
        shot.generated_revision
        and shot.generated_revision != shot.prompt_revision
    )


def is_stale(shot: Shot) -> bool:
    return bool(
        shot.generated_revision
        and shot.generated_revision != shot.prompt_revision
    )


def refresh_project(db: Session, project_id: str) -> list[str]:
    """Recompute every shot's digest; return the ids whose revision advanced.

    Idempotent, so it is safe to call after any mutation and again before any
    read that depends on it. Loading the Story Bible once and reusing it across
    the project keeps this a handful of queries rather than one set per shot.
    """
    if not project_id:
        return []

    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )
    if not scenes:
        return []

    bible = prompt_context.story_bible(db, project_id)
    advanced: list[str] = []

    for scene in scenes:
        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        for shot in shots:
            digest = shot_digest(
                db, shot, scene=scene, bible=bible, project_id=project_id
            )
            if apply_digest(shot, digest):
                advanced.append(shot.id)
            _sync_staleness(shot)

    db.commit()
    if advanced:
        logger.info(
            "Project %s: %d shot(s) advanced a content revision",
            project_id, len(advanced),
        )
    return advanced


def mark_generated(db: Session, shot: Shot, digest: ShotDigest | None = None) -> None:
    """Record that this shot has been generated at its current revision."""
    if digest is None:
        digest = shot_digest(db, shot)
    apply_digest(shot, digest)
    shot.generated_revision = shot.prompt_revision
    shot.generated_content_sha256 = shot.content_sha256
    _sync_staleness(shot)
