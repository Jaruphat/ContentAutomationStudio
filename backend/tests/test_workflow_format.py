"""
Tests for ComfyUI workflow format detection.

The distinction this module draws is the one that matters most for real
generation: an editor/UI graph looks like a workflow, is named like a workflow,
and is what ComfyUI's Save button produces - but /prompt rejects it. Detecting
that up front is the difference between a clear message and a confusing 400.
"""

import pytest

from app.services.workflow_format import (
    FRONTEND_ONLY_NODE_TYPES,
    WorkflowFormat,
    detect_format,
)


# ---------------------------------------------------------------------------
# Fixtures mirroring the two real shapes
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_workflow() -> dict:
    """A minimal API-format (prompt) document."""
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {"seed": 42, "steps": 20, "model": ["4", 0]},
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "model.safetensors"},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a cat", "clip": ["4", 1]},
        },
    }


@pytest.fixture()
def ui_workflow() -> dict:
    """A minimal UI-format (editor graph) document."""
    return {
        "id": "b1f0",
        "revision": 0,
        "last_node_id": 9,
        "last_link_id": 8,
        "nodes": [
            {
                "id": 3,
                "type": "KSampler",
                "widgets_values": [42, "fixed", 20],
                "inputs": [{"name": "model", "type": "MODEL", "link": 1}],
            },
            {
                "id": 6,
                "type": "CLIPTextEncode",
                "widgets_values": ["a cat"],
                "inputs": [{"name": "clip", "type": "CLIP", "link": 2}],
            },
        ],
        "links": [[1, 4, 0, 3, 0, "MODEL"], [2, 4, 1, 6, 0, "CLIP"]],
        "groups": [],
        "config": {},
        "extra": {},
        "version": 0.4,
    }


# ---------------------------------------------------------------------------
# API format
# ---------------------------------------------------------------------------

class TestApiFormat:
    def test_detected(self, api_workflow):
        result = detect_format(api_workflow)
        assert result.format is WorkflowFormat.API
        assert result.confidence == 1.0

    def test_is_submittable(self, api_workflow):
        assert detect_format(api_workflow).is_submittable is True

    def test_reason_mentions_class_type(self, api_workflow):
        reasons = " ".join(detect_format(api_workflow).reasons)
        assert "class_type" in reasons

    def test_indicators_count_entries(self, api_workflow):
        indicators = detect_format(api_workflow).indicators
        assert indicators["api_entry_count"] == 3
        assert indicators["api_entry_ratio"] == 1.0

    def test_single_node_document(self):
        result = detect_format({"1": {"class_type": "SaveImage", "inputs": {}}})
        assert result.format is WorkflowFormat.API


# ---------------------------------------------------------------------------
# UI format
# ---------------------------------------------------------------------------

class TestUiFormat:
    def test_detected(self, ui_workflow):
        result = detect_format(ui_workflow)
        assert result.format is WorkflowFormat.UI
        assert result.confidence == 1.0

    def test_is_not_submittable(self, ui_workflow):
        assert detect_format(ui_workflow).is_submittable is False

    def test_reasons_explain_the_problem_and_the_fix(self, ui_workflow):
        reasons = " ".join(detect_format(ui_workflow).reasons)
        assert "nodes" in reasons
        assert "cannot be submitted" in reasons
        assert "Export (API)" in reasons

    def test_indicators_count_nodes_and_links(self, ui_workflow):
        indicators = detect_format(ui_workflow).indicators
        assert indicators["node_array_count"] == 2
        assert indicators["link_count"] == 2
        assert "last_node_id" in indicators["ui_only_keys"]

    def test_nodes_array_alone_is_still_ui(self):
        """Editor keys strengthen the verdict but are not required for it."""
        result = detect_format({"nodes": [{"id": 1, "type": "KSampler"}]})
        assert result.format is WorkflowFormat.UI
        assert result.confidence == 0.8

    def test_empty_nodes_array_is_still_ui(self):
        assert detect_format({"nodes": [], "links": []}).format is WorkflowFormat.UI


# ---------------------------------------------------------------------------
# Subgraphs
# ---------------------------------------------------------------------------

class TestSubgraphDetection:
    def test_subgraphs_counted_and_explained(self, ui_workflow):
        ui_workflow["definitions"] = {
            "subgraphs": [{"id": "abc", "name": "Sampler", "nodes": []}]
        }
        result = detect_format(ui_workflow)
        assert result.uses_subgraphs is True
        assert result.indicators["subgraph_count"] == 1
        assert "flattens these during API export" in " ".join(result.reasons)

    def test_absent_subgraphs_report_zero(self, ui_workflow):
        result = detect_format(ui_workflow)
        assert result.uses_subgraphs is False
        assert result.indicators["subgraph_count"] == 0


# ---------------------------------------------------------------------------
# Unknown shapes
# ---------------------------------------------------------------------------

class TestUnknownFormat:
    @pytest.mark.parametrize("value", [[], "text", 42, None, True])
    def test_non_object_top_level(self, value):
        result = detect_format(value)
        assert result.format is WorkflowFormat.UNKNOWN
        assert result.is_submittable is False

    def test_empty_object(self):
        result = detect_format({})
        assert result.format is WorkflowFormat.UNKNOWN
        assert "empty" in " ".join(result.reasons).lower()

    def test_unrelated_object(self):
        result = detect_format({"name": "my workflow", "author": "someone"})
        assert result.format is WorkflowFormat.UNKNOWN

    def test_partial_api_document_is_not_trusted(self):
        """A half-converted export must not be treated as submittable."""
        result = detect_format({
            "1": {"class_type": "KSampler", "inputs": {}},
            "2": {"inputs": {}},          # no class_type
            "3": {"inputs": {}},
            "metadata": {"note": "hand edited"},
        })
        assert result.format is WorkflowFormat.UNKNOWN
        assert result.is_submittable is False
        assert "not" in " ".join(result.reasons).lower()

    def test_mostly_api_document_still_detected(self):
        """One stray key among many nodes should not derail detection."""
        data = {str(i): {"class_type": "X", "inputs": {}} for i in range(19)}
        data["extra_note"] = {"hello": "world"}
        result = detect_format(data)
        assert result.format is WorkflowFormat.API
        assert result.confidence == 0.9


# ---------------------------------------------------------------------------
# Frontend-only node types
# ---------------------------------------------------------------------------

class TestFrontendOnlyTypes:
    def test_note_types_listed(self):
        assert "MarkdownNote" in FRONTEND_ONLY_NODE_TYPES
        assert "Note" in FRONTEND_ONLY_NODE_TYPES
        assert "Reroute" in FRONTEND_ONLY_NODE_TYPES

    def test_real_node_classes_not_listed(self):
        assert "KSampler" not in FRONTEND_ONLY_NODE_TYPES
        assert "SaveImage" not in FRONTEND_ONLY_NODE_TYPES
