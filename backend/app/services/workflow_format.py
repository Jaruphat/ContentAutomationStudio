"""
ComfyUI workflow format detection.

ComfyUI stores two different JSON shapes and they are easy to confuse:

* **UI (graph) format** - what "Save"/"Export" writes and what lives in
  ``ComfyUI/user/default/workflows``. A ``nodes`` array of visual nodes with
  ``widgets_values``, a ``links`` array, and optional ``definitions.subgraphs``.
  The editor needs this; the server cannot execute it.

* **API (prompt) format** - what "Export (API)" writes and the only shape
  ``POST /prompt`` accepts. A flat object keyed by node id, each entry carrying
  ``class_type`` and an ``inputs`` dict, with subgraphs already flattened and
  widget values resolved to named inputs.

Submitting UI JSON to ``/prompt`` fails, and it fails confusingly, so this
module identifies the shape up front and explains what it found. Detection is
structural - no node ids, class names or workflow specifics are hardcoded.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowFormat(str, Enum):
    """Which of ComfyUI's two JSON shapes a file is."""

    #: Flat ``{node_id: {class_type, inputs}}`` - submittable to /prompt.
    API = "api"
    #: Graph/editor format with ``nodes`` and ``links`` - NOT submittable.
    UI = "ui"
    #: Parsed as JSON but matches neither shape.
    UNKNOWN = "unknown"


@dataclass
class FormatDetection:
    """What the detector concluded and why."""

    format: WorkflowFormat
    #: 0.0-1.0. Below 1.0 means the shape was only partially matched.
    confidence: float
    #: Human-readable observations supporting the verdict.
    reasons: list[str] = field(default_factory=list)
    #: Structural counts, useful for diagnostics and tests.
    indicators: dict[str, Any] = field(default_factory=dict)

    @property
    def is_submittable(self) -> bool:
        """Whether this shape may be sent to ComfyUI's /prompt endpoint."""
        return self.format is WorkflowFormat.API

    @property
    def uses_subgraphs(self) -> bool:
        return bool(self.indicators.get("subgraph_count"))


# Node types the editor renders but the server never executes. They are absent
# from /object_info by design, so a dependency check must not flag them.
FRONTEND_ONLY_NODE_TYPES: frozenset[str] = frozenset({
    "MarkdownNote",
    "Note",
    "Reroute",
    "PrimitiveNode",
})


def _looks_like_api_entry(value: Any) -> bool:
    """True if a value has the shape of an API-format node entry."""
    return isinstance(value, dict) and "class_type" in value


def detect_format(data: Any) -> FormatDetection:
    """
    Classify a parsed workflow JSON document.

    Parameters
    ----------
    data : Any
        The already-parsed JSON. Must be a dict to be either known format.

    Returns
    -------
    FormatDetection
        The verdict, a confidence score, the observations behind it, and
        structural counts.
    """
    if not isinstance(data, dict):
        return FormatDetection(
            format=WorkflowFormat.UNKNOWN,
            confidence=1.0,
            reasons=[
                f"Top level is {type(data).__name__}, but a ComfyUI workflow "
                f"is always a JSON object."
            ],
        )

    if not data:
        return FormatDetection(
            format=WorkflowFormat.UNKNOWN,
            confidence=1.0,
            reasons=["The document is an empty object."],
        )

    # -- UI markers ------------------------------------------------------
    nodes = data.get("nodes")
    has_node_array = isinstance(nodes, list)
    has_links = isinstance(data.get("links"), list)
    ui_only_keys = [
        k for k in ("last_node_id", "last_link_id", "groups", "extra", "revision")
        if k in data
    ]
    subgraphs = (data.get("definitions") or {}).get("subgraphs")
    subgraph_count = len(subgraphs) if isinstance(subgraphs, list) else 0

    # -- API markers -----------------------------------------------------
    # Every value of an API document is a node entry keyed by node id.
    api_entries = [v for v in data.values() if _looks_like_api_entry(v)]
    api_ratio = len(api_entries) / len(data) if data else 0.0

    indicators: dict[str, Any] = {
        "top_level_keys": sorted(data.keys())[:20],
        "node_array_count": len(nodes) if has_node_array else 0,
        "link_count": len(data["links"]) if has_links else 0,
        "subgraph_count": subgraph_count,
        "api_entry_count": len(api_entries),
        "api_entry_ratio": round(api_ratio, 3),
        "ui_only_keys": ui_only_keys,
    }

    # A UI document is unambiguous: a nodes array plus editor-only keys.
    if has_node_array:
        reasons = [
            f"Contains a top-level 'nodes' array with {len(nodes)} node(s), "
            f"which is the editor graph format.",
        ]
        if has_links:
            reasons.append(
                f"Contains a top-level 'links' array with "
                f"{indicators['link_count']} link(s)."
            )
        if ui_only_keys:
            reasons.append(
                f"Carries editor-only key(s): {', '.join(ui_only_keys)}."
            )
        if subgraph_count:
            reasons.append(
                f"Defines {subgraph_count} subgraph(s) under "
                f"'definitions.subgraphs'. ComfyUI flattens these during API "
                f"export, so the executable graph differs structurally from "
                f"this file."
            )
        reasons.append(
            "This shape cannot be submitted to /prompt. Export the API format "
            "from ComfyUI (Workflow -> Export (API)) to run it."
        )
        return FormatDetection(
            format=WorkflowFormat.UI,
            confidence=1.0 if (has_links or ui_only_keys) else 0.8,
            reasons=reasons,
            indicators=indicators,
        )

    # An API document has every value carrying class_type.
    if api_entries and api_ratio >= 0.9:
        return FormatDetection(
            format=WorkflowFormat.API,
            confidence=1.0 if api_ratio == 1.0 else 0.9,
            reasons=[
                f"All {len(api_entries)} top-level entries carry 'class_type', "
                f"which is the API prompt format.",
                "This shape can be submitted to /prompt.",
            ],
            indicators=indicators,
        )

    # Partial match: some entries look right, others do not.
    if api_entries:
        stray = [
            k for k, v in data.items() if not _looks_like_api_entry(v)
        ][:10]
        return FormatDetection(
            format=WorkflowFormat.UNKNOWN,
            confidence=0.5,
            reasons=[
                f"{len(api_entries)} of {len(data)} top-level entries carry "
                f"'class_type', so this resembles API format but is not "
                f"consistent.",
                f"Entries without 'class_type': {', '.join(stray)}",
                "It may be a hand-edited or truncated export.",
            ],
            indicators=indicators,
        )

    return FormatDetection(
        format=WorkflowFormat.UNKNOWN,
        confidence=1.0,
        reasons=[
            "No 'nodes' array (editor format) and no entries carrying "
            "'class_type' (API format).",
            f"Top-level keys seen: {', '.join(sorted(data.keys())[:10])}",
        ],
        indicators=indicators,
    )
