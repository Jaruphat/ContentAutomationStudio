"""
Tests for Scene and Shot API endpoints.

Validates CRUD operations and reorder for scenes under projects
and shots under scenes.
"""

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper to create a project
# ---------------------------------------------------------------------------

def _create_project(client: TestClient) -> str:
    resp = client.post("/api/projects", json={"title": "Scene Test Project"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_scene(client: TestClient, project_id: str, **kwargs) -> dict:
    payload = {"title": "Test Scene", **kwargs}
    resp = client.post(f"/api/projects/{project_id}/scenes", json=payload)
    assert resp.status_code == 201
    return resp.json()


def _create_shot(
    client: TestClient, project_id: str, scene_id: str, **kwargs
) -> dict:
    payload = {"shot_type": "wide shot", **kwargs}
    resp = client.post(
        f"/api/projects/{project_id}/scenes/{scene_id}/shots", json=payload
    )
    assert resp.status_code == 201
    return resp.json()


# ===========================================================================
# Scene CRUD
# ===========================================================================

class TestCreateScene:
    """POST /api/projects/{project_id}/scenes"""

    def test_create_scene(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id, title="Opening")
        assert scene["title"] == "Opening"
        assert scene["project_id"] == project_id
        assert scene["status"] == "Draft"

    def test_create_scene_auto_order(self, client: TestClient):
        project_id = _create_project(client)
        s1 = _create_scene(client, project_id, title="Scene 1")
        s2 = _create_scene(client, project_id, title="Scene 2")
        assert s1["order"] == 1
        assert s2["order"] == 2

    def test_create_scene_with_character_ids(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(
            client, project_id, character_ids=["char-1", "char-2"]
        )
        assert scene["character_ids"] == ["char-1", "char-2"]

    def test_create_scene_nonexistent_project(self, client: TestClient):
        resp = client.post(
            "/api/projects/nonexistent/scenes",
            json={"title": "Orphan Scene"},
        )
        assert resp.status_code == 404


class TestListScenes:
    """GET /api/projects/{project_id}/scenes"""

    def test_list_empty(self, client: TestClient):
        project_id = _create_project(client)
        resp = client.get(f"/api/projects/{project_id}/scenes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_scenes(self, client: TestClient):
        project_id = _create_project(client)
        _create_scene(client, project_id, title="A")
        _create_scene(client, project_id, title="B")

        resp = client.get(f"/api/projects/{project_id}/scenes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_ordered_by_order(self, client: TestClient):
        project_id = _create_project(client)
        _create_scene(client, project_id, title="Second", order=2)
        _create_scene(client, project_id, title="First", order=1)

        resp = client.get(f"/api/projects/{project_id}/scenes")
        data = resp.json()
        assert data[0]["title"] == "First"
        assert data[1]["title"] == "Second"


class TestGetScene:
    """GET /api/projects/{project_id}/scenes/{scene_id}"""

    def test_get_scene(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id, title="My Scene")

        resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}"
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "My Scene"

    def test_get_nonexistent_scene(self, client: TestClient):
        project_id = _create_project(client)
        resp = client.get(f"/api/projects/{project_id}/scenes/nonexistent")
        assert resp.status_code == 404


class TestUpdateScene:
    """PUT /api/projects/{project_id}/scenes/{scene_id}"""

    def test_update_scene(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id, title="Original")

        resp = client.put(
            f"/api/projects/{project_id}/scenes/{scene['id']}",
            json={"title": "Updated", "summary": "New summary"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated"
        assert data["summary"] == "New summary"

    def test_update_nonexistent_scene(self, client: TestClient):
        project_id = _create_project(client)
        resp = client.put(
            f"/api/projects/{project_id}/scenes/nonexistent",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404


class TestDeleteScene:
    """DELETE /api/projects/{project_id}/scenes/{scene_id}"""

    def test_delete_scene(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id, title="Delete Me")

        resp = client.delete(
            f"/api/projects/{project_id}/scenes/{scene['id']}"
        )
        assert resp.status_code == 204

        # Verify deletion
        get_resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}"
        )
        assert get_resp.status_code == 404

    def test_delete_nonexistent_scene(self, client: TestClient):
        project_id = _create_project(client)
        resp = client.delete(
            f"/api/projects/{project_id}/scenes/nonexistent"
        )
        assert resp.status_code == 404


class TestReorderScenes:
    """PUT /api/projects/{project_id}/scenes (reorder)"""

    def test_reorder_scenes(self, client: TestClient):
        project_id = _create_project(client)
        s1 = _create_scene(client, project_id, title="Was First")
        s2 = _create_scene(client, project_id, title="Was Second")

        resp = client.put(
            f"/api/projects/{project_id}/scenes",
            json={
                "scenes": [
                    {"id": s1["id"], "order": 2},
                    {"id": s2["id"], "order": 1},
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["title"] == "Was Second"
        assert data[0]["order"] == 1
        assert data[1]["title"] == "Was First"
        assert data[1]["order"] == 2


# ===========================================================================
# Shot CRUD
# ===========================================================================

class TestCreateShot:
    """POST /api/projects/{project_id}/scenes/{scene_id}/shots"""

    def test_create_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        shot = _create_shot(client, project_id, scene["id"])
        assert shot["shot_type"] == "wide shot"
        assert shot["scene_id"] == scene["id"]
        assert shot["status"] == "Draft"

    def test_create_shot_auto_order(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        s1 = _create_shot(client, project_id, scene["id"], shot_type="shot1")
        s2 = _create_shot(client, project_id, scene["id"], shot_type="shot2")
        assert s1["order"] == 1
        assert s2["order"] == 2

    def test_create_shot_with_all_fields(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        resp = client.post(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots",
            json={
                "shot_type": "close-up",
                "camera_angle": "low angle",
                "camera_movement": "pan right",
                "lens_framing": "85mm",
                "subject": "Alice",
                "action": "smiling",
                "environment": "garden",
                "dialogue": "Hello world",
                "planned_duration_sec": 3.5,
                "generation_mode": "video",
                "image_prompt": "photo realistic",
                "video_prompt": "smooth motion",
                "negative_prompt": "blurry",
                "seed_policy": "fixed",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["camera_angle"] == "low angle"
        assert data["generation_mode"] == "video"
        assert data["planned_duration_sec"] == 3.5

    def test_create_shot_nonexistent_scene(self, client: TestClient):
        project_id = _create_project(client)
        resp = client.post(
            f"/api/projects/{project_id}/scenes/nonexistent/shots",
            json={"shot_type": "wide"},
        )
        assert resp.status_code == 404


class TestListShots:
    """GET /api/projects/{project_id}/scenes/{scene_id}/shots"""

    def test_list_empty(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_shots(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        _create_shot(client, project_id, scene["id"])
        _create_shot(client, project_id, scene["id"])

        resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetShot:
    """GET /api/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}"""

    def test_get_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        shot = _create_shot(client, project_id, scene["id"])

        resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/{shot['id']}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == shot["id"]

    def test_get_nonexistent_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/nonexistent"
        )
        assert resp.status_code == 404


class TestUpdateShot:
    """PUT /api/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}"""

    def test_update_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        shot = _create_shot(client, project_id, scene["id"])

        resp = client.put(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/{shot['id']}",
            json={"shot_type": "close-up", "action": "laughing"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["shot_type"] == "close-up"
        assert data["action"] == "laughing"

    def test_update_nonexistent_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        resp = client.put(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/nonexistent",
            json={"shot_type": "medium"},
        )
        assert resp.status_code == 404


class TestDeleteShot:
    """DELETE /api/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}"""

    def test_delete_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        shot = _create_shot(client, project_id, scene["id"])

        resp = client.delete(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/{shot['id']}"
        )
        assert resp.status_code == 204

        get_resp = client.get(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/{shot['id']}"
        )
        assert get_resp.status_code == 404

    def test_delete_nonexistent_shot(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        resp = client.delete(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots/nonexistent"
        )
        assert resp.status_code == 404


class TestReorderShots:
    """PUT /api/projects/{project_id}/scenes/{scene_id}/shots (reorder)"""

    def test_reorder_shots(self, client: TestClient):
        project_id = _create_project(client)
        scene = _create_scene(client, project_id)
        s1 = _create_shot(client, project_id, scene["id"], shot_type="first")
        s2 = _create_shot(client, project_id, scene["id"], shot_type="second")

        resp = client.put(
            f"/api/projects/{project_id}/scenes/{scene['id']}/shots",
            json={
                "shots": [
                    {"id": s1["id"], "order": 2},
                    {"id": s2["id"], "order": 1},
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["shot_type"] == "second"
        assert data[0]["order"] == 1
        assert data[1]["shot_type"] == "first"
        assert data[1]["order"] == 2
