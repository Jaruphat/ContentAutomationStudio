"""
Tests for the Workflows API endpoints.

Validates workflow import via file upload, mapping updates,
and validation against stored workflow JSON.
"""

import io
import json

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_workflow_bytes() -> bytes:
    """Return a minimal valid ComfyUI workflow JSON."""
    workflow = {
        "3": {
            "inputs": {
                "seed": 42,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
            },
            "class_type": "KSampler",
        },
        "6": {
            "inputs": {"text": "a landscape", "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": "ugly", "clip": ["4", 1]},
            "class_type": "CLIPTextEncode",
        },
        "9": {
            "inputs": {"filename_prefix": "output", "images": ["8", 0]},
            "class_type": "SaveImage",
        },
    }
    return json.dumps(workflow).encode("utf-8")


def _import_workflow(client: TestClient, name: str = "Test WF") -> dict:
    """Upload a workflow via the import endpoint and return the response dict."""
    wf_bytes = _sample_workflow_bytes()
    resp = client.post(
        "/api/workflows/import",
        files={"file": ("workflow.json", io.BytesIO(wf_bytes), "application/json")},
        data={"name": name, "purpose": "image", "version": "1.0"},
    )
    assert resp.status_code == 201
    return resp.json()


# ===========================================================================
# Import
# ===========================================================================

class TestImportWorkflow:
    """POST /api/workflows/import"""

    def test_import_workflow(self, client: TestClient):
        data = _import_workflow(client, name="My Workflow")
        assert data["name"] == "My Workflow"
        assert data["purpose"] == "image"
        assert data["version"] == "1.0"
        assert data["validation_status"] == "pending"
        assert len(data["id"]) == 36
        assert data["sha256_hash"] != ""

    def test_import_creates_source_file(self, client: TestClient):
        data = _import_workflow(client)
        assert data["source_json_path"] != ""

    def test_import_invalid_json(self, client: TestClient):
        resp = client.post(
            "/api/workflows/import",
            files={
                "file": (
                    "bad.json",
                    io.BytesIO(b"not valid json"),
                    "application/json",
                )
            },
            data={"name": "Bad WF"},
        )
        assert resp.status_code == 400

    def test_import_with_purpose(self, client: TestClient):
        wf_bytes = _sample_workflow_bytes()
        resp = client.post(
            "/api/workflows/import",
            files={"file": ("wf.json", io.BytesIO(wf_bytes), "application/json")},
            data={"name": "Video WF", "purpose": "text-to-video"},
        )
        assert resp.status_code == 201
        assert resp.json()["purpose"] == "text-to-video"

    def test_import_empty_mappings(self, client: TestClient):
        data = _import_workflow(client)
        assert data["parameter_mapping"] == {}
        assert data["output_mapping"] == []


# ===========================================================================
# List & Get
# ===========================================================================

class TestListWorkflows:
    """GET /api/workflows"""

    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_import(self, client: TestClient):
        _import_workflow(client, name="WF A")
        _import_workflow(client, name="WF B")

        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestGetWorkflow:
    """GET /api/workflows/{workflow_id}"""

    def test_get_workflow(self, client: TestClient):
        imported = _import_workflow(client)
        resp = client.get(f"/api/workflows/{imported['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == imported["id"]

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get("/api/workflows/nonexistent")
        assert resp.status_code == 404


# ===========================================================================
# Mapping Update
# ===========================================================================

class TestUpdateMapping:
    """PUT /api/workflows/{workflow_id}/mapping"""

    def test_update_mapping(self, client: TestClient):
        imported = _import_workflow(client)
        mapping_payload = {
            "parameter_mapping": {
                "positivePrompt": {"nodeId": "6", "field": "text"},
                "seed": {"nodeId": "3", "field": "seed"},
            },
            "output_mapping": [{"nodeId": "9", "type": "image"}],
        }

        resp = client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json=mapping_payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parameter_mapping"]["positivePrompt"]["nodeId"] == "6"
        assert len(data["output_mapping"]) == 1
        assert data["validation_status"] == "pending"

    def test_update_mapping_nonexistent(self, client: TestClient):
        resp = client.put(
            "/api/workflows/nonexistent/mapping",
            json={"parameter_mapping": {}, "output_mapping": []},
        )
        assert resp.status_code == 404

    def test_update_mapping_resets_validation_status(self, client: TestClient):
        imported = _import_workflow(client)
        # Set mapping
        client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json={
                "parameter_mapping": {"seed": {"nodeId": "3", "field": "seed"}},
                "output_mapping": [{"nodeId": "9", "type": "image"}],
            },
        )
        # Validate
        client.post(f"/api/workflows/{imported['id']}/validate")

        # Update mapping again
        resp = client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json={
                "parameter_mapping": {
                    "positivePrompt": {"nodeId": "6", "field": "text"}
                },
            },
        )
        assert resp.json()["validation_status"] == "pending"


# ===========================================================================
# Validation
# ===========================================================================

class TestValidateWorkflow:
    """POST /api/workflows/{workflow_id}/validate"""

    def test_validate_valid_mapping(self, client: TestClient):
        imported = _import_workflow(client)
        # Set a valid mapping
        client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json={
                "parameter_mapping": {
                    "positivePrompt": {"nodeId": "6", "field": "text"},
                    "seed": {"nodeId": "3", "field": "seed"},
                },
                "output_mapping": [{"nodeId": "9", "type": "image"}],
            },
        )

        resp = client.post(f"/api/workflows/{imported['id']}/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert len(data["errors"]) == 0

    def test_validate_invalid_node_id(self, client: TestClient):
        imported = _import_workflow(client)
        client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json={
                "parameter_mapping": {
                    "prompt": {"nodeId": "999", "field": "text"},
                },
            },
        )

        resp = client.post(f"/api/workflows/{imported['id']}/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_invalid_field(self, client: TestClient):
        imported = _import_workflow(client)
        client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json={
                "parameter_mapping": {
                    "prompt": {"nodeId": "6", "field": "nonexistent"},
                },
            },
        )

        resp = client.post(f"/api/workflows/{imported['id']}/validate")
        data = resp.json()
        assert data["valid"] is False

    def test_validate_nonexistent_workflow(self, client: TestClient):
        resp = client.post("/api/workflows/nonexistent/validate")
        assert resp.status_code == 404

    def test_validate_updates_status_in_db(self, client: TestClient):
        imported = _import_workflow(client)
        client.put(
            f"/api/workflows/{imported['id']}/mapping",
            json={
                "parameter_mapping": {
                    "seed": {"nodeId": "3", "field": "seed"},
                },
                "output_mapping": [{"nodeId": "9", "type": "image"}],
            },
        )

        client.post(f"/api/workflows/{imported['id']}/validate")

        # Check the workflow record reflects validated status
        get_resp = client.get(f"/api/workflows/{imported['id']}")
        assert get_resp.json()["validation_status"] == "valid"

    def test_validate_empty_mappings_has_warnings(self, client: TestClient):
        imported = _import_workflow(client)
        # Don't set any mapping, validate with defaults (empty)
        resp = client.post(f"/api/workflows/{imported['id']}/validate")
        data = resp.json()
        assert data["valid"] is True  # Empty mapping is not an error
        assert len(data["warnings"]) > 0


# ===========================================================================
# Delete
# ===========================================================================

class TestDeleteWorkflow:
    """DELETE /api/workflows/{workflow_id}"""

    def test_delete_workflow(self, client: TestClient):
        imported = _import_workflow(client)
        resp = client.delete(f"/api/workflows/{imported['id']}")
        assert resp.status_code == 204

        get_resp = client.get(f"/api/workflows/{imported['id']}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent(self, client: TestClient):
        resp = client.delete("/api/workflows/nonexistent")
        assert resp.status_code == 404
