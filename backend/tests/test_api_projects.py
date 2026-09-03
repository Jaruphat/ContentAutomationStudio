"""
Tests for the Projects API endpoints.

Validates full CRUD operations via FastAPI TestClient.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import GenerationRun, Workflow


class TestCreateProject:
    """POST /api/projects"""

    def test_create_project_minimal(self, client: TestClient):
        response = client.post(
            "/api/projects",
            json={"title": "New Project"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Project"
        assert data["status"] == "Draft"
        assert data["content_type"] == "video"
        assert "id" in data
        assert "created_at" in data

    def test_create_project_full(self, client: TestClient):
        response = client.post(
            "/api/projects",
            json={
                "title": "Full Project",
                "objective": "Test all fields",
                "audience": "Developers",
                "content_type": "short-form",
                "aspect_ratio": "9:16",
                "target_resolution": "1080x1920",
                "target_duration_sec": 60.0,
                "frame_rate": 30.0,
                "language": "es",
                "status": "Active",
                "brief_text": "A comprehensive brief",
                "plot_text": "The plot unfolds",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Full Project"
        assert data["objective"] == "Test all fields"
        assert data["audience"] == "Developers"
        assert data["aspect_ratio"] == "9:16"
        assert data["language"] == "es"

    def test_create_project_missing_title_fails(self, client: TestClient):
        response = client.post(
            "/api/projects",
            json={},
        )
        assert response.status_code == 422  # Validation error

    def test_create_project_rejects_non_positive_or_odd_resolution(
        self, client: TestClient
    ):
        for resolution in ("-10x-20", "1921x1081", "invalid"):
            response = client.post(
                "/api/projects",
                json={"title": "Invalid resolution", "target_resolution": resolution},
            )
            assert response.status_code == 422, resolution

    def test_create_project_returns_uuid_id(self, client: TestClient):
        response = client.post(
            "/api/projects",
            json={"title": "UUID Test"},
        )
        assert response.status_code == 201
        data = response.json()
        # UUID should be 36 characters (8-4-4-4-12)
        assert len(data["id"]) == 36

    def test_create_project_derives_resolution_from_explicit_aspect(
        self, client: TestClient
    ):
        response = client.post(
            "/api/projects", json={"title": "Vertical", "aspect_ratio": "9:16"}
        )

        assert response.status_code == 201
        assert response.json()["target_resolution"] == "1080x1920"

    def test_create_project_assigns_runnable_local_workflow_defaults(
        self, client: TestClient, db_session: Session
    ):
        db_session.add_all(
            [
                Workflow(
                    id="image-t2i",
                    name="Local T2I",
                    purpose="image",
                    source_format="api",
                    validation_status="valid",
                    parameter_mapping={"positivePrompt": {}},
                    output_mapping=[{"nodeId": "1", "type": "image"}],
                ),
                Workflow(
                    id="image-edit",
                    name="Reference image edit",
                    purpose="image",
                    source_format="api",
                    validation_status="valid",
                    parameter_mapping={"positivePrompt": {}, "referenceImage": {}},
                    output_mapping=[{"nodeId": "2", "type": "image"}],
                ),
                Workflow(
                    id="video-t2v",
                    name="Local T2V",
                    purpose="text-to-video",
                    source_format="api",
                    validation_status="valid",
                    parameter_mapping={"positivePrompt": {}},
                    output_mapping=[{"nodeId": "3", "type": "video"}],
                ),
            ]
        )
        db_session.commit()

        response = client.post("/api/projects", json={"title": "Ready Project"})

        assert response.status_code == 201
        data = response.json()
        assert data["default_image_workflow_id"] == "image-t2i"
        assert data["default_video_workflow_id"] == "video-t2v"


class TestListProjects:
    """GET /api/projects"""

    def test_list_empty(self, client: TestClient):
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_created_projects(self, client: TestClient):
        client.post("/api/projects", json={"title": "Project A"})
        client.post("/api/projects", json={"title": "Project B"})

        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        titles = {p["title"] for p in data}
        assert "Project A" in titles
        assert "Project B" in titles

    def test_list_ordered_by_created_at_desc(self, client: TestClient):
        client.post("/api/projects", json={"title": "First"})
        client.post("/api/projects", json={"title": "Second"})

        response = client.get("/api/projects")
        data = response.json()
        # Most recent first
        assert data[0]["title"] == "Second"
        assert data[1]["title"] == "First"


class TestGetProject:
    """GET /api/projects/{project_id}"""

    def test_get_existing_project(self, client: TestClient):
        create_resp = client.post(
            "/api/projects", json={"title": "Get Me"}
        )
        project_id = create_resp.json()["id"]

        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Get Me"

    def test_get_nonexistent_project(self, client: TestClient):
        response = client.get("/api/projects/nonexistent-id")
        assert response.status_code == 404

    def test_get_returns_all_fields(self, client: TestClient):
        create_resp = client.post(
            "/api/projects",
            json={"title": "Fields Test", "brief_text": "My brief"},
        )
        project_id = create_resp.json()["id"]

        response = client.get(f"/api/projects/{project_id}")
        data = response.json()
        assert data["brief_text"] == "My brief"
        assert "updated_at" in data


class TestUpdateProject:
    """PUT /api/projects/{project_id}"""

    def test_update_title(self, client: TestClient):
        create_resp = client.post(
            "/api/projects", json={"title": "Original"}
        )
        project_id = create_resp.json()["id"]

        response = client.put(
            f"/api/projects/{project_id}",
            json={"title": "Updated"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated"

    def test_update_partial(self, client: TestClient):
        create_resp = client.post(
            "/api/projects",
            json={"title": "Partial", "objective": "Original objective"},
        )
        project_id = create_resp.json()["id"]

        response = client.put(
            f"/api/projects/{project_id}",
            json={"objective": "Updated objective"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Partial"  # Unchanged
        assert data["objective"] == "Updated objective"

    def test_update_nonexistent_project(self, client: TestClient):
        response = client.put(
            "/api/projects/nonexistent-id",
            json={"title": "Nope"},
        )
        assert response.status_code == 404

    def test_update_brief_and_plot(self, client: TestClient):
        create_resp = client.post(
            "/api/projects", json={"title": "Story Project"}
        )
        project_id = create_resp.json()["id"]

        response = client.put(
            f"/api/projects/{project_id}",
            json={
                "brief_text": "Updated brief",
                "plot_text": "Updated plot",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["brief_text"] == "Updated brief"
        assert data["plot_text"] == "Updated plot"

    def test_update_changes_updated_at(self, client: TestClient):
        create_resp = client.post(
            "/api/projects", json={"title": "Timestamp Test"}
        )
        project_id = create_resp.json()["id"]
        original_updated = create_resp.json()["updated_at"]

        response = client.put(
            f"/api/projects/{project_id}",
            json={"title": "Changed"},
        )
        new_updated = response.json()["updated_at"]
        assert new_updated >= original_updated


class TestDeleteProject:
    """DELETE /api/projects/{project_id}"""

    def test_delete_existing_project(self, client: TestClient):
        create_resp = client.post(
            "/api/projects", json={"title": "Delete Me"}
        )
        project_id = create_resp.json()["id"]

        response = client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_project(self, client: TestClient):
        response = client.delete("/api/projects/nonexistent-id")
        assert response.status_code == 404

    def test_delete_removes_generation_runs_without_sqlite_fk_cascades(
        self, client: TestClient, db_session: Session, sample_project, sample_shot
    ):
        generated = client.post(
            f"/api/projects/{sample_project.id}/generate", json={}
        )
        assert generated.status_code == 200, generated.text
        run_id = generated.json()[0]["run_id"]
        assert db_session.query(GenerationRun).filter(
            GenerationRun.id == run_id
        ).count() == 1

        deleted = client.delete(f"/api/projects/{sample_project.id}")

        assert deleted.status_code == 204
        assert db_session.query(GenerationRun).filter(
            GenerationRun.id == run_id
        ).count() == 0
        assert client.get(f"/api/runs/{run_id}").status_code == 404

    def test_delete_removes_from_list(self, client: TestClient):
        create_resp = client.post(
            "/api/projects", json={"title": "Will Be Deleted"}
        )
        project_id = create_resp.json()["id"]

        client.delete(f"/api/projects/{project_id}")

        list_resp = client.get("/api/projects")
        project_ids = [p["id"] for p in list_resp.json()]
        assert project_id not in project_ids
