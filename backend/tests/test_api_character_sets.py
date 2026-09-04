"""
HTTP surface of the Character Set Generator.

The whole point of a character set is that a person can define an identity
once, generate a sheet of canonical views from it, look at them, and approve
one version as the truth. None of that is reachable unless the API exposes
creation, generation, the version list, the view gallery and approval - so
that is what is asserted here, over HTTP, with the ownership and paid-generation
gates the rest of the application already enforces.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Character, Project, Scene, Shot
from app.services import character_sets


@pytest.fixture()
def project_id(client: TestClient) -> str:
    response = client.post("/api/projects", json={"title": "Character Sets"})
    assert response.status_code == 201
    return response.json()["id"]


def _create_set(client: TestClient, project_id: str, **overrides) -> dict:
    payload = {
        "name": "Mara",
        "appearance": "Close-cropped silver hair, weathered face.",
        "wardrobe": "Grey field coat.",
        "palette": "Cold blues and slate.",
        **overrides,
    }
    response = client.post(
        f"/api/projects/{project_id}/character-sets", json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def _generate_version(client: TestClient, project_id: str, set_id: str, **body):
    return client.post(
        f"/api/projects/{project_id}/character-sets/{set_id}/versions",
        json={"slots": ["front", "side"], **body},
    )


# ---------------------------------------------------------------------------
# Sets
# ---------------------------------------------------------------------------

def test_a_character_set_is_created_with_a_sheet_to_hold_its_views(
    client: TestClient, project_id: str
):
    body = _create_set(client, project_id)
    assert body["name"] == "Mara"
    assert body["project_id"] == project_id
    # Views are stored through the Reference Bible, so the set owns a sheet.
    assert body["reference_sheet_id"]
    assert body["approved_version_id"] is None
    assert body["approved_version_is_current"] is False
    assert body["versions"] == []


def test_a_set_without_a_name_is_refused_rather_than_left_unrecognisable(
    client: TestClient, project_id: str
):
    response = client.post(
        f"/api/projects/{project_id}/character-sets", json={"name": "   "}
    )
    assert response.status_code == 422


def test_sets_are_listed_only_under_the_project_that_owns_them(
    client: TestClient, project_id: str
):
    _create_set(client, project_id)
    other = client.post("/api/projects", json={"title": "Other"}).json()["id"]
    _create_set(client, other, name="Intruder")

    names = [
        entry["name"]
        for entry in client.get(
            f"/api/projects/{project_id}/character-sets"
        ).json()
    ]
    assert names == ["Mara"]


def test_a_set_id_from_another_project_does_not_resolve(
    client: TestClient, project_id: str
):
    other = client.post("/api/projects", json={"title": "Other"}).json()["id"]
    foreign = _create_set(client, other, name="Intruder")
    response = client.get(
        f"/api/projects/{project_id}/character-sets/{foreign['id']}"
    )
    assert response.status_code == 404


def test_editing_the_spec_is_reported_as_the_approved_version_falling_behind(
    client: TestClient, project_id: str
):
    """Approval publishes an identity; editing the text only proposes one."""
    body = _create_set(client, project_id)
    set_id = body["id"]
    version = _generate_version(client, project_id, set_id).json()
    client.post(
        f"/api/projects/{project_id}/character-sets/{set_id}"
        f"/versions/{version['id']}/generate",
        json={},
    )
    client.post(
        f"/api/projects/{project_id}/character-sets/{set_id}"
        f"/versions/{version['id']}/approve"
    )
    assert client.get(
        f"/api/projects/{project_id}/character-sets/{set_id}"
    ).json()["approved_version_is_current"] is True

    client.put(
        f"/api/projects/{project_id}/character-sets/{set_id}",
        json={"wardrobe": "Now a rain-soaked overcoat."},
    )
    refreshed = client.get(
        f"/api/projects/{project_id}/character-sets/{set_id}"
    ).json()
    assert refreshed["approved_version_is_current"] is False
    # The approved version is still the one downstream generation reads.
    assert refreshed["approved_version_id"] == version["id"]


# ---------------------------------------------------------------------------
# Versions, generation and the gallery
# ---------------------------------------------------------------------------

def test_a_version_opens_with_one_pending_view_per_requested_slot(
    client: TestClient, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    body = _generate_version(client, project_id, set_id).json()

    assert body["version"] == 1
    assert body["status"] == "Draft"
    assert [view["slot"] for view in body["views"]] == ["front", "side"]
    assert all(view["status"] == "Pending" for view in body["views"])
    assert all(view["url"] is None for view in body["views"])
    # Each view carries the prompt it will be generated from, so the gallery
    # can show what was asked for before anything is spent.
    assert "front-facing" in body["views"][0]["view_prompt"]
    assert "silver hair" in body["views"][0]["view_prompt"]


def test_an_unknown_view_slot_is_refused_with_the_list_of_real_ones(
    client: TestClient, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    response = _generate_version(client, project_id, set_id, slots=["backwards"])
    assert response.status_code == 422
    assert "front" in response.json()["detail"]


def test_generating_a_version_fills_the_gallery_with_real_images(
    client: TestClient, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    version = _generate_version(client, project_id, set_id).json()

    response = client.post(
        f"/api/projects/{project_id}/character-sets/{set_id}"
        f"/versions/{version['id']}/generate",
        json={},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "NeedsReview"
    assert all(view["status"] == "Ready" for view in body["views"])
    for view in body["views"]:
        assert view["url"], "the gallery needs a URL it can actually load"
        assert view["sha256"]
        assert view["provider_id"]
        assert client.get(view["url"]).status_code == 200
    # One seed across the sheet: the views are meant to be the same person.
    assert len({view["seed"] for view in body["views"]}) == 1


def test_a_half_generated_version_cannot_be_approved_as_canonical(
    client: TestClient, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    version = _generate_version(client, project_id, set_id).json()

    response = client.post(
        f"/api/projects/{project_id}/character-sets/{set_id}"
        f"/versions/{version['id']}/approve"
    )
    assert response.status_code == 409
    assert "front" in response.json()["detail"]


def test_approving_a_second_version_supersedes_the_first_without_deleting_it(
    client: TestClient, project_id: str
):
    """History is what lets an old approved take still be explained."""
    set_id = _create_set(client, project_id)["id"]
    base = f"/api/projects/{project_id}/character-sets/{set_id}"

    first = _generate_version(client, project_id, set_id).json()
    client.post(f"{base}/versions/{first['id']}/generate", json={})
    client.post(f"{base}/versions/{first['id']}/approve")

    second = _generate_version(client, project_id, set_id).json()
    client.post(f"{base}/versions/{second['id']}/generate", json={})
    approved = client.post(f"{base}/versions/{second['id']}/approve")
    assert approved.status_code == 200

    versions = client.get(f"{base}").json()["versions"]
    by_id = {entry["id"]: entry for entry in versions}
    assert by_id[first["id"]]["status"] == "Superseded"
    assert by_id[second["id"]]["status"] == "Approved"
    assert client.get(base).json()["approved_version_id"] == second["id"]
    # The superseded version keeps its images.
    old = client.get(f"{base}/versions/{first['id']}").json()
    assert all(view["url"] for view in old["views"])


def test_canonical_status_can_be_withdrawn(client: TestClient, project_id: str):
    set_id = _create_set(client, project_id)["id"]
    base = f"/api/projects/{project_id}/character-sets/{set_id}"
    version = _generate_version(client, project_id, set_id).json()
    client.post(f"{base}/versions/{version['id']}/generate", json={})
    client.post(f"{base}/versions/{version['id']}/approve")

    response = client.post(f"{base}/versions/{version['id']}/unapprove")
    assert response.status_code == 200
    assert client.get(base).json()["approved_version_id"] is None


# ---------------------------------------------------------------------------
# Paid generation
# ---------------------------------------------------------------------------

def test_generating_a_sheet_through_a_metered_provider_needs_confirmation(
    client: TestClient, project_id: str, monkeypatch
):
    """A character sheet is four images; it costs the same as four shots do."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-one")
    from app.services import media_providers

    media_providers.reset_provider_cache()

    set_id = _create_set(client, project_id)["id"]
    version = _generate_version(client, project_id, set_id).json()
    base = f"/api/projects/{project_id}/character-sets/{set_id}"

    response = client.post(
        f"{base}/versions/{version['id']}/generate",
        json={"provider_id": "openai"},
    )
    assert response.status_code == 409
    assert "confirm_paid_generation" in response.json()["detail"]


def test_an_unconfigured_metered_provider_is_refused_before_anything_runs(
    client: TestClient, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    version = _generate_version(client, project_id, set_id).json()
    response = client.post(
        f"/api/projects/{project_id}/character-sets/{set_id}"
        f"/versions/{version['id']}/generate",
        json={"provider_id": "openai", "confirm_paid_generation": True},
    )
    assert response.status_code == 409
    assert "OPENAI_API_KEY" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Deletion and binding
# ---------------------------------------------------------------------------

def test_a_set_a_shot_still_binds_cannot_be_deleted_by_accident(
    client: TestClient, db_session: Session, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    scene = client.post(
        f"/api/projects/{project_id}/scenes", json={"title": "One"}
    ).json()
    shot = client.post(
        f"/api/projects/{project_id}/scenes/{scene['id']}/shots",
        json={"image_prompt": "a face", "character_set_ids": [set_id]},
    ).json()

    response = client.delete(
        f"/api/projects/{project_id}/character-sets/{set_id}"
    )
    assert response.status_code == 409
    assert shot["id"] in response.json()["detail"]

    forced = client.delete(
        f"/api/projects/{project_id}/character-sets/{set_id}?force=true"
    )
    assert forced.status_code == 204
    detached = client.get(
        f"/api/projects/{project_id}/scenes/{scene['id']}/shots/{shot['id']}"
    ).json()
    assert detached["character_set_ids"] == []


def test_a_shot_cannot_bind_a_character_set_from_another_project(
    client: TestClient, project_id: str
):
    other = client.post("/api/projects", json={"title": "Other"}).json()["id"]
    foreign = _create_set(client, other, name="Intruder")
    scene = client.post(
        f"/api/projects/{project_id}/scenes", json={"title": "One"}
    ).json()

    response = client.post(
        f"/api/projects/{project_id}/scenes/{scene['id']}/shots",
        json={"image_prompt": "a face", "character_set_ids": [foreign["id"]]},
    )
    assert response.status_code == 400
    assert "another project" in response.json()["detail"]


def test_binding_a_set_is_visible_on_the_shot_it_was_bound_to(
    client: TestClient, project_id: str
):
    set_id = _create_set(client, project_id)["id"]
    scene = client.post(
        f"/api/projects/{project_id}/scenes", json={"title": "One"}
    ).json()
    shot = client.post(
        f"/api/projects/{project_id}/scenes/{scene['id']}/shots",
        json={"image_prompt": "a face"},
    ).json()

    updated = client.put(
        f"/api/projects/{project_id}/scenes/{scene['id']}/shots/{shot['id']}",
        json={"character_set_ids": [set_id]},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["character_set_ids"] == [set_id]
    # Binding is a content change, so the shot's revision moved with it.
    assert body["prompt_revision"] == shot["prompt_revision"] + 1


# ---------------------------------------------------------------------------
# Migration safety
# ---------------------------------------------------------------------------

def test_a_shot_created_before_character_sets_still_serialises(
    client: TestClient, db_session: Session, sample_project: Project,
    sample_scene: Scene,
):
    """Columns an ALTER TABLE could only add as NULL must not break a read."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=9,
        image_prompt="legacy",
    )
    shot.character_set_ids = None
    shot.character_set_sha256s = None
    shot.continuity_source_mode = None
    shot.continuity_source_sha256 = None
    db_session.add(shot)
    db_session.commit()

    response = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}"
        f"/shots/{shot.id}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["character_set_ids"] == []
    assert body["continuity_source_mode"] == "none"


def test_the_service_and_the_api_agree_on_what_is_approved(
    client: TestClient, db_session: Session, sample_project: Project,
    sample_character: Character,
):
    """The API is a view over the service, not a second implementation."""
    character_set = character_sets.create_set(
        db_session, project_id=sample_project.id, name="Mara",
        character_id=sample_character.id,
    )
    body = client.get(
        f"/api/projects/{sample_project.id}/character-sets/{character_set.id}"
    ).json()
    assert body["character_id"] == sample_character.id
    assert body["approved_version_id"] is None
