"""
Visual Reference Bible.

A project's reference sheets are its identity record: what a character, a
recurring prop or a location must look like in every shot, as prose *and* as
canonical images a reference-conditioned workflow can be given.

Three rules hold everywhere in this module:

* **Ownership is checked, not assumed.** Every image carries its project id and
  every lookup filters on it, so an id from another project resolves to nothing
  rather than to someone else's artwork.
* **The upload never chooses its path.** Stored filenames are built from the
  row's own UUID (see :mod:`app.services.image_validation`), and the bytes land
  under ``paths.references_dir(project_id)`` and nowhere else.
* **Identity has a digest.** ``content_sha256`` covers a sheet's prose and the
  hashes of its images, so "did anything change that would alter a generation?"
  is one comparison - which is what selective staleness is built on.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import ReferenceImage, ReferenceSheet, Scene, Shot
from app.services import image_validation

logger = logging.getLogger("cas.reference_bible")

#: What a reference sheet may describe. Deliberately closed: each kind has a
#: different meaning downstream, and an unrecognised one would silently never
#: be applied.
#: A sheet holding end frames lifted from approved takes. Kept as a kind of
#: its own so continuity stills are stored, validated and conditioned through
#: exactly the same path as a hand-uploaded plate, while still being
#: distinguishable from art direction someone chose.
KIND_CONTINUITY = "continuity"

SHEET_KINDS: tuple[str, ...] = ("character", "prop", "location", KIND_CONTINUITY)

#: Roles an image may play on its sheet. "canonical" is what generation uses.
IMAGE_ROLES: tuple[str, ...] = ("canonical", "support")

#: Sheet fields a client may write. Anything else - id, project, revision,
#: digest - is ours.
EDITABLE_SHEET_FIELDS: tuple[str, ...] = (
    "kind",
    "name",
    "subject_ref_id",
    "canonical_description",
    "identity_tokens",
    "negative_tokens",
    "notes",
)


class ReferenceBibleError(Exception):
    """A reference operation was refused, with a machine-readable reason."""

    def __init__(self, message: str, code: str, *, shot_ids: list[str] | None = None):
        super().__init__(message)
        self.code = code
        #: Populated for ``reference_in_use``: the shots still relying on it.
        self.shot_ids = shot_ids or []


@dataclass(frozen=True)
class ReferenceProblem:
    """One reason a requested reference cannot be used."""

    reference_id: str
    code: str
    message: str


# ---------------------------------------------------------------------------
# Digests
# ---------------------------------------------------------------------------

def _digest(payload: Any) -> str:
    """Stable SHA-256 over a JSON-serialisable structure."""
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sheet_content_digest(sheet: ReferenceSheet) -> str:
    """Everything about a sheet that could change a generation.

    Image *hashes* are included rather than image ids: replacing an image with
    identical bytes is not a change, and re-uploading the same plate should not
    invalidate a shot that was already generated from it.
    """
    return _digest({
        "kind": sheet.kind or "",
        "name": sheet.name or "",
        "canonical_description": sheet.canonical_description or "",
        "identity_tokens": sheet.identity_tokens or "",
        "negative_tokens": sheet.negative_tokens or "",
        "images": sorted(
            (image.sha256 or "", image.role or "") for image in (sheet.images or [])
        ),
    })


def _resync_sheet(db: Session, sheet: ReferenceSheet) -> bool:
    """Recompute a sheet's digest, bumping its revision when it moved.

    Returns True when the identity actually changed. A no-op edit leaves the
    revision alone so a save button cannot invalidate approved work.
    """
    digest = sheet_content_digest(sheet)
    if digest == sheet.content_sha256:
        return False
    if sheet.content_sha256:
        sheet.revision = (sheet.revision or 1) + 1
    sheet.content_sha256 = digest
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def create_sheet(
    db: Session,
    *,
    project_id: str,
    kind: str,
    name: str,
    subject_ref_id: str | None = None,
    canonical_description: str = "",
    identity_tokens: str = "",
    negative_tokens: str = "",
    notes: str = "",
) -> ReferenceSheet:
    """Create a reference sheet for a project."""
    normalised_kind = (kind or "").strip().lower()
    if normalised_kind not in SHEET_KINDS:
        raise ReferenceBibleError(
            f"'{kind}' is not a reference kind. Use one of: "
            f"{', '.join(SHEET_KINDS)}.",
            "invalid_kind",
        )
    if not (name or "").strip():
        raise ReferenceBibleError(
            "A reference sheet needs a name so it can be recognised in the "
            "storyboard.",
            "missing_name",
        )

    sheet = ReferenceSheet(
        project_id=project_id,
        kind=normalised_kind,
        name=name.strip(),
        subject_ref_id=subject_ref_id or None,
        canonical_description=canonical_description or "",
        identity_tokens=identity_tokens or "",
        negative_tokens=negative_tokens or "",
        notes=notes or "",
        revision=1,
    )
    db.add(sheet)
    db.flush()
    sheet.content_sha256 = sheet_content_digest(sheet)
    db.commit()
    db.refresh(sheet)
    return sheet


def update_sheet(
    db: Session, sheet: ReferenceSheet, changes: dict[str, Any]
) -> ReferenceSheet:
    """Apply an edit to a sheet, advancing its revision only if it moved."""
    if "kind" in changes and changes["kind"] is not None:
        kind = str(changes["kind"]).strip().lower()
        if kind not in SHEET_KINDS:
            raise ReferenceBibleError(
                f"'{changes['kind']}' is not a reference kind. Use one of: "
                f"{', '.join(SHEET_KINDS)}.",
                "invalid_kind",
            )
        changes = {**changes, "kind": kind}
    if "name" in changes and changes["name"] is not None:
        if not str(changes["name"]).strip():
            raise ReferenceBibleError(
                "A reference sheet needs a name.", "missing_name",
            )
        changes = {**changes, "name": str(changes["name"]).strip()}

    for field, value in changes.items():
        if field in EDITABLE_SHEET_FIELDS and value is not None:
            setattr(sheet, field, value)

    _resync_sheet(db, sheet)
    db.commit()
    db.refresh(sheet)
    return sheet


def list_sheets(db: Session, project_id: str) -> list[ReferenceSheet]:
    """Every sheet in a project, grouped by kind then name."""
    return (
        db.query(ReferenceSheet)
        .filter(ReferenceSheet.project_id == project_id)
        .order_by(ReferenceSheet.kind, ReferenceSheet.name)
        .all()
    )


def get_sheet(db: Session, project_id: str, sheet_id: str) -> ReferenceSheet | None:
    """Fetch one sheet, scoped to its project so a foreign id simply misses."""
    return (
        db.query(ReferenceSheet)
        .filter(
            ReferenceSheet.id == sheet_id,
            ReferenceSheet.project_id == project_id,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def store_image(
    db: Session,
    *,
    sheet: ReferenceSheet,
    data: bytes,
    original_filename: str = "",
    content_type: str = "",
    role: str = "canonical",
    caption: str = "",
    source: str = "upload",
    source_detail: dict[str, Any] | None = None,
) -> ReferenceImage:
    """Validate, persist and register one canonical image for a sheet.

    Re-uploading bytes the sheet already holds returns the existing record
    rather than creating a duplicate: the store is content-addressed, so the
    same plate is one row and one file however many times it is submitted.
    """
    try:
        inspected = image_validation.validate_image_bytes(
            data,
            declared_content_type=content_type,
            declared_filename=original_filename,
        )
    except image_validation.ImageValidationError as exc:
        raise ReferenceBibleError(str(exc), exc.code) from exc

    normalised_role = (role or "canonical").strip().lower()
    if normalised_role not in IMAGE_ROLES:
        raise ReferenceBibleError(
            f"'{role}' is not a reference image role. Use one of: "
            f"{', '.join(IMAGE_ROLES)}.",
            "invalid_role",
        )

    existing = (
        db.query(ReferenceImage)
        .filter(
            ReferenceImage.sheet_id == sheet.id,
            ReferenceImage.sha256 == inspected.sha256,
        )
        .first()
    )
    if existing is not None and os.path.isfile(existing.file_path):
        logger.info(
            "Reference image %s already holds these bytes; reusing it",
            existing.id,
        )
        return existing

    image = ReferenceImage(
        sheet_id=sheet.id,
        project_id=sheet.project_id,
        role=normalised_role,
        original_filename=image_validation.safe_display_filename(original_filename),
        mime_type=inspected.mime_type,
        size_bytes=inspected.size_bytes,
        width=inspected.width,
        height=inspected.height,
        sha256=inspected.sha256,
        caption=caption or "",
    )
    db.add(image)
    db.flush()  # assigns the id the filename is derived from

    image.stored_filename = image_validation.stored_filename(
        image.id, inspected.extension
    )
    destination = os.path.join(
        paths.references_dir(sheet.project_id), image.stored_filename
    )
    _write_atomic(destination, data)
    image.file_path = destination
    image.provenance = {
        "source": source,
        "sha256": inspected.sha256,
        "mime_type": inspected.mime_type,
        "width": inspected.width,
        "height": inspected.height,
        "size_bytes": inspected.size_bytes,
        "original_filename": image.original_filename,
        **(source_detail or {}),
    }

    db.flush()
    db.refresh(sheet)
    _resync_sheet(db, sheet)
    db.commit()
    db.refresh(image)
    return image


def _write_atomic(destination: str, data: bytes) -> None:
    """Write bytes via temp-and-rename so a crash leaves no partial image."""
    tmp = destination + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, destination)


def get_image(db: Session, image_id: str) -> ReferenceImage | None:
    return db.query(ReferenceImage).filter(ReferenceImage.id == image_id).first()


def shots_using(db: Session, image_ids: list[str]) -> list[Shot]:
    """Every shot that names one of these reference images.

    ``reference_asset_ids`` is a JSON list, which SQLite cannot index into
    portably, so the membership test happens in Python over the project's
    shots. Projects here hold tens of shots, not millions.
    """
    if not image_ids:
        return []
    wanted = set(image_ids)
    project_ids = {
        row.project_id
        for row in db.query(ReferenceImage)
        .filter(ReferenceImage.id.in_(image_ids))
        .all()
    }
    if not project_ids:
        return []
    shots = (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Scene.project_id.in_(project_ids))
        .all()
    )
    return [s for s in shots if wanted & set(s.reference_asset_ids or [])]


def delete_image(
    db: Session, image: ReferenceImage, *, force: bool = False
) -> list[str]:
    """Delete one reference image; returns the shot ids that were detached.

    A reference a shot still points at is refused by default: deleting it would
    leave that shot silently un-conditioned at the next generation. ``force``
    is the explicit override, and it detaches the shots rather than leaving
    dangling ids behind.
    """
    dependents = shots_using(db, [image.id])
    if dependents and not force:
        raise ReferenceBibleError(
            f"{len(dependents)} shot(s) still use this reference image. "
            f"Remove it from those shots first, or delete it with force to "
            f"detach them.",
            "reference_in_use",
            shot_ids=[s.id for s in dependents],
        )

    detached: list[str] = []
    for shot in dependents:
        shot.reference_asset_ids = [
            ref for ref in (shot.reference_asset_ids or []) if ref != image.id
        ]
        detached.append(shot.id)

    file_path = image.file_path
    sheet = image.sheet
    db.delete(image)
    db.flush()
    if sheet is not None:
        db.refresh(sheet)
        _resync_sheet(db, sheet)
    db.commit()

    _remove_quietly(file_path)
    return detached


def delete_sheet(
    db: Session, sheet: ReferenceSheet, *, force: bool = False
) -> list[str]:
    """Delete a sheet and every image on it; returns detached shot ids."""
    image_ids = [image.id for image in (sheet.images or [])]
    dependents = shots_using(db, image_ids)
    if dependents and not force:
        raise ReferenceBibleError(
            f"{len(dependents)} shot(s) still use images from this reference "
            f"sheet. Remove them from those shots first, or delete the sheet "
            f"with force to detach them.",
            "reference_in_use",
            shot_ids=[s.id for s in dependents],
        )

    detached: list[str] = []
    wanted = set(image_ids)
    for shot in dependents:
        shot.reference_asset_ids = [
            ref for ref in (shot.reference_asset_ids or []) if ref not in wanted
        ]
        detached.append(shot.id)

    file_paths = [image.file_path for image in (sheet.images or [])]
    db.delete(sheet)
    db.commit()

    for path in file_paths:
        _remove_quietly(path)
    return detached


def _remove_quietly(file_path: str) -> None:
    """Delete a stored file, tolerating one that is already gone."""
    if not file_path:
        return
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass
    except OSError as exc:  # pragma: no cover - platform-specific lock
        logger.warning("Could not remove reference image %s: %s", file_path, exc)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_images(
    db: Session, project_id: str, reference_ids: list[str]
) -> tuple[list[ReferenceImage], list[ReferenceProblem]]:
    """Turn requested reference ids into usable images, in the order asked.

    Anything that cannot be used is reported rather than skipped: a shot that
    names a reference is asking to be conditioned on it, so a missing row, a
    foreign project or a vanished file must reach preflight as a blocker
    instead of quietly producing an unconditioned render.
    """
    resolved: list[ReferenceImage] = []
    problems: list[ReferenceProblem] = []

    if not reference_ids:
        return resolved, problems

    found = {
        image.id: image
        for image in db.query(ReferenceImage)
        .filter(ReferenceImage.id.in_(reference_ids))
        .all()
    }

    for reference_id in reference_ids:
        image = found.get(reference_id)
        if image is None:
            problems.append(ReferenceProblem(
                reference_id, "not_found",
                f"Reference image {reference_id} no longer exists.",
            ))
            continue
        if image.project_id != project_id:
            problems.append(ReferenceProblem(
                reference_id, "wrong_project",
                f"Reference image {reference_id} belongs to another project "
                f"and cannot be used here.",
            ))
            continue
        if image.mime_type not in image_validation.ALLOWED_MIME_EXTENSIONS:
            problems.append(ReferenceProblem(
                reference_id, "unsupported_media_type",
                f"Reference image {reference_id} is stored as "
                f"'{image.mime_type}', which cannot be used for generation.",
            ))
            continue
        if not image.file_path or not os.path.isfile(image.file_path):
            problems.append(ReferenceProblem(
                reference_id, "file_missing",
                f"The file for reference image {reference_id} is missing from "
                f"disk. Re-upload it on its reference sheet.",
            ))
            continue
        resolved.append(image)

    return resolved, problems
