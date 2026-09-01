"""
Tests for workflow inventory, mapping suggestion and dependency checking.

The synthetic fixtures mirror the structure of the user's real ComfyUI exports
(a subgraph whose interface inputs drive inner nodes) without depending on
those files. A separate class exercises the real files when they are present,
so the heuristics are checked against genuine ComfyUI output rather than only
against shapes written to suit them.
"""

import json
import os

import pytest

from app.services import job_payload
from app.services.workflow_analysis import (
    analyze_api_workflow,
    analyze_ui_workflow,
    analyze_workflow,
    suggested_parameter_mapping,
)
from app.services.workflow_dependencies import check_dependencies, known_model_files
from app.services.workflow_format import WorkflowFormat

# The real exports live outside the backend package, beside the repo root.
_REAL_WORKFLOW_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "workflows", "source", "ui")
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ui_with_subgraph() -> dict:
    """A UI workflow whose generation nodes live inside a subgraph.

    Mirrors how ComfyUI stores a subgraph: the node's ``type`` is the
    definition's UUID, and links from the virtual input node (-10) bind each
    interface input to an inner node input by slot index.
    """
    return {
        "last_node_id": 60,
        "nodes": [
            {
                "id": 32,
                "type": "LoadImage",
                "widgets_values": ["reference.png", "image"],
                "inputs": [{"name": "image", "type": "COMBO"}],
            },
            {
                "id": 45,
                "type": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "widgets_values": ["a prompt", 1024, 1024, 22],
                "inputs": [
                    {"name": "images.image_1", "type": "IMAGE", "link": 92},
                    {"name": "prompt", "type": "STRING"},
                    {"name": "width", "type": "INT"},
                ],
            },
            {
                "id": 55,
                "type": "SaveImageAdvanced",
                "widgets_values": ["My_Output", "png"],
                "inputs": [
                    {"name": "images", "type": "IMAGE"},
                    {"name": "filename_prefix", "type": "STRING"},
                ],
            },
            {"id": 56, "type": "MarkdownNote", "widgets_values": ["a note"]},
        ],
        "links": [],
        "definitions": {
            "subgraphs": [
                {
                    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "name": "Image Edit",
                    "inputs": [
                        {"name": "images.image_1", "type": "IMAGE"},
                        {"name": "prompt", "type": "STRING"},
                        {"name": "width", "type": "INT"},
                        {"name": "height", "type": "INT"},
                        {"name": "noise_seed", "type": "INT"},
                    ],
                    "outputs": [{"name": "IMAGE", "type": "IMAGE"}],
                    "nodes": [
                        {
                            "id": 2,
                            "type": "UNETLoader",
                            "widgets_values": ["diffusion.safetensors", "default"],
                            "inputs": [{"name": "unet_name", "type": "COMBO"}],
                        },
                        {
                            "id": 8,
                            "type": "EmptyLatentImage",
                            "widgets_values": [1024, 1024, 1],
                            "inputs": [
                                {"name": "width", "type": "INT"},
                                {"name": "height", "type": "INT"},
                            ],
                        },
                        {
                            "id": 36,
                            "type": "TextEncodeEdit",
                            "widgets_values": ["a prompt", ""],
                            "inputs": [
                                {"name": "clip", "type": "CLIP"},
                                {"name": "vae", "type": "VAE"},
                                {"name": "images", "type": "IMAGE"},
                                {"name": "negative_prompt", "type": "STRING"},
                                {"name": "prompt", "type": "STRING"},
                            ],
                        },
                        {
                            "id": 21,
                            "type": "SamplerCustom",
                            "widgets_values": [True, 22, "fixed", 3.5],
                            "inputs": [
                                {"name": "model", "type": "MODEL"},
                                {"name": "positive", "type": "CONDITIONING"},
                                {"name": "negative", "type": "CONDITIONING"},
                                {"name": "sampler", "type": "SAMPLER"},
                                {"name": "sigmas", "type": "SIGMAS"},
                                {"name": "latent_image", "type": "LATENT"},
                                {"name": "add_noise", "type": "BOOLEAN"},
                                {"name": "noise_seed", "type": "INT"},
                            ],
                        },
                        {
                            "id": 5,
                            "type": "VAELoader",
                            "widgets_values": ["ae.safetensors"],
                            "inputs": [{"name": "vae_name", "type": "COMBO"}],
                        },
                    ],
                    "links": [
                        # interface slot -> inner node input slot
                        {"origin_id": -10, "origin_slot": 0, "target_id": 36, "target_slot": 2},
                        {"origin_id": -10, "origin_slot": 1, "target_id": 36, "target_slot": 4},
                        {"origin_id": -10, "origin_slot": 2, "target_id": 8, "target_slot": 0},
                        {"origin_id": -10, "origin_slot": 3, "target_id": 8, "target_slot": 1},
                        {"origin_id": -10, "origin_slot": 4, "target_id": 21, "target_slot": 7},
                    ],
                }
            ]
        },
    }


@pytest.fixture()
def api_graph() -> dict:
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {"seed": 42, "steps": 20, "model": ["4", 0]},
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 576, "batch_size": 1},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["4", 1]}},
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"negative_prompt": "blurry", "clip": ["4", 1]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "out", "images": ["8", 0]},
        },
    }


def candidate_for(analysis, logical_field):
    return next(
        (c for c in analysis.mapping_candidates if c.logical_field == logical_field),
        None,
    )


# ---------------------------------------------------------------------------
# UI inventory
# ---------------------------------------------------------------------------

class TestUiInventory:
    def test_reports_ui_format_and_not_submittable(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        assert analysis.format is WorkflowFormat.UI
        assert analysis.submittable is False

    def test_inner_subgraph_nodes_are_inventoried(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        # Inner classes must appear; a check that only walked the top level
        # would miss every node that actually runs.
        assert "SamplerCustom" in analysis.required_node_classes
        assert "TextEncodeEdit" in analysis.required_node_classes
        assert "UNETLoader" in analysis.required_node_classes

    def test_subgraph_placeholder_type_is_not_required(self, ui_with_subgraph):
        """The UUID is a container, not a node class the server must provide."""
        analysis = analyze_workflow(ui_with_subgraph)
        assert not any("-" in c and len(c) == 36 for c in analysis.required_node_classes)

    def test_editor_only_nodes_separated(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        assert analysis.frontend_only_node_classes == ["MarkdownNote"]
        assert "MarkdownNote" not in analysis.required_node_classes

    def test_models_collected_from_inner_nodes(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        assert "diffusion.safetensors" in analysis.required_models
        assert "ae.safetensors" in analysis.required_models

    def test_non_model_widget_values_ignored(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        assert "fixed" not in analysis.required_models
        assert "png" not in analysis.required_models

    def test_subgraph_bindings_recorded(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        assert len(analysis.subgraphs) == 1
        bindings = analysis.subgraphs[0].input_bindings
        assert bindings["prompt"]["node_class"] == "TextEncodeEdit"
        assert bindings["prompt"]["input_name"] == "prompt"
        assert bindings["noise_seed"]["node_class"] == "SamplerCustom"


# ---------------------------------------------------------------------------
# Candidate mappings
# ---------------------------------------------------------------------------

class TestUiMappingCandidates:
    def test_prompt_traced_through_the_subgraph_interface(self, ui_with_subgraph):
        candidate = candidate_for(analyze_workflow(ui_with_subgraph), job_payload.POSITIVE_PROMPT)
        assert candidate is not None
        assert candidate.node_class == "TextEncodeEdit"
        assert candidate.input_name == "prompt"
        assert candidate.exposed is True

    def test_seed_prefers_the_sampler_over_a_widget(self, ui_with_subgraph):
        candidate = candidate_for(analyze_workflow(ui_with_subgraph), job_payload.SEED)
        assert candidate.node_class == "SamplerCustom"
        assert candidate.input_name == "noise_seed"

    def test_dotted_autogrow_input_name_is_matched(self, ui_with_subgraph):
        """ComfyUI names dynamic inputs 'group.slot'; the group is meaningful."""
        candidate = candidate_for(analyze_workflow(ui_with_subgraph), job_payload.REFERENCE_IMAGE)
        assert candidate.node_class == "TextEncodeEdit"

    def test_unexposed_inner_input_is_still_reported(self, ui_with_subgraph):
        """negative_prompt exists on an inner node but is not promoted to the
        subgraph interface; it is only reachable after API export."""
        analysis = analyze_workflow(ui_with_subgraph)
        candidate = candidate_for(analysis, job_payload.NEGATIVE_PROMPT)
        assert candidate is not None
        assert candidate.exposed is False
        assert "not expose" in candidate.note

    def test_unexposed_selection_raises_a_warning(self, ui_with_subgraph):
        analysis = analyze_workflow(ui_with_subgraph)
        assert any("not promoted" in w for w in analysis.warnings)

    def test_output_prefix_from_top_level_save_node(self, ui_with_subgraph):
        candidate = candidate_for(analyze_workflow(ui_with_subgraph), job_payload.OUTPUT_PREFIX)
        assert candidate.node_class == "SaveImageAdvanced"
        assert candidate.input_name == "filename_prefix"

    def test_no_node_ids_are_proposed_for_ui_workflows(self, ui_with_subgraph):
        """UI node ids are renumbered by ComfyUI's API export, so binding to
        them would silently point at the wrong node."""
        analysis = analyze_workflow(ui_with_subgraph)
        assert all(c.node_id is None for c in analysis.mapping_candidates)
        assert suggested_parameter_mapping(analysis) == {}

    def test_selection_is_independent_of_node_order(self, ui_with_subgraph):
        """Reversing the file's node order must not change the result."""
        first = analyze_workflow(ui_with_subgraph)
        ui_with_subgraph["nodes"].reverse()
        second = analyze_workflow(ui_with_subgraph)
        as_tuples = lambda a: sorted(  # noqa: E731
            (c.logical_field, c.node_class, c.input_name) for c in a.mapping_candidates
        )
        assert as_tuples(first) == as_tuples(second)


class TestApiMappingCandidates:
    def test_concrete_node_ids_are_proposed(self, api_graph):
        analysis = analyze_api_workflow(api_graph)
        candidate = candidate_for(analysis, job_payload.POSITIVE_PROMPT)
        assert candidate.node_id == "6"
        assert candidate.input_name == "text"

    def test_negative_prompt_not_confused_with_positive(self, api_graph):
        analysis = analyze_api_workflow(api_graph)
        assert candidate_for(analysis, job_payload.NEGATIVE_PROMPT).node_id == "7"
        assert candidate_for(analysis, job_payload.POSITIVE_PROMPT).node_id != "7"

    def test_suggested_mapping_is_directly_usable(self, api_graph):
        analysis = analyze_api_workflow(api_graph)
        mapping = suggested_parameter_mapping(analysis)
        assert mapping[job_payload.SEED] == {"nodeId": "3", "field": "seed"}
        assert mapping[job_payload.WIDTH] == {"nodeId": "5", "field": "width"}
        assert mapping[job_payload.OUTPUT_PREFIX] == {"nodeId": "9", "field": "filename_prefix"}

    def test_suggested_mapping_validates_against_its_own_workflow(self, api_graph):
        """A suggestion that its own validator rejects would be worthless."""
        from app.services.workflow_registry import validate_mapping

        analysis = analyze_api_workflow(api_graph)
        valid, errors, _ = validate_mapping(
            workflow_data=api_graph,
            parameter_mapping=suggested_parameter_mapping(analysis),
            output_mapping=[{"nodeId": "9", "type": "image"}],
        )
        assert valid, errors

    def test_linked_inputs_are_never_proposed(self, api_graph):
        """A list value is a wire to another node, not a settable widget."""
        analysis = analyze_api_workflow(api_graph)
        for candidate in analysis.mapping_candidates:
            value = api_graph[candidate.node_id]["inputs"][candidate.input_name]
            assert not isinstance(value, list)

    def test_required_fields_missing_produces_a_warning(self):
        analysis = analyze_api_workflow(
            {"1": {"class_type": "SaveImage", "inputs": {"filename_prefix": "x"}}}
        )
        assert job_payload.POSITIVE_PROMPT in analysis.unmapped_logical_fields
        assert any("required logical field" in w for w in analysis.warnings)


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------

class TestDependencyCheck:
    @pytest.fixture()
    def catalogue(self) -> dict:
        return {
            "UNETLoader": {
                "input": {"required": {"unet_name": [["diffusion.safetensors"], {}]}}
            },
            "VAELoader": {
                "input": {"required": {"vae_name": [["ae.safetensors", "other.safetensors"], {}]}}
            },
            "EmptyLatentImage": {"input": {"required": {"width": ["INT", {}]}}},
            "TextEncodeEdit": {"input": {}},
            "SamplerCustom": {
                "input": {"required": {"sampler_name": [["euler", "dpmpp_2m"], {}]}}
            },
            "SaveImageAdvanced": {"input": {}},
            "LoadImage": {"input": {}},
        }

    def test_all_present(self, ui_with_subgraph, catalogue):
        report = check_dependencies(analyze_workflow(ui_with_subgraph), catalogue)
        assert report.checked is True
        assert report.satisfied is True
        assert report.node_classes_missing == []
        assert report.models_missing == []

    def test_missing_node_class_reported(self, ui_with_subgraph, catalogue):
        del catalogue["SamplerCustom"]
        report = check_dependencies(analyze_workflow(ui_with_subgraph), catalogue)
        assert report.satisfied is False
        assert "SamplerCustom" in report.node_classes_missing
        assert "SamplerCustom" in report.summary()

    def test_missing_model_reported(self, ui_with_subgraph, catalogue):
        catalogue["UNETLoader"]["input"]["required"]["unet_name"] = [["something_else.safetensors"], {}]
        report = check_dependencies(analyze_workflow(ui_with_subgraph), catalogue)
        assert report.satisfied is False
        assert "diffusion.safetensors" in report.models_missing

    def test_editor_only_nodes_never_reported_missing(self, ui_with_subgraph, catalogue):
        report = check_dependencies(analyze_workflow(ui_with_subgraph), catalogue)
        assert "MarkdownNote" not in report.node_classes_missing
        assert "MarkdownNote" in report.node_classes_frontend_only

    def test_unavailable_catalogue_is_unchecked_not_failed(self, ui_with_subgraph):
        """A mock provider or an offline instance must not read as 'missing'."""
        report = check_dependencies(analyze_workflow(ui_with_subgraph), None)
        assert report.checked is False
        assert report.satisfied is False
        assert report.node_classes_missing == []
        assert "unavailable" in report.reason

    def test_model_files_gathered_from_any_combo(self, catalogue):
        files = known_model_files(catalogue)
        assert files == {"diffusion.safetensors", "ae.safetensors", "other.safetensors"}

    def test_enum_options_are_not_mistaken_for_models(self, catalogue):
        assert "euler" not in known_model_files(catalogue)
        assert "dpmpp_2m" not in known_model_files(catalogue)


# ---------------------------------------------------------------------------
# The user's real ComfyUI exports
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.isdir(_REAL_WORKFLOW_DIR),
    reason="workflows/source/ui is not present in this checkout",
)
class TestRealComfyUIExports:
    """Runs the heuristics against genuine ComfyUI output.

    Synthetic fixtures can accidentally be written to suit the code. These
    files came from the user's ComfyUI install unchanged.
    """

    @pytest.fixture(params=[
        "image_boogu_image_0_1_edit_int8.ui.json",
        "video_minimax_h3_t2v.ui.json",
        "video_minimax_h3_i2v.ui.json",
    ])
    def real_workflow(self, request):
        path = os.path.join(_REAL_WORKFLOW_DIR, request.param)
        if not os.path.isfile(path):
            pytest.skip(f"{request.param} not present")
        with open(path, encoding="utf-8") as f:
            return request.param, json.load(f)

    def test_all_detected_as_ui_format(self, real_workflow):
        name, data = real_workflow
        analysis = analyze_workflow(data)
        assert analysis.format is WorkflowFormat.UI, name
        assert analysis.submittable is False

    def test_all_use_subgraphs(self, real_workflow):
        _name, data = real_workflow
        assert analyze_workflow(data).subgraphs

    def test_prompt_and_seed_candidates_found(self, real_workflow):
        """Without these two a run is neither controllable nor reproducible."""
        name, data = real_workflow
        analysis = analyze_workflow(data)
        for logical_field in job_payload.REQUIRED_LOGICAL_FIELDS:
            assert candidate_for(analysis, logical_field) is not None, (
                f"{name} has no candidate for {logical_field}"
            )

    def test_models_are_discovered(self, real_workflow):
        name, data = real_workflow
        analysis = analyze_workflow(data)
        assert analysis.required_models, name
        assert all(m.endswith(".safetensors") for m in analysis.required_models)

    def test_no_uuid_placeholder_in_required_classes(self, real_workflow):
        _name, data = real_workflow
        analysis = analyze_workflow(data)
        for node_class in analysis.required_node_classes:
            assert not (len(node_class) == 36 and node_class.count("-") == 4)

    def test_never_proposes_node_ids(self, real_workflow):
        _name, data = real_workflow
        analysis = analyze_workflow(data)
        assert suggested_parameter_mapping(analysis) == {}

    def test_analysis_is_deterministic(self, real_workflow):
        _name, data = real_workflow
        first = analyze_workflow(data)
        second = analyze_workflow(data)
        assert [
            (c.logical_field, c.node_class, c.input_name)
            for c in first.mapping_candidates
        ] == [
            (c.logical_field, c.node_class, c.input_name)
            for c in second.mapping_candidates
        ]

    def test_image_workflow_maps_the_edit_encoder(self):
        path = os.path.join(_REAL_WORKFLOW_DIR, "image_boogu_image_0_1_edit_int8.ui.json")
        if not os.path.isfile(path):
            pytest.skip("image workflow not present")
        with open(path, encoding="utf-8") as f:
            analysis = analyze_workflow(json.load(f))
        prompt = candidate_for(analysis, job_payload.POSITIVE_PROMPT)
        assert prompt.node_class == "TextEncodeBooguEdit"
        assert prompt.input_name == "prompt"

    def test_video_workflow_maps_the_video_node(self):
        path = os.path.join(_REAL_WORKFLOW_DIR, "video_minimax_h3_i2v.ui.json")
        if not os.path.isfile(path):
            pytest.skip("video workflow not present")
        with open(path, encoding="utf-8") as f:
            analysis = analyze_workflow(json.load(f))
        prompt = candidate_for(analysis, job_payload.POSITIVE_PROMPT)
        assert prompt.node_class == "MiniMaxH3ImageToVideo"
        reference = candidate_for(analysis, job_payload.REFERENCE_IMAGE)
        assert reference.input_name == "first_frame"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_api_document_routed_to_api_analyser(self, api_graph):
        assert analyze_workflow(api_graph).format is WorkflowFormat.API

    def test_ui_document_routed_to_ui_analyser(self, ui_with_subgraph):
        assert analyze_workflow(ui_with_subgraph).format is WorkflowFormat.UI

    def test_unknown_document_yields_an_explained_empty_analysis(self):
        analysis = analyze_workflow({"something": "else"})
        assert analysis.format is WorkflowFormat.UNKNOWN
        assert analysis.required_node_classes == []
        assert analysis.warnings

    def test_missing_subgraph_definition_warns(self):
        analysis = analyze_ui_workflow({
            "nodes": [{"id": 1, "type": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}],
            "links": [],
        })
        assert any("not defined" in w for w in analysis.warnings)
