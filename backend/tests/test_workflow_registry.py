"""
Tests for the workflow registry service.

Validates JSON parsing, SHA-256 hashing, mapping validation,
parameter application, and the full import pipeline.
"""

import hashlib
import json

import pytest

from app.services.workflow_registry import (
    apply_parameter_mapping,
    compute_sha256,
    extract_node_field_names,
    extract_node_ids,
    import_workflow,
    parse_workflow_json,
    validate_mapping,
)


# ---------------------------------------------------------------------------
# parse_workflow_json
# ---------------------------------------------------------------------------

class TestParseWorkflowJson:
    """Tests for parse_workflow_json."""

    def test_valid_json(self, sample_workflow_json: bytes):
        result = parse_workflow_json(sample_workflow_json)
        assert isinstance(result, dict)
        assert "3" in result
        assert "6" in result

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_workflow_json(b"not valid json {{{")

    def test_non_object_json_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_workflow_json(b'[1, 2, 3]')

    def test_empty_object(self):
        result = parse_workflow_json(b'{}')
        assert result == {}

    def test_utf8_encoding(self):
        data = {"1": {"inputs": {"text": "Hello \u00e9"}, "class_type": "Test"}}
        raw = json.dumps(data).encode("utf-8")
        result = parse_workflow_json(raw)
        assert result["1"]["inputs"]["text"] == "Hello \u00e9"


# ---------------------------------------------------------------------------
# compute_sha256
# ---------------------------------------------------------------------------

class TestComputeSha256:
    """Tests for compute_sha256."""

    def test_known_hash(self):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(content) == expected

    def test_deterministic(self, sample_workflow_json: bytes):
        hash1 = compute_sha256(sample_workflow_json)
        hash2 = compute_sha256(sample_workflow_json)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        assert compute_sha256(b"aaa") != compute_sha256(b"bbb")

    def test_empty_content(self):
        result = compute_sha256(b"")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex digest is 64 chars


# ---------------------------------------------------------------------------
# extract_node_ids / extract_node_field_names
# ---------------------------------------------------------------------------

class TestExtractNodeIds:
    """Tests for extract_node_ids."""

    def test_extracts_all_node_ids(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        node_ids = extract_node_ids(data)
        assert "3" in node_ids
        assert "4" in node_ids
        assert "6" in node_ids
        assert "9" in node_ids

    def test_empty_workflow(self):
        node_ids = extract_node_ids({})
        assert node_ids == set()


class TestExtractNodeFieldNames:
    """Tests for extract_node_field_names."""

    def test_extracts_fields(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        fields = extract_node_field_names(data, "3")
        assert "seed" in fields
        assert "steps" in fields
        assert "cfg" in fields
        assert "sampler_name" in fields

    def test_nonexistent_node(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        fields = extract_node_field_names(data, "999")
        assert fields == set()

    def test_clip_text_encode_fields(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        fields = extract_node_field_names(data, "6")
        assert "text" in fields
        assert "clip" in fields


# ---------------------------------------------------------------------------
# validate_mapping
# ---------------------------------------------------------------------------

class TestValidateMapping:
    """Tests for validate_mapping."""

    def test_valid_mapping(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": {"nodeId": "6", "field": "text"},
            "negativePrompt": {"nodeId": "7", "field": "text"},
            "seed": {"nodeId": "3", "field": "seed"},
        }
        output_mapping = [{"nodeId": "9", "type": "image"}]

        is_valid, errors, warnings = validate_mapping(data, param_mapping, output_mapping)
        assert is_valid is True
        assert len(errors) == 0

    def test_missing_node_id_error(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": {"nodeId": "999", "field": "text"},
        }
        is_valid, errors, warnings = validate_mapping(data, param_mapping, [])
        assert is_valid is False
        assert any("999" in e and "not found" in e for e in errors)

    def test_missing_field_error(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": {"nodeId": "6", "field": "nonexistent_field"},
        }
        is_valid, errors, warnings = validate_mapping(data, param_mapping, [])
        assert is_valid is False
        assert any("nonexistent_field" in e and "not found" in e for e in errors)

    def test_missing_node_id_key_error(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": {"field": "text"},  # missing nodeId
        }
        is_valid, errors, warnings = validate_mapping(data, param_mapping, [])
        assert is_valid is False
        assert any("missing 'nodeId'" in e for e in errors)

    def test_missing_field_key_error(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": {"nodeId": "6"},  # missing field
        }
        is_valid, errors, warnings = validate_mapping(data, param_mapping, [])
        assert is_valid is False
        assert any("missing 'field'" in e for e in errors)

    def test_non_dict_mapping_value_error(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": "invalid",
        }
        is_valid, errors, warnings = validate_mapping(data, param_mapping, [])
        assert is_valid is False
        assert any("must be a dict" in e for e in errors)

    def test_invalid_output_mapping_node(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        output_mapping = [{"nodeId": "999", "type": "image"}]
        is_valid, errors, warnings = validate_mapping(data, {}, output_mapping)
        assert is_valid is False
        assert any("999" in e and "not found" in e for e in errors)

    def test_output_mapping_missing_node_id(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        output_mapping = [{"type": "image"}]  # missing nodeId
        is_valid, errors, warnings = validate_mapping(data, {}, output_mapping)
        assert is_valid is False
        assert any("missing 'nodeId'" in e for e in errors)

    def test_output_mapping_non_dict(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        output_mapping = ["invalid"]
        is_valid, errors, warnings = validate_mapping(data, {}, output_mapping)
        assert is_valid is False
        assert any("must be a dict" in e for e in errors)

    def test_warning_no_parameter_mappings(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        is_valid, errors, warnings = validate_mapping(data, {}, [{"nodeId": "9", "type": "image"}])
        assert is_valid is True
        assert any("No parameter mappings" in w for w in warnings)

    def test_warning_no_output_mappings(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {"seed": {"nodeId": "3", "field": "seed"}}
        is_valid, errors, warnings = validate_mapping(data, param_mapping, [])
        assert is_valid is True
        assert any("No output mappings" in w for w in warnings)


# ---------------------------------------------------------------------------
# apply_parameter_mapping
# ---------------------------------------------------------------------------

class TestApplyParameterMapping:
    """Tests for apply_parameter_mapping."""

    def test_apply_values(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {
            "positivePrompt": {"nodeId": "6", "field": "text"},
            "seed": {"nodeId": "3", "field": "seed"},
        }
        values = {
            "positivePrompt": "a beautiful cat",
            "seed": 12345,
        }

        result = apply_parameter_mapping(data, param_mapping, values)

        assert result["6"]["inputs"]["text"] == "a beautiful cat"
        assert result["3"]["inputs"]["seed"] == 12345

    def test_does_not_modify_original(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        original_text = data["6"]["inputs"]["text"]
        param_mapping = {"positivePrompt": {"nodeId": "6", "field": "text"}}
        values = {"positivePrompt": "modified text"}

        apply_parameter_mapping(data, param_mapping, values)

        # Original should be unchanged
        assert data["6"]["inputs"]["text"] == original_text

    def test_unmapped_values_ignored(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {"seed": {"nodeId": "3", "field": "seed"}}
        values = {
            "seed": 99,
            "unknownParam": "should be ignored",
        }

        result = apply_parameter_mapping(data, param_mapping, values)
        assert result["3"]["inputs"]["seed"] == 99

    def test_empty_values(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {"seed": {"nodeId": "3", "field": "seed"}}

        result = apply_parameter_mapping(data, param_mapping, {})
        # No values applied, original values preserved
        assert result["3"]["inputs"]["seed"] == 42

    def test_nonexistent_node_in_mapping_skipped(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {"seed": {"nodeId": "999", "field": "seed"}}
        values = {"seed": 12345}

        result = apply_parameter_mapping(data, param_mapping, values)
        # Should not crash; node 999 doesn't exist, so nothing changes
        assert "999" not in result

    def test_mapping_with_empty_node_id_skipped(self, sample_workflow_json: bytes):
        data = parse_workflow_json(sample_workflow_json)
        param_mapping = {"seed": {"nodeId": "", "field": "seed"}}
        values = {"seed": 12345}

        result = apply_parameter_mapping(data, param_mapping, values)
        # Should not crash
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# import_workflow
# ---------------------------------------------------------------------------

class TestImportWorkflow:
    """Tests for the full import_workflow pipeline."""

    def test_import_returns_record_dict(self, sample_workflow_json: bytes):
        result = import_workflow(sample_workflow_json, name="Test Workflow")
        assert isinstance(result, dict)
        assert result["name"] == "Test Workflow"
        assert result["purpose"] == "image"
        assert result["version"] == "1.0"
        assert result["validation_status"] == "pending"

    def test_import_generates_uuid_id(self, sample_workflow_json: bytes):
        result = import_workflow(sample_workflow_json, name="Test")
        assert "id" in result
        assert len(result["id"]) == 36  # UUID string length

    def test_import_computes_sha256(self, sample_workflow_json: bytes):
        result = import_workflow(sample_workflow_json, name="Test")
        expected_hash = compute_sha256(sample_workflow_json)
        assert result["sha256_hash"] == expected_hash

    def test_import_saves_source_file(self, sample_workflow_json: bytes):
        import os
        result = import_workflow(sample_workflow_json, name="Test")
        assert os.path.isfile(result["source_json_path"])

    def test_import_with_custom_purpose(self, sample_workflow_json: bytes):
        result = import_workflow(
            sample_workflow_json, name="Video WF", purpose="text-to-video"
        )
        assert result["purpose"] == "text-to-video"

    def test_import_with_models_and_nodes(self, sample_workflow_json: bytes):
        result = import_workflow(
            sample_workflow_json,
            name="Full",
            required_models=["model_a.safetensors"],
            required_custom_nodes=["ComfyUI-Impact-Pack"],
        )
        assert result["required_models"] == ["model_a.safetensors"]
        assert result["required_custom_nodes"] == ["ComfyUI-Impact-Pack"]

    def test_import_invalid_json_raises(self):
        with pytest.raises(ValueError):
            import_workflow(b"not json", name="Bad")

    def test_import_empty_mappings(self, sample_workflow_json: bytes):
        result = import_workflow(sample_workflow_json, name="Test")
        assert result["parameter_mapping"] == {}
        assert result["output_mapping"] == []
