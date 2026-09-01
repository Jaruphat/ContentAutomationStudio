"""
Tests for workflow format detection on import and the analysis endpoint.

The behaviour under test is the one that protects a live ComfyUI: an editor
graph can be imported and inspected, but is never marked runnable, and no
mapping is offered that would bind to node ids the API export will renumber.
"""

import json

import pytest


@pytest.fixture()
def ui_workflow_json() -> bytes:
    """A ComfyUI editor/UI graph - the shape /prompt cannot execute.

    Structured like a real export: a subgraph node whose type is the
    definition's UUID, with interface inputs wired to inner nodes by slot.
    """
    workflow = {
        "id": "test-ui-workflow",
        "revision": 0,
        "last_node_id": 60,
        "last_link_id": 20,
        "nodes": [
            {
                "id": 40,
                "type": "11111111-2222-3333-4444-555555555555",
                "widgets_values": ["a prompt", 1024, 1024, 7],
                "inputs": [
                    {"name": "prompt", "type": "STRING"},
                    {"name": "width", "type": "INT"},
                ],
                "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
            },
            {
                "id": 50,
                "type": "SaveImage",
                "widgets_values": ["Result"],
                "inputs": [
                    {"name": "images", "type": "IMAGE"},
                    {"name": "filename_prefix", "type": "STRING"},
                ],
            },
            {"id": 51, "type": "MarkdownNote", "widgets_values": ["notes"]},
        ],
        "links": [[1, 40, 0, 50, 0, "IMAGE"]],
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
        "definitions": {
            "subgraphs": [
                {
                    "id": "11111111-2222-3333-4444-555555555555",
                    "name": "Sampler Group",
                    "inputs": [
                        {"name": "prompt", "type": "STRING"},
                        {"name": "width", "type": "INT"},
                        {"name": "height", "type": "INT"},
                        {"name": "noise_seed", "type": "INT"},
                    ],
                    "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    "nodes": [
                        {
                            "id": 1,
                            "type": "CheckpointLoaderSimple",
                            "widgets_values": ["sd_xl_base_1.0.safetensors"],
                            "inputs": [{"name": "ckpt_name", "type": "COMBO"}],
                        },
                        {
                            "id": 2,
                            "type": "CLIPTextEncode",
                            "widgets_values": ["a prompt"],
                            "inputs": [
                                {"name": "clip", "type": "CLIP"},
                                {"name": "text", "type": "STRING"},
                            ],
                        },
                        {
                            "id": 3,
                            "type": "EmptyLatentImage",
                            "widgets_values": [1024, 1024, 1],
                            "inputs": [
                                {"name": "width", "type": "INT"},
                                {"name": "height", "type": "INT"},
                            ],
                        },
                        {
                            "id": 4,
                            "type": "KSampler",
                            "widgets_values": [7, "fixed", 20],
                            "inputs": [
                                {"name": "model", "type": "MODEL"},
                                {"name": "seed", "type": "INT"},
                            ],
                        },
                    ],
                    "links": [
                        {"origin_id": -10, "origin_slot": 0, "target_id": 2, "target_slot": 1},
                        {"origin_id": -10, "origin_slot": 1, "target_id": 3, "target_slot": 0},
                        {"origin_id": -10, "origin_slot": 2, "target_id": 3, "target_slot": 1},
                        {"origin_id": -10, "origin_slot": 3, "target_id": 4, "target_slot": 1},
                    ],
                }
            ]
        },
    }
    return json.dumps(workflow).encode("utf-8")


def import_workflow(client, payload: bytes, name: str) -> str:
    resp = client.post(
        "/api/workflows/import",
        files={"file": ("wf.json", payload, "application/json")},
        data={"name": name, "purpose": "image"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Format detection on import
# ---------------------------------------------------------------------------

class TestImportFormatDetection:
    """A UI graph must be importable for inspection but never runnable."""

    def test_api_import_is_marked_api_and_pending(self, client, sample_workflow_json):
        resp = client.post(
            "/api/workflows/import",
            files={"file": ("wf.json", sample_workflow_json, "application/json")},
            data={"name": "API WF", "purpose": "image"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["source_format"] == "api"
        assert body["validation_status"] == "pending"

    def test_ui_import_is_marked_ui_and_unsupported(self, client, ui_workflow_json):
        resp = client.post(
            "/api/workflows/import",
            files={"file": ("wf.json", ui_workflow_json, "application/json")},
            data={"name": "UI WF", "purpose": "image"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["source_format"] == "ui"
        # Not "pending": no mapping can make an editor graph submittable.
        assert body["validation_status"] == "unsupported_format"

    def test_ui_import_is_still_stored_for_inspection(self, client, ui_workflow_json):
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        assert client.get(f"/api/workflows/{workflow_id}").status_code == 200


# ---------------------------------------------------------------------------
# Analysis endpoint
# ---------------------------------------------------------------------------

class TestAnalysisEndpoint:
    def test_analyses_a_ui_workflow(self, client, ui_workflow_json):
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        resp = client.get(f"/api/workflows/{workflow_id}/analysis")
        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "ui"
        assert body["submittable"] is False
        assert "Export (API)" in body["blocking_reason"]
        assert body["required_node_classes"]

    def test_analysis_reaches_inside_the_subgraph(self, client, ui_workflow_json):
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        body = client.get(f"/api/workflows/{workflow_id}/analysis").json()
        assert "KSampler" in body["required_node_classes"]
        assert "sd_xl_base_1.0.safetensors" in body["required_models"]
        assert body["subgraphs"][0]["name"] == "Sampler Group"

    def test_editor_only_nodes_are_not_required(self, client, ui_workflow_json):
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        body = client.get(f"/api/workflows/{workflow_id}/analysis").json()
        assert "MarkdownNote" in body["frontend_only_node_classes"]
        assert "MarkdownNote" not in body["required_node_classes"]

    def test_ui_analysis_offers_no_applicable_mapping(self, client, ui_workflow_json):
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        body = client.get(f"/api/workflows/{workflow_id}/analysis").json()
        # Candidates are described, but none can bind to a node id yet.
        assert body["mapping_candidates"]
        assert body["suggested_parameter_mapping"] == {}

    def test_api_analysis_offers_an_applicable_mapping(self, client, sample_workflow_json):
        workflow_id = import_workflow(client, sample_workflow_json, "API WF")
        body = client.get(f"/api/workflows/{workflow_id}/analysis").json()
        assert body["format"] == "api"
        assert body["submittable"] is True
        assert body["blocking_reason"] == ""
        assert body["suggested_parameter_mapping"]

    def test_suggested_mapping_can_be_applied_and_validated(
        self, client, sample_workflow_json
    ):
        """The point of a suggestion: apply it, then have validation pass."""
        workflow_id = import_workflow(client, sample_workflow_json, "API WF")
        suggestion = client.get(
            f"/api/workflows/{workflow_id}/analysis"
        ).json()["suggested_parameter_mapping"]

        applied = client.put(
            f"/api/workflows/{workflow_id}/mapping",
            json={"parameter_mapping": suggestion, "output_mapping": []},
        )
        assert applied.status_code == 200

        validated = client.post(f"/api/workflows/{workflow_id}/validate").json()
        assert validated["valid"] is True, validated["errors"]

    def test_dependencies_unchecked_without_a_catalogue(self, client, ui_workflow_json):
        """The mock provider has no /object_info. That must read as
        'not checked', never as 'everything is missing'."""
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        deps = client.get(f"/api/workflows/{workflow_id}/analysis").json()["dependencies"]
        assert deps["checked"] is False
        assert deps["satisfied"] is False
        assert deps["node_classes_missing"] == []
        assert "unavailable" in deps["reason"]

    def test_unknown_workflow_is_404(self, client):
        assert client.get("/api/workflows/nope/analysis").status_code == 404


# ---------------------------------------------------------------------------
# The submission guard
# ---------------------------------------------------------------------------

class TestUiFormatCannotBeSubmitted:
    def test_real_provider_refuses_to_build_a_payload(
        self, client, db_session, ui_workflow_json, sample_shot
    ):
        """The guard that keeps UI JSON away from /prompt."""
        import uuid

        from app.models import GenerationJob, Workflow
        from app.services.job_payload import (
            POSITIVE_PROMPT,
            SEED,
            WorkflowValidationError,
            build_payload,
        )

        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        workflow = db_session.query(Workflow).filter(Workflow.id == workflow_id).first()
        # Even with a mapping filled in, the format alone must block it.
        workflow.parameter_mapping = {
            POSITIVE_PROMPT: {"nodeId": "40", "field": "prompt"},
            SEED: {"nodeId": "40", "field": "noise_seed"},
        }
        db_session.commit()

        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            workflow_id=workflow_id,
            parameter_map={POSITIVE_PROMPT: "a shot", SEED: 5},
            seed=5,
            status="Queued",
        )
        db_session.add(job)
        db_session.commit()

        with pytest.raises(WorkflowValidationError) as exc_info:
            build_payload(db_session, job, require_workflow=True)
        message = str(exc_info.value)
        assert "ui-format" in message
        assert "Export (API)" in message

    def test_mock_provider_still_generates(
        self, client, db_session, ui_workflow_json, sample_shot
    ):
        """Mock generation must keep working: it never touches the graph, so a
        UI-format workflow degrades to passthrough rather than blocking the
        product flow."""
        import uuid

        from app.models import GenerationJob
        from app.services.job_payload import POSITIVE_PROMPT, SEED, build_payload

        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            workflow_id=workflow_id,
            parameter_map={POSITIVE_PROMPT: "a shot", SEED: 5},
            seed=5,
            status="Queued",
        )
        db_session.add(job)
        db_session.commit()

        built = build_payload(db_session, job, require_workflow=False)
        assert built.passthrough is True
        assert built.payload[POSITIVE_PROMPT] == "a shot"
        # Nothing resembling a graph was produced.
        assert "nodes" not in built.payload


class TestPreflightReportsFormat:
    """Preflight must keep the specific reason, not flatten it to 'invalid'."""

    def test_ui_workflow_reported_as_unsupported_not_invalid(
        self, client, db_session, ui_workflow_json, sample_project, sample_shot
    ):
        from app.models import Workflow

        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        sample_project.default_image_workflow_id = workflow_id
        db_session.commit()

        body = client.get(f"/api/projects/{sample_project.id}/preflight").json()
        check = next(
            c for c in body["workflow_checks"] if c["workflow_id"] == workflow_id
        )
        assert check["valid"] is False
        assert check["source_format"] == "ui"
        assert "Export (API)" in " ".join(check["errors"])

        stored = db_session.query(Workflow).filter(Workflow.id == workflow_id).first()
        db_session.refresh(stored)
        assert stored.validation_status == "unsupported_format"

    def test_shots_using_a_ui_workflow_are_not_ready(
        self, client, db_session, ui_workflow_json, sample_project, sample_shot
    ):
        workflow_id = import_workflow(client, ui_workflow_json, "UI WF")
        sample_project.default_image_workflow_id = workflow_id
        db_session.commit()

        body = client.get(f"/api/projects/{sample_project.id}/preflight").json()
        assert body["ready"] is False
        assert body["issues"]
