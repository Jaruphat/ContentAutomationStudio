"""
Revision and staleness over HTTP.

The selective-invalidation rules are unit-tested in ``test_revisions.py``; this
file proves they are actually reachable through the API - that every mutation
which can change a generation dependency refreshes revisions, and that the UI
can see which shots went stale.
"""

import pytest


@pytest.fixture()
def storyboard(client):
    """Two scenes, one character each, one shot each."""
    project = client.post("/api/projects", json={"title": "Revision Project"}).json()
    pid = project["id"]

    made = {"project": project, "characters": [], "scenes": [], "shots": []}
    for index in (0, 1):
        character = client.post(
            f"/api/projects/{pid}/characters",
            json={"name": f"Character {index}", "appearance": f"look {index}"},
        ).json()
        scene = client.post(
            f"/api/projects/{pid}/scenes",
            json={
                "order": index + 1,
                "title": f"Scene {index}",
                "summary": f"summary {index}",
                "character_ids": [character["id"]],
            },
        ).json()
        shot = client.post(
            f"/api/projects/{pid}/scenes/{scene['id']}/shots",
            json={
                "order": 1,
                "subject": f"subject {index}",
                "image_prompt": f"prompt {index}",
            },
        ).json()
        made["characters"].append(character)
        made["scenes"].append(scene)
        made["shots"].append(shot)
    return made


def _shot(client, project_id, shot):
    return client.get(
        f"/api/projects/{project_id}/scenes/{shot['scene_id']}/shots/{shot['id']}"
    ).json()


def test_shot_response_carries_its_revision(client, storyboard):
    pid = storyboard["project"]["id"]
    body = _shot(client, pid, storyboard["shots"][0])
    assert body["prompt_revision"] == 1
    assert body["is_stale"] is False
    assert len(body["content_sha256"]) == 64


def test_editing_a_shot_advances_only_its_own_revision(client, storyboard):
    pid = storyboard["project"]["id"]
    first, second = storyboard["shots"]

    updated = client.put(
        f"/api/projects/{pid}/scenes/{first['scene_id']}/shots/{first['id']}",
        json={"action": "a new action"},
    )
    assert updated.status_code == 200
    assert updated.json()["prompt_revision"] == 2
    assert _shot(client, pid, second)["prompt_revision"] == 1


def test_editing_a_character_advances_only_the_scenes_it_is_in(client, storyboard):
    pid = storyboard["project"]["id"]
    first, second = storyboard["shots"]

    client.put(
        f"/api/projects/{pid}/characters/{storyboard['characters'][1]['id']}",
        json={"clothing": "a new coat"},
    )
    assert _shot(client, pid, first)["prompt_revision"] == 1
    assert _shot(client, pid, second)["prompt_revision"] == 2


def test_editing_a_scene_advances_its_shots(client, storyboard):
    pid = storyboard["project"]["id"]
    first, second = storyboard["shots"]

    client.put(
        f"/api/projects/{pid}/scenes/{first['scene_id']}",
        json={"summary": "rewritten"},
    )
    assert _shot(client, pid, first)["prompt_revision"] == 2
    assert _shot(client, pid, second)["prompt_revision"] == 1


def test_editing_project_output_format_advances_every_shot(client, storyboard):
    pid = storyboard["project"]["id"]
    first, second = storyboard["shots"]

    response = client.put(
        f"/api/projects/{pid}",
        json={"aspect_ratio": "9:16", "target_resolution": "1080x1920"},
    )

    assert response.status_code == 200
    assert _shot(client, pid, first)["prompt_revision"] == 2
    assert _shot(client, pid, second)["prompt_revision"] == 2


def test_uploading_a_reference_advances_only_the_shots_using_it(
    client, storyboard, png_bytes
):
    pid = storyboard["project"]["id"]
    first, second = storyboard["shots"]

    sheet = client.post(
        f"/api/projects/{pid}/references",
        json={"kind": "character", "name": "Hero"},
    ).json()
    image = client.post(
        f"/api/projects/{pid}/references/{sheet['id']}/images",
        files={"file": ("hero.png", png_bytes(128, 128), "image/png")},
    ).json()

    client.put(
        f"/api/projects/{pid}/scenes/{first['scene_id']}/shots/{first['id']}",
        json={"reference_asset_ids": [image["id"]]},
    )
    baseline = _shot(client, pid, first)["prompt_revision"]
    assert baseline == 2
    assert _shot(client, pid, second)["prompt_revision"] == 1

    # Editing the sheet's identity reaches the shot that uses it, and only it.
    client.put(
        f"/api/projects/{pid}/references/{sheet['id']}",
        json={"canonical_description": "Now with a scar."},
    )
    assert _shot(client, pid, first)["prompt_revision"] == baseline + 1
    assert _shot(client, pid, second)["prompt_revision"] == 1


def test_deleting_a_character_advances_the_shots_that_referenced_it(
    client, storyboard
):
    pid = storyboard["project"]["id"]
    first, second = storyboard["shots"]

    client.delete(f"/api/projects/{pid}/characters/{storyboard['characters'][0]['id']}")
    assert _shot(client, pid, first)["prompt_revision"] == 2
    assert _shot(client, pid, second)["prompt_revision"] == 1


def test_preflight_reports_stale_shots(client, storyboard, db_session):
    """Preflight is a read, but it refreshes first so it never reports stale data."""
    from app.models import Shot
    from app.services import revisions

    pid = storyboard["project"]["id"]
    first = storyboard["shots"][0]

    shot = db_session.query(Shot).filter(Shot.id == first["id"]).first()
    revisions.mark_generated(db_session, shot)
    db_session.commit()

    client.put(
        f"/api/projects/{pid}/scenes/{first['scene_id']}/shots/{first['id']}",
        json={"action": "changed after generating"},
    )

    body = _shot(client, pid, first)
    assert body["is_stale"] is True

    preflight = client.get(f"/api/projects/{pid}/preflight").json()
    stale = [issue for issue in preflight["issues"] if issue["shot_id"] == first["id"]]
    assert stale
    assert any("stale" in reason.lower() for reason in stale[0]["issues"])
