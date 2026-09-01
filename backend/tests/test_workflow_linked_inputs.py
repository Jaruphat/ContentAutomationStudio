"""
Tests for linked inputs and the user's real API-format exports.

An input fed by a wire has no settable widget. Writing to one would be
silently ignored - ComfyUI executes the link instead - so a mapping that binds
to it looks correct and does nothing. The analysis therefore follows one hop
upstream and offers the driving node's widget, or explains why it cannot.
"""

import json
import os

import pytest

from app.services import job_payload
from app.services.workflow_analysis import (
    analyze_api_workflow,
    analyze_workflow,
    suggested_parameter_mapping,
)
from app.services.workflow_dependencies import check_dependencies
from app.services.workflow_format import WorkflowFormat

_WORKFLOW_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "workflows", "source")
)
_API_DIR = os.path.join(_WORKFLOW_ROOT, "api")


def candidate_for(analysis, logical_field):
    return next(
        (c for c in analysis.mapping_candidates if c.logical_field == logical_field),
        None,
    )


@pytest.fixture()
def wired_graph() -> dict:
    """An API graph whose video node has most inputs driven by wires."""
    return {
        "10": {
            "class_type": "VideoNode",
            "inputs": {
                "prompt": "a shot",
                "width": ["20", 0],        # from a resolution helper
                "height": ["20", 1],
                "length": ["30", 0],       # from a math expression
                "first_frame": ["40", 0],  # from an image loader
            },
        },
        "20": {
            "class_type": "ResolutionSelector",
            "inputs": {"aspect_ratio": "16:9", "megapixels": 0.4, "multiple": 32},
        },
        "30": {
            # Derives its output from node 60, mirroring the real workflows.
            "class_type": "MathExpression",
            "inputs": {"expression": "round(a * 24)", "values.a": ["60", 0]},
        },
        "40": {"class_type": "LoadImage", "inputs": {"image": "ref.png"}},
        "60": {"class_type": "PrimitiveFloat", "inputs": {"value": 5.0}},
        "50": {
            "class_type": "SaveVideo",
            "inputs": {"filename_prefix": "out", "video": ["10", 0]},
        },
    }


class TestLinkedInputs:
    def test_directly_settable_input_still_wins(self, wired_graph):
        candidate = candidate_for(
            analyze_api_workflow(wired_graph), job_payload.POSITIVE_PROMPT
        )
        assert candidate.node_id == "10"
        assert candidate.exposed is True

    def test_single_widget_upstream_node_is_proposed(self, wired_graph):
        candidate = candidate_for(
            analyze_api_workflow(wired_graph), job_payload.REFERENCE_IMAGE
        )
        assert candidate.node_id == "40"
        assert candidate.node_class == "LoadImage"
        assert candidate.input_name == "image"
        assert candidate.exposed is False
        assert candidate.match_kind == "upstream-widget"

    def test_upstream_note_names_both_nodes(self, wired_graph):
        candidate = candidate_for(
            analyze_api_workflow(wired_graph), job_payload.REFERENCE_IMAGE
        )
        assert "wired from" in candidate.note
        assert "LoadImage" in candidate.note

    def test_math_driven_frame_count_is_proposed_for_review(self, wired_graph):
        candidate = candidate_for(analyze_api_workflow(wired_graph), job_payload.FRAMES)
        assert candidate.node_id == "30"
        assert candidate.input_name == "expression"
        # Proposed, but not applied automatically: see TestAutoApplicability.
        assert candidate.auto_applicable is False

    def test_upstream_without_a_matching_widget_is_explained(self, wired_graph):
        """ResolutionSelector drives width and height but has no width widget,
        so no binding is invented; the driving node is named instead."""
        analysis = analyze_api_workflow(wired_graph)
        assert candidate_for(analysis, job_payload.WIDTH) is None
        assert job_payload.WIDTH in analysis.unmapped_logical_fields

        joined = " ".join(analysis.warnings)
        assert "ResolutionSelector" in joined
        assert "aspect_ratio" in joined
        assert "megapixels" in joined

    def test_applicable_mapping_never_points_at_a_wired_input(self, wired_graph):
        """Otherwise applying the mapping would be a silent no-op."""
        analysis = analyze_api_workflow(wired_graph)
        for logical_field, entry in suggested_parameter_mapping(analysis).items():
            value = wired_graph[entry["nodeId"]]["inputs"][entry["field"]]
            assert not isinstance(value, list), f"{logical_field} points at a wire"

    def test_reference_image_input_is_not_filed_as_a_frame_count(self, wired_graph):
        """The name first_frame contains 'frame' but means a reference image;
        a loose substring match would misfile it as the frame count."""
        analysis = analyze_api_workflow(wired_graph)
        assert candidate_for(analysis, job_payload.FRAMES).node_class == "MathExpression"

    def test_upstream_candidates_are_flagged_in_warnings(self, wired_graph):
        analysis = analyze_api_workflow(wired_graph)
        assert any("wired from another node" in w for w in analysis.warnings)


@pytest.mark.skipif(
    not os.path.isdir(_API_DIR),
    reason="workflows/source/api is not present in this checkout",
)
class TestRealApiExports:
    """The genuine ComfyUI API exports supplied by the user."""

    @pytest.fixture(params=[
        "video_minimax_h3_t2v.api.json",
        "video_minimax_h3_i2v.api.json",
    ])
    def api_export(self, request):
        path = os.path.join(_API_DIR, request.param)
        if not os.path.isfile(path):
            pytest.skip(f"{request.param} not present")
        with open(path, encoding="utf-8") as f:
            return request.param, json.load(f)

    def test_detected_as_api_and_submittable(self, api_export):
        name, data = api_export
        analysis = analyze_workflow(data)
        assert analysis.format is WorkflowFormat.API, name
        assert analysis.submittable is True

    def test_subgraphs_are_already_flattened(self, api_export):
        _name, data = api_export
        assert analyze_workflow(data).subgraphs == []

    def test_required_fields_have_applicable_bindings(self, api_export):
        name, data = api_export
        mapping = suggested_parameter_mapping(analyze_workflow(data))
        for logical_field in job_payload.REQUIRED_LOGICAL_FIELDS:
            assert logical_field in mapping, f"{name} lacks {logical_field}"
            entry = mapping[logical_field]
            value = data[entry["nodeId"]]["inputs"][entry["field"]]
            assert not isinstance(value, list)

    def test_suggested_mapping_passes_the_registry_validator(self, api_export):
        from app.services.workflow_registry import validate_mapping

        name, data = api_export
        valid, errors, _ = validate_mapping(
            workflow_data=data,
            parameter_mapping=suggested_parameter_mapping(analyze_workflow(data)),
            output_mapping=[],
        )
        assert valid, f"{name}: {errors}"

    def test_prompt_binds_to_the_video_node(self, api_export):
        _name, data = api_export
        mapping = suggested_parameter_mapping(analyze_workflow(data))
        node_id = mapping[job_payload.POSITIVE_PROMPT]["nodeId"]
        assert data[node_id]["class_type"] == "MiniMaxH3ImageToVideo"

    def test_seed_binds_to_the_noise_node(self, api_export):
        _name, data = api_export
        mapping = suggested_parameter_mapping(analyze_workflow(data))
        node_id = mapping[job_payload.SEED]["nodeId"]
        assert data[node_id]["class_type"] == "RandomNoise"

    def test_resolution_is_reported_as_wired(self, api_export):
        """Both exports drive width and height from ResolutionSelector, so
        neither is directly settable. That must be explained, not dropped."""
        _name, data = api_export
        analysis = analyze_workflow(data)
        assert job_payload.WIDTH in analysis.unmapped_logical_fields
        assert any("ResolutionSelector" in w for w in analysis.warnings)

    def test_models_match_the_ui_source(self, api_export):
        """The API export must need the same models as the editor graph it
        came from; a mismatch would mean the wrong file was exported."""
        name, data = api_export
        ui_name = name.replace(".api.json", ".ui.json")
        ui_path = os.path.join(_WORKFLOW_ROOT, "ui", ui_name)
        if not os.path.isfile(ui_path):
            pytest.skip(f"{ui_name} not present")
        with open(ui_path, encoding="utf-8") as f:
            ui_analysis = analyze_workflow(json.load(f))
        assert set(analyze_workflow(data).required_models) == set(
            ui_analysis.required_models
        )

    def test_dependencies_check_is_self_consistent(self, api_export):
        """Using the file's own class list as a stand-in catalogue must yield
        no missing nodes, proving the inventory and the checker agree."""
        _name, data = api_export
        analysis = analyze_workflow(data)
        catalogue = {c: {"input": {}} for c in analysis.required_node_classes}
        report = check_dependencies(analysis, catalogue)
        assert report.node_classes_missing == []


class TestAutoApplicability:
    """Applying a mapping must never silently change what a graph computes."""

    def test_leaf_source_is_auto_applicable(self, wired_graph):
        candidate = candidate_for(
            analyze_api_workflow(wired_graph), job_payload.REFERENCE_IMAGE
        )
        assert candidate.node_class == "LoadImage"
        assert candidate.auto_applicable is True

    def test_computed_source_is_review_only(self, wired_graph):
        """MathExpression derives its output from a wired input, so writing a
        constant over its formula would change the graph's behaviour."""
        candidate = candidate_for(analyze_api_workflow(wired_graph), job_payload.FRAMES)
        assert candidate.node_class == "MathExpression"
        assert candidate.auto_applicable is False

    def test_review_only_candidates_stay_out_of_the_mapping(self, wired_graph):
        analysis = analyze_api_workflow(wired_graph)
        mapping = suggested_parameter_mapping(analysis)
        assert job_payload.FRAMES not in mapping
        assert job_payload.REFERENCE_IMAGE in mapping

    def test_review_only_candidates_are_still_reported(self, wired_graph):
        analysis = analyze_api_workflow(wired_graph)
        assert candidate_for(analysis, job_payload.FRAMES) is not None
        assert any("overwrite a value the graph computes" in w for w in analysis.warnings)

    def test_directly_settable_inputs_remain_auto_applicable(self, wired_graph):
        candidate = candidate_for(
            analyze_api_workflow(wired_graph), job_payload.POSITIVE_PROMPT
        )
        assert candidate.auto_applicable is True
