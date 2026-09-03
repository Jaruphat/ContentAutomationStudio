"""
HTTP surface of the Visual Reference Bible.

Covers the upload boundary (what is accepted, what is refused and with which
status), project isolation, the file endpoint's path containment, and assigning
references to shots.
"""

import os

import pytest

from app.models import Project, ReferenceImage, Scene, Shot


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_project(client):
    return client.post("/api/projects", json={"title": "Reference Project"}).json()


@pytest.fixture()
def api_sheet(client, api_project):
    return client.post(
        f"/api/projects/{api_project['id']}/references",
        json={
            "kind": "character",
            "name": "Alice",
            "canonical_description": "Tall, brown hair, red dress.",
            "identity_tokens": "1girl, brown hair, red dress",
        },
    ).json()


def _upload(client, project_id, sheet_id, data, filename="alice.png",
            content_type="image/png", role="canonical"):
    return client.post(
        f"/api/projects/{project_id}/references/{sheet_id}/images",
        files={"file": (filename, data, content_type)},
        data={"role": role},
    )


# ---------------------------------------------------------------------------
# Sheet CRUD
# ---------------------------------------------------------------------------

def test_create_and_list_sheets(client, api_project, api_sheet):
    assert api_sheet["kind"] == "character"
    assert api_sheet["name"] == "Alice"
    assert api_sheet["revision"] == 1
    assert api_sheet["images"] == []

    listed = client.get(f"/api/projects/{api_project['id']}/references")
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()] == [api_sheet["id"]]


def test_create_sheet_rejects_an_unknown_kind(client, api_project):
    resp = client.post(
        f"/api/projects/{api_project['id']}/references",
        json={"kind": "spaceship", "name": "Nostromo"},
    )
    assert resp.status_code == 422


def test_sheets_are_not_visible_from_another_project(client, api_project, api_sheet):
    other = client.post("/api/projects", json={"title": "Other"}).json()
    assert client.get(f"/api/projects/{other['id']}/references").json() == []
    assert client.get(
        f"/api/projects/{other['id']}/references/{api_sheet['id']}"
    ).status_code == 404


def test_update_sheet_advances_the_revision(client, api_project, api_sheet):
    resp = client.put(
        f"/api/projects/{api_project['id']}/references/{api_sheet['id']}",
        json={"canonical_description": "Tall, brown hair, blue dress."},
    )
    assert resp.status_code == 200
    assert resp.json()["revision"] == 2


def test_delete_sheet(client, api_project, api_sheet):
    resp = client.delete(
        f"/api/projects/{api_project['id']}/references/{api_sheet['id']}"
    )
    assert resp.status_code == 204
    assert client.get(f"/api/projects/{api_project['id']}/references").json() == []


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def test_upload_returns_the_stored_image(client, api_project, api_sheet, png_bytes):
    data = png_bytes(256, 256)
    resp = _upload(client, api_project["id"], api_sheet["id"], data)
    assert resp.status_code == 201
    body = resp.json()
    assert body["mime_type"] == "image/png"
    assert body["width"] == 256
    assert body["size_bytes"] == len(data)
    assert len(body["sha256"]) == 64
    assert body["stored_filename"] == f"{body['id']}.png"
    # The absolute path is deliberately not exposed to the browser.
    assert "file_path" not in body
    assert body["url"] == f"/api/media/references/{body['id']}/file"


def test_upload_appears_on_the_sheet(client, api_project, api_sheet, png_bytes):
    _upload(client, api_project["id"], api_sheet["id"], png_bytes(128, 128))
    sheet = client.get(
        f"/api/projects/{api_project['id']}/references/{api_sheet['id']}"
    ).json()
    assert len(sheet["images"]) == 1
    assert sheet["revision"] == 2


def test_upload_refuses_a_disguised_file(client, api_project, api_sheet):
    resp = _upload(
        client, api_project["id"], api_sheet["id"],
        b"%PDF-1.7 definitely not a png", filename="alice.png",
    )
    assert resp.status_code == 415
    assert "PNG, JPEG or WEBP" in resp.json()["detail"]


def test_upload_refuses_a_tiny_image(client, api_project, api_sheet, png_bytes):
    resp = _upload(client, api_project["id"], api_sheet["id"], png_bytes(16, 16))
    assert resp.status_code == 422


def test_upload_refuses_an_oversized_file(
    client, api_project, api_sheet, png_bytes, monkeypatch
):
    from app.services import image_validation

    monkeypatch.setattr(image_validation, "MAX_IMAGE_BYTES", 256)
    resp = _upload(client, api_project["id"], api_sheet["id"], png_bytes(400, 400))
    assert resp.status_code == 413


def test_upload_with_a_traversal_filename_stays_inside_the_project_dir(
    client, api_project, api_sheet, png_bytes, db_session
):
    resp = _upload(
        client, api_project["id"], api_sheet["id"], png_bytes(128, 128),
        filename="../../../../windows/system32/evil.png",
    )
    assert resp.status_code == 201
    image = db_session.query(ReferenceImage).filter(
        ReferenceImage.id == resp.json()["id"]
    ).first()

    from app import paths

    expected = os.path.realpath(paths.references_dir(api_project["id"]))
    assert os.path.realpath(os.path.dirname(image.file_path)) == expected
    assert ".." not in image.stored_filename


def test_upload_to_another_projects_sheet_is_refused(
    client, api_project, api_sheet, png_bytes
):
    other = client.post("/api/projects", json={"title": "Other"}).json()
    resp = _upload(client, other["id"], api_sheet["id"], png_bytes(128, 128))
    assert resp.status_code == 404


def test_uploading_identical_bytes_twice_yields_one_image(
    client, api_project, api_sheet, png_bytes
):
    data = png_bytes(200, 200)
    first = _upload(client, api_project["id"], api_sheet["id"], data).json()
    second = _upload(client, api_project["id"], api_sheet["id"], data).json()
    assert first["id"] == second["id"]
    sheet = client.get(
        f"/api/projects/{api_project['id']}/references/{api_sheet['id']}"
    ).json()
    assert len(sheet["images"]) == 1


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------

def test_reference_file_is_served_with_its_real_type(
    client, api_project, api_sheet, png_bytes
):
    data = png_bytes(128, 128)
    image = _upload(client, api_project["id"], api_sheet["id"], data).json()
    resp = client.get(f"/api/media/references/{image['id']}/file")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == data


def test_reference_file_outside_the_data_dir_is_refused(
    client, api_project, api_sheet, png_bytes, db_session, tmp_path
):
    image_id = _upload(
        client, api_project["id"], api_sheet["id"], png_bytes(128, 128)
    ).json()["id"]

    # Simulate a hand-edited database pointing at somewhere else entirely.
    outside = tmp_path / "secret.png"
    outside.write_bytes(png_bytes(128, 128))
    row = db_session.query(ReferenceImage).filter(
        ReferenceImage.id == image_id
    ).first()
    row.file_path = str(outside)
    db_session.commit()

    resp = client.get(f"/api/media/references/{image_id}/file")
    assert resp.status_code == 403


def test_missing_reference_file_reports_404(
    client, api_project, api_sheet, png_bytes, db_session
):
    image_id = _upload(
        client, api_project["id"], api_sheet["id"], png_bytes(128, 128)
    ).json()["id"]
    row = db_session.query(ReferenceImage).filter(
        ReferenceImage.id == image_id
    ).first()
    os.remove(row.file_path)
    assert client.get(f"/api/media/references/{image_id}/file").status_code == 404


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def _make_shot(client, project_id) -> dict:
    scene = client.post(
        f"/api/projects/{project_id}/scenes", json={"title": "S1", "order": 1},
    ).json()
    return client.post(
        f"/api/projects/{project_id}/scenes/{scene['id']}/shots",
        json={"order": 1, "image_prompt": "a portrait"},
    ).json()


def test_deleting_a_referenced_image_is_refused_then_forced(
    client, api_project, api_sheet, png_bytes
):
    image = _upload(client, api_project["id"], api_sheet["id"], png_bytes(128, 128)).json()
    shot = _make_shot(client, api_project["id"])
    scene_id = shot["scene_id"]
    assigned = client.put(
        f"/api/projects/{api_project['id']}/scenes/{scene_id}/shots/{shot['id']}",
        json={"reference_asset_ids": [image["id"]]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["reference_asset_ids"] == [image["id"]]

    url = (
        f"/api/projects/{api_project['id']}/references/"
        f"{api_sheet['id']}/images/{image['id']}"
    )
    refused = client.delete(url)
    assert refused.status_code == 409
    assert shot["id"] in refused.json()["detail"]

    forced = client.delete(url + "?force=true")
    assert forced.status_code == 204
    after = client.get(
        f"/api/projects/{api_project['id']}/scenes/{scene_id}/shots/{shot['id']}"
    ).json()
    assert after["reference_asset_ids"] == []


# ---------------------------------------------------------------------------
# Assignment to shots
# ---------------------------------------------------------------------------

def test_assigning_a_reference_from_another_project_is_refused(
    client, api_project, api_sheet, png_bytes
):
    other = client.post("/api/projects", json={"title": "Other"}).json()
    other_sheet = client.post(
        f"/api/projects/{other['id']}/references",
        json={"kind": "character", "name": "Stranger"},
    ).json()
    foreign = _upload(
        client, other["id"], other_sheet["id"], png_bytes(128, 128)
    ).json()

    shot = _make_shot(client, api_project["id"])
    resp = client.put(
        f"/api/projects/{api_project['id']}/scenes/{shot['scene_id']}"
        f"/shots/{shot['id']}",
        json={"reference_asset_ids": [foreign["id"]]},
    )
    assert resp.status_code == 400
    assert "another project" in resp.json()["detail"]


def test_assigning_an_unknown_reference_is_refused(client, api_project):
    shot = _make_shot(client, api_project["id"])
    resp = client.put(
        f"/api/projects/{api_project['id']}/scenes/{shot['scene_id']}"
        f"/shots/{shot['id']}",
        json={"reference_asset_ids": ["no-such-reference"]},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Persistence across a restart
# ---------------------------------------------------------------------------

def test_reference_survives_a_backend_restart(db_engine, png_bytes):
    """A second TestClient over the same database sees the same sheet."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.database import get_db
    from app.main import app

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as first:
            project = first.post(
                "/api/projects", json={"title": "Persisted"}
            ).json()
            sheet = first.post(
                f"/api/projects/{project['id']}/references",
                json={"kind": "prop", "name": "Lantern"},
            ).json()
            image = _upload(
                first, project["id"], sheet["id"], png_bytes(128, 128)
            ).json()

        with TestClient(app, raise_server_exceptions=False) as second:
            sheets = second.get(
                f"/api/projects/{project['id']}/references"
            ).json()
            assert [s["id"] for s in sheets] == [sheet["id"]]
            assert [i["id"] for i in sheets[0]["images"]] == [image["id"]]
            served = second.get(f"/api/media/references/{image['id']}/file")
            assert served.status_code == 200
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------

def test_deleting_a_project_removes_its_reference_rows(
    client, api_project, api_sheet, png_bytes, db_session
):
    _upload(client, api_project["id"], api_sheet["id"], png_bytes(128, 128))
    assert client.delete(f"/api/projects/{api_project['id']}").status_code == 204
    assert db_session.query(Project).filter(
        Project.id == api_project["id"]
    ).count() == 0
    assert db_session.query(ReferenceImage).filter(
        ReferenceImage.project_id == api_project["id"]
    ).count() == 0


def test_scene_and_shot_fixtures_stay_untouched(client, api_project):
    """A reference upload must not disturb unrelated storyboard rows."""
    shot = _make_shot(client, api_project["id"])
    assert client.get(
        f"/api/projects/{api_project['id']}/scenes/{shot['scene_id']}"
        f"/shots/{shot['id']}"
    ).json()["reference_asset_ids"] == []


def test_orm_relationship_exposes_project_sheets(db_session, sample_project):
    from app.services import reference_bible

    reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="location", name="Clearing",
    )
    db_session.refresh(sample_project)
    assert [s.name for s in sample_project.reference_sheets] == ["Clearing"]


def test_shot_scene_project_chain_is_used_for_dependents(
    db_session, sample_project, sample_scene, sample_shot, png_bytes
):
    """shots_using walks shot -> scene -> project, not a raw JSON query."""
    from app.services import reference_bible

    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="l.png", content_type="image/png",
    )
    sample_shot.reference_asset_ids = [image.id]
    db_session.commit()

    assert [s.id for s in reference_bible.shots_using(db_session, [image.id])] == [
        sample_shot.id
    ]
    assert db_session.query(Scene).count() >= 1
    assert db_session.query(Shot).count() >= 1
