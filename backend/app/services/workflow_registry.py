"""
Workflow Registry Service.

Handles:
  - Import and parse ComfyUI API-format workflow JSON files.
  - Compute SHA-256 hash of workflow content for versioning.
  - Detect whether an import is API-format or editor/UI-format.
  - Validate that parameter/output mappings reference real nodes/fields.
  - Apply parameter mapping to produce a ready-to-submit payload.
"""

import hashlib
import json
import os
import uuid
from typing import Any

from app import paths
from app.services.workflow_format import WorkflowFormat, detect_format


def compute_sha256(content: bytes) -> str:
    """Return hex-digest SHA-256 of raw bytes."""
    return hashlib.sha256(content).hexdigest()


def parse_workflow_json(raw_bytes: bytes) -> dict[str, Any]:
    """
    Parse raw bytes as JSON and return the workflow dict.

    Raises ValueError if parsing fails.
    """
    try:
        data = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Workflow JSON must be a JSON object at the top level")
    return data


def save_workflow_source(raw_bytes: bytes, workflow_id: str, name: str) -> str:
    """
    Persist the raw workflow JSON to the workflows directory.

    Returns the absolute path to the saved file.
    """
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    filename = f"{workflow_id}_{safe_name}.json"
    dest = os.path.join(paths.workflows_dir(), filename)
    with open(dest, "wb") as f:
        f.write(raw_bytes)
    return dest


def extract_node_ids(workflow_data: dict[str, Any]) -> set[str]:
    """Return the set of node IDs present in the workflow JSON."""
    return set(workflow_data.keys())


def extract_node_field_names(workflow_data: dict[str, Any], node_id: str) -> set[str]:
    """
    Return the set of input field names for a given node.

    ComfyUI API-format has structure:
        { "nodeId": { "inputs": { "field": value, ... }, "class_type": "..." } }
    """
    node = workflow_data.get(node_id, {})
    inputs = node.get("inputs", {})
    if isinstance(inputs, dict):
        return set(inputs.keys())
    return set()


def validate_mapping(
    workflow_data: dict[str, Any],
    parameter_mapping: dict[str, Any],
    output_mapping: list[dict[str, Any]],
) -> tuple[bool, list[str], list[str]]:
    """
    Validate that mapped node IDs and fields exist in the workflow JSON.

    Parameters
    ----------
    workflow_data : dict
        Parsed workflow JSON.
    parameter_mapping : dict
        Mapping of logical names to {"nodeId": "...", "field": "..."}.
    output_mapping : list[dict]
        List of {"nodeId": "...", "type": "..."}.

    Returns
    -------
    tuple of (is_valid, errors, warnings)
    """
    node_ids = extract_node_ids(workflow_data)
    errors: list[str] = []
    warnings: list[str] = []

    # Validate parameter mapping
    for logical_name, mapping in parameter_mapping.items():
        if not isinstance(mapping, dict):
            errors.append(f"Parameter '{logical_name}': mapping must be a dict, got {type(mapping).__name__}")
            continue

        node_id = mapping.get("nodeId", "")
        field_name = mapping.get("field", "")

        if not node_id:
            errors.append(f"Parameter '{logical_name}': missing 'nodeId'")
            continue
        if not field_name:
            errors.append(f"Parameter '{logical_name}': missing 'field'")
            continue

        if str(node_id) not in node_ids:
            errors.append(
                f"Parameter '{logical_name}': nodeId '{node_id}' not found in workflow. "
                f"Available nodes: {sorted(node_ids)[:20]}"
            )
            continue

        fields = extract_node_field_names(workflow_data, str(node_id))
        if field_name not in fields:
            errors.append(
                f"Parameter '{logical_name}': field '{field_name}' not found in node '{node_id}'. "
                f"Available fields: {sorted(fields)}"
            )

    # Validate output mapping
    for idx, out in enumerate(output_mapping):
        if not isinstance(out, dict):
            errors.append(f"Output mapping [{idx}]: must be a dict")
            continue
        node_id = out.get("nodeId", "")
        if not node_id:
            errors.append(f"Output mapping [{idx}]: missing 'nodeId'")
            continue
        if str(node_id) not in node_ids:
            errors.append(
                f"Output mapping [{idx}]: nodeId '{node_id}' not found in workflow"
            )

    is_valid = len(errors) == 0

    if not parameter_mapping:
        warnings.append("No parameter mappings defined; workflow will be submitted as-is")
    if not output_mapping:
        warnings.append("No output mappings defined; output retrieval may fail")

    return is_valid, errors, warnings


def apply_parameter_mapping(
    workflow_data: dict[str, Any],
    parameter_mapping: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply parameter values to a copy of the workflow JSON using the mapping.

    Parameters
    ----------
    workflow_data : dict
        Original parsed workflow JSON.
    parameter_mapping : dict
        Mapping of logical names to {"nodeId": "...", "field": "..."}.
    values : dict
        Logical name to value, e.g. {"positivePrompt": "a cat", "seed": 42}.

    Returns
    -------
    dict
        A deep copy of workflow_data with mapped values injected.
    """
    import copy

    payload = copy.deepcopy(workflow_data)

    for logical_name, value in values.items():
        mapping = parameter_mapping.get(logical_name)
        if mapping is None:
            continue
        node_id = str(mapping.get("nodeId", ""))
        field_name = mapping.get("field", "")
        if not node_id or not field_name:
            continue

        if node_id in payload:
            if "inputs" not in payload[node_id]:
                payload[node_id]["inputs"] = {}
            payload[node_id]["inputs"][field_name] = value

    return payload


def import_workflow(
    raw_bytes: bytes,
    name: str,
    purpose: str = "image",
    version: str = "1.0",
    required_models: list[str] | None = None,
    required_custom_nodes: list[str] | None = None,
    tested_comfyui_version: str = "",
) -> dict[str, Any]:
    """
    Full import pipeline: parse, hash, save, and return record fields.

    Returns a dict suitable for constructing a Workflow ORM model.
    """
    data = parse_workflow_json(raw_bytes)  # Validate JSON before saving
    detection = detect_format(data)

    sha256 = compute_sha256(raw_bytes)
    workflow_id = str(uuid.uuid4())
    source_path = save_workflow_source(raw_bytes, workflow_id, name)

    # A non-API shape is stored so it can be inspected, but it is marked
    # unsupported rather than pending: no amount of mapping makes an editor
    # graph submittable to /prompt.
    validation_status = (
        "pending" if detection.format is WorkflowFormat.API else "unsupported_format"
    )

    return {
        "id": workflow_id,
        "name": name,
        "purpose": purpose,
        "source_json_path": source_path,
        "source_format": detection.format.value,
        "sha256_hash": sha256,
        "version": version,
        "required_models": required_models or [],
        "required_custom_nodes": required_custom_nodes or [],
        "parameter_mapping": {},
        "output_mapping": [],
        "tested_comfyui_version": tested_comfyui_version,
        "validation_status": validation_status,
    }


def load_workflow_source(source_json_path: str) -> dict[str, Any]:
    """Load and parse a previously saved workflow JSON file."""
    if not os.path.isfile(source_json_path):
        raise FileNotFoundError(f"Workflow source not found: {source_json_path}")
    with open(source_json_path, "rb") as f:
        return parse_workflow_json(f.read())
