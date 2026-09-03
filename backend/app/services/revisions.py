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

from app.models import Project, ReferenceImage, ReferenceSheet, Scene, Shot, Take
from app.services import prompt_context

logger = logging.getLogger("cas.revisions")

#: The take was generated from exactly the shot as it stands now.
LINEAGE_CURRENT = "current"
#: The take predates lineage tracking, so it can be proven neither current nor
#: stale. Written by a database that was migrated, never by a new generation.
LINEAGE_UNVERIFIED = "unverified"
#: The take records a lineage, and it is not this shot's.
LINEAGE_STALE = "stale"

#: Marker the migration writes onto a take whose lineage could not be
#: recovered. It makes "we never recorded this" a state of its own rather than
#: something indistinguishable from "this does not match".
LEGACY_LINEAGE_FLAG = "legacy_unverified_lineage"

#: Written alongside the flag: the shot revision the migration observed. It is
#: what turns "unverified" from a permanent excuse into a claim with an expiry.
LEGACY_BASELINE_FLAG = "legacy_baseline_revision"

#: The revision a migrated shot starts at, and therefore the baseline assumed
#: for a take flagged by a build that recorded no baseline of its own.
FIRST_TRACKED_REVISION = 1


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
        (
            shot.generated_revision
            and shot.generated_revision != shot.prompt_revision
        )
        or (
            shot.generated_content_sha256
            and shot.generated_content_sha256 != shot.content_sha256
        )
    )


def is_stale(shot: Shot) -> bool:
    return bool(
        (
            shot.generated_revision
            and shot.generated_revision != shot.prompt_revision
        )
        or (
            shot.generated_content_sha256
            and shot.generated_content_sha256 != shot.content_sha256
        )
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
            had_content_baseline = bool(shot.content_sha256)
            digest = shot_digest(
                db, shot, scene=scene, bible=bible, project_id=project_id
            )
            if apply_digest(shot, digest):
                advanced.append(shot.id)
                # Editing delivered content revokes the shot-level approval.
                # Historical takes keep their review records, but the edited
                # shot must return to an eligible state until a current take is
                # generated and approved.
                if had_content_baseline and shot.status == "Approved":
                    shot.status = "Ready"
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


def mark_generated_if_current(
    db: Session,
    shot: Shot,
    content_sha256: str,
    digest: ShotDigest | None = None,
) -> bool:
    """Record a generation only when it was built from the shot as it stands.

    A job can finish long after the shot it was compiled from was edited.
    Clearing staleness on that shot would claim the delivered media matches a
    brief it was never generated against, so the job's own recorded digest is
    compared with the shot's current one and the generation is only credited
    when the two agree. The digest is refreshed either way, so the shot's
    revision and ``is_stale`` flag stay accurate.

    Returns True when the generation was credited to the current revision.
    """
    if digest is None:
        digest = shot_digest(db, shot)
    apply_digest(shot, digest)
    matches = bool(content_sha256) and shot.content_sha256 == content_sha256
    if matches:
        shot.generated_revision = shot.prompt_revision
        shot.generated_content_sha256 = shot.content_sha256
    elif content_sha256:
        # A first job can become stale before the shot has any credited
        # generation revision. Keep its submitted digest as durable evidence
        # that output exists for older content without pretending revision zero
        # generated the edited shot.
        shot.generated_content_sha256 = content_sha256
    _sync_staleness(shot)
    return matches


# ---------------------------------------------------------------------------
# Take lineage
# ---------------------------------------------------------------------------

def is_legacy_lineage(take: Take) -> bool:
    """Whether the migration marked this take's lineage as unrecoverable."""
    lineage = take.lineage if isinstance(take.lineage, dict) else {}
    return bool(lineage.get(LEGACY_LINEAGE_FLAG))


def legacy_baseline_revision(take: Take) -> int:
    """The shot revision a legacy take is unverifiable *at*.

    A database migrated by a build that predates this records the flag without
    a baseline; those takes fall back to the revision a migrated shot starts
    at, which is what the migration would have written anyway.
    """
    lineage = take.lineage if isinstance(take.lineage, dict) else {}
    value = lineage.get(LEGACY_BASELINE_FLAG)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return FIRST_TRACKED_REVISION
    return value


def take_lineage_state(take: Take, shot: Shot) -> str:
    """Classify a take against the shot as it stands now.

    Three answers, not two: a take written before lineage was recorded cannot
    be proven current, but neither can it be called stale. Collapsing that into
    "does not match" is what silently drops migrated approved work off the cut.

    Unverified is bounded, though. It says "this take predates lineage
    tracking, and the shot has not moved since the migration looked at it" -
    which stops being true the moment someone edits the shot or its references.
    Past that baseline the take is no longer merely unproven; the shot it was
    generated from demonstrably no longer exists, so it is stale like any
    other take of a superseded revision.
    """
    if take is None or shot is None or take.shot_id != shot.id:
        return LINEAGE_STALE
    if is_legacy_lineage(take) or not (take.prompt_sha256 or take.content_sha256):
        current = shot.prompt_revision or FIRST_TRACKED_REVISION
        if current > legacy_baseline_revision(take):
            return LINEAGE_STALE
        return LINEAGE_UNVERIFIED
    if (
        take.prompt_revision == shot.prompt_revision
        and take.prompt_sha256 == shot.prompt_sha256
        and take.content_sha256 == shot.content_sha256
        and list(take.reference_image_ids or []) == list(shot.reference_asset_ids or [])
        and list(take.reference_sha256s or []) == list(shot.reference_sha256s or [])
    ):
        return LINEAGE_CURRENT
    return LINEAGE_STALE
