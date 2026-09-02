"""Append-only, tamper-evident AI authoring revision records."""

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AIAuthoringRevision, Project


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _material(revision: AIAuthoringRevision) -> dict[str, Any]:
    """All decision-bearing fields covered by a revision's digest."""
    return {
        "id": revision.id,
        "project_id": revision.project_id,
        "kind": revision.kind,
        "task": revision.task,
        "payload": revision.payload,
        "payload_sha256": revision.payload_sha256,
        "provider_id": revision.provider_id or "",
        "model": revision.model or "",
        "prompt_version": revision.prompt_version or "",
        "schema_version": revision.schema_version or "",
        "usage": revision.usage or {},
        "provenance": revision.provenance or {},
        "brief_snapshot": revision.brief_snapshot or {},
        "source_revision_id": revision.source_revision_id,
        "source_revision_sha256": revision.source_revision_sha256 or "",
    }


def revision_hash(revision: AIAuthoringRevision) -> str:
    return _canonical_sha256(_material(revision))


def is_hash_valid(revision: AIAuthoringRevision) -> bool:
    return (
        revision.payload_sha256 == _canonical_sha256(revision.payload)
        and revision.revision_sha256 == revision_hash(revision)
    )


def _brief(project: Project) -> dict[str, str]:
    return {
        "brief_text": project.brief_text or "",
        "plot_text": project.plot_text or "",
    }


def _new_revision(
    *,
    project: Project,
    kind: str,
    task: str,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    source: AIAuthoringRevision | None = None,
) -> AIAuthoringRevision:
    # Applied rows retain the provider/model/version of the preview they cite,
    # while provenance.source records that no second provider call occurred.
    metadata = source if source is not None else None
    revision = AIAuthoringRevision(
        id=str(uuid.uuid4()),
        project_id=project.id,
        kind=kind,
        task=task,
        payload=payload,
        payload_sha256=_canonical_sha256(payload),
        revision_sha256="",
        provider_id=(metadata.provider_id if metadata else provenance.get("provider_id", "")),
        model=(metadata.model if metadata else provenance.get("model", "")),
        prompt_version=(
            metadata.prompt_version if metadata else provenance.get("prompt_version", "")
        ),
        schema_version=(
            metadata.schema_version if metadata else provenance.get("schema_version", "")
        ),
        usage=(metadata.usage if metadata else provenance.get("usage", {})) or {},
        provenance=dict(provenance),
        brief_snapshot=_brief(project),
        source_revision_id=source.id if source else None,
        source_revision_sha256=source.revision_sha256 if source else "",
    )
    revision.revision_sha256 = revision_hash(revision)
    return revision


def create_preview(
    db: Session,
    project: Project,
    task: str,
    payload: dict[str, Any],
    provenance: dict[str, Any],
) -> AIAuthoringRevision:
    revision = _new_revision(
        project=project, kind="preview", task=task,
        payload=payload, provenance=provenance,
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def require_reviewed_preview(
    db: Session,
    *,
    project_id: str,
    task: str,
    revision_id: str,
    expected_sha256: str,
) -> AIAuthoringRevision:
    revision = db.get(AIAuthoringRevision, revision_id)
    if (
        revision is None
        or revision.project_id != project_id
        or revision.task != task
        or revision.kind != "preview"
    ):
        raise ValueError("The reviewed preview does not belong to this project and task.")
    if expected_sha256 and revision.revision_sha256 != expected_sha256:
        raise ValueError("The reviewed preview hash does not match the stored revision.")
    if not is_hash_valid(revision):
        raise ValueError("The stored reviewed preview failed tamper verification.")
    return revision


def create_applied(
    db: Session,
    project: Project,
    task: str,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    source: AIAuthoringRevision,
) -> AIAuthoringRevision:
    revision = _new_revision(
        project=project, kind="applied", task=task,
        payload=payload, provenance=provenance, source=source,
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def revision_to_dict(revision: AIAuthoringRevision) -> dict[str, Any]:
    return {
        "id": revision.id,
        "kind": revision.kind,
        "task": revision.task,
        "payload": revision.payload,
        "payload_sha256": revision.payload_sha256,
        "revision_sha256": revision.revision_sha256,
        "hash_valid": is_hash_valid(revision),
        "provider_id": revision.provider_id or "",
        "model": revision.model or "",
        "prompt_version": revision.prompt_version or "",
        "schema_version": revision.schema_version or "",
        "usage": revision.usage or {},
        "provenance": revision.provenance or {},
        "brief_snapshot": revision.brief_snapshot or {},
        "source_revision_id": revision.source_revision_id,
        "source_revision_sha256": revision.source_revision_sha256 or "",
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }


def project_audit(db: Session, project: Project) -> dict[str, Any]:
    revisions = (
        db.query(AIAuthoringRevision)
        .filter(AIAuthoringRevision.project_id == project.id)
        .order_by(AIAuthoringRevision.created_at, AIAuthoringRevision.id)
        .all()
    )
    return {
        "project_id": project.id,
        "project_title": project.title,
        "current_brief": _brief(project),
        "revisions": [revision_to_dict(item) for item in revisions],
    }
