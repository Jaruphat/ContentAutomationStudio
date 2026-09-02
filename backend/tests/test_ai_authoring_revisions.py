"""Durable, tamper-evident audit trail for AI authoring decisions."""

import copy
import hashlib
import json
import uuid

from sqlalchemy.orm import Session

from app.models import AIAuthoringRevision, Project


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_preview_persists_exact_response_and_provider_neutral_provenance(
    client, db_session: Session, sample_project: Project,
):
    response = client.post(
        f"/api/projects/{sample_project.id}/ai/storyboard",
        json={"scene_count": 2, "min_shots": 4, "max_shots": 8},
    )
    assert response.status_code == 200
    body = response.json()

    revision = db_session.get(AIAuthoringRevision, body["preview_revision_id"])
    assert revision is not None
    assert revision.project_id == sample_project.id
    assert revision.kind == "preview"
    assert revision.task == body["task"]
    assert revision.payload == body["data"]
    assert revision.provider_id == body["provenance"]["provider_id"]
    assert revision.model == body["provenance"]["model"]
    assert revision.prompt_version == body["provenance"]["prompt_version"]
    assert revision.schema_version == body["provenance"]["schema_version"]
    assert revision.usage == body["provenance"]["usage"]
    assert revision.brief_snapshot == {
        "brief_text": sample_project.brief_text,
        "plot_text": sample_project.plot_text,
    }
    assert revision.payload_sha256 == canonical_sha256(body["data"])
    assert len(revision.revision_sha256) == 64
    assert body["preview_sha256"] == revision.revision_sha256


def test_apply_creates_immutable_revision_linked_to_reviewed_preview(
    client, db_session: Session, sample_project: Project,
):
    preview = client.post(
        f"/api/projects/{sample_project.id}/ai/storyboard",
        json={"scene_count": 2, "min_shots": 4, "max_shots": 8},
    ).json()
    reviewed = copy.deepcopy(preview["data"])
    reviewed["notes"] = "Reviewed by the editor."

    response = client.post(
        f"/api/projects/{sample_project.id}/ai/storyboard",
        json={
            "scene_count": 2,
            "min_shots": 4,
            "max_shots": 8,
            "apply": True,
            "draft": reviewed,
            "reviewed_preview_id": preview["preview_revision_id"],
            "reviewed_preview_sha256": preview["preview_sha256"],
        },
    )
    assert response.status_code == 200
    body = response.json()

    applied = db_session.get(AIAuthoringRevision, body["applied_revision_id"])
    assert applied is not None
    assert applied.kind == "applied"
    assert applied.source_revision_id == preview["preview_revision_id"]
    assert applied.source_revision_sha256 == preview["preview_sha256"]
    assert applied.payload == reviewed
    assert applied.payload_sha256 == canonical_sha256(reviewed)
    assert body["applied_sha256"] == applied.revision_sha256


def test_apply_rejects_a_tampered_preview_reference(
    client, db_session: Session, sample_project: Project,
):
    preview = client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible", json={},
    ).json()

    response = client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible",
        json={
            "apply": True,
            "draft": preview["data"],
            "reviewed_preview_id": preview["preview_revision_id"],
            "reviewed_preview_sha256": "0" * 64,
        },
    )

    assert response.status_code == 409
    assert response.json()["category"] == "conflict"
    assert db_session.query(AIAuthoringRevision).filter_by(kind="applied").count() == 0


def test_project_scoped_audit_endpoint_links_brief_preview_and_apply(
    client, sample_project: Project, db_session: Session,
):
    preview = client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible", json={},
    ).json()
    applied = client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible",
        json={
            "apply": True,
            "draft": preview["data"],
            "reviewed_preview_id": preview["preview_revision_id"],
            "reviewed_preview_sha256": preview["preview_sha256"],
        },
    ).json()

    other = Project(id=str(uuid.uuid4()), title="Other", brief_text="secret")
    db_session.add(other)
    db_session.add(AIAuthoringRevision(
        id=str(uuid.uuid4()), project_id=other.id, kind="preview", task="story_bible",
        payload={}, payload_sha256=canonical_sha256({}), revision_sha256="f" * 64,
    ))
    db_session.commit()

    response = client.get(f"/api/projects/{sample_project.id}/ai/revisions")
    assert response.status_code == 200
    audit = response.json()
    assert audit["project_id"] == sample_project.id
    assert [item["id"] for item in audit["revisions"]] == [
        preview["preview_revision_id"], applied["applied_revision_id"],
    ]
    assert all(item["hash_valid"] is True for item in audit["revisions"])
    assert audit["revisions"][1]["source_revision_id"] == audit["revisions"][0]["id"]
    assert "secret" not in response.text


def test_authoring_audit_export_and_project_archive_include_revisions(
    client, sample_project: Project,
):
    preview = client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible", json={},
    ).json()
    client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible",
        json={
            "apply": True,
            "draft": preview["data"],
            "reviewed_preview_id": preview["preview_revision_id"],
            "reviewed_preview_sha256": preview["preview_sha256"],
        },
    )

    exported = client.get(
        f"/api/projects/{sample_project.id}/export/authoring-audit"
    )
    assert exported.status_code == 200
    assert len(exported.json()["revisions"]) == 2

    archive = client.get(
        f"/api/projects/{sample_project.id}/export/project-archive"
    ).json()
    assert archive["ai_authoring_audit"] == exported.json()


def test_credentials_are_never_persisted_or_exported(
    client, db_session: Session, sample_project: Project, monkeypatch,
):
    secret = "sk-do-not-store-this"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    response = client.post(
        f"/api/projects/{sample_project.id}/ai/story-bible",
        json={"provider_id": "mock"},
    )
    assert response.status_code == 200
    revision = db_session.get(
        AIAuthoringRevision, response.json()["preview_revision_id"],
    )

    assert secret not in json.dumps(revision.payload)
    assert secret not in json.dumps(revision.provenance)
    assert secret not in client.get(
        f"/api/projects/{sample_project.id}/ai/revisions"
    ).text
