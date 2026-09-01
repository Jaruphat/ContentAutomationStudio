"""
Workflow analysis and mapping suggestion.

Two jobs, both driven by structure rather than by any particular workflow:

1. **Inventory.** Walk a workflow - including the inner nodes of any subgraph -
   and report the node classes it executes and the model files it names. This
   is what a dependency check against ``/object_info`` needs.

2. **Candidate logical mappings.** Propose which node input each of our logical
   fields (positive prompt, seed, width, ...) should drive. Proposals come from
   generic input-name and type heuristics, so no node id, class name or
   workflow of any vendor is hardcoded. A proposal is a starting point for the
   workflow mapper UI, never an automatic binding.

For a UI-format file the proposals name a *node class and input*, because UI
node ids are renumbered when ComfyUI exports the API format. For an API-format
file they name the concrete ``nodeId``/``field`` pair our mapping uses.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.services import job_payload
from app.services.workflow_format import (
    FRONTEND_ONLY_NODE_TYPES,
    WorkflowFormat,
    detect_format,
)

# A ComfyUI subgraph node's "type" is the subgraph definition's UUID.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Extensions that indicate a widget value names a model file on disk.
_MODEL_SUFFIXES = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx")

# The virtual node id ComfyUI gives a subgraph's input boundary.
_SUBGRAPH_INPUT_NODE_ID = -10


# ---------------------------------------------------------------------------
# Logical field heuristics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldHeuristic:
    """How to recognise the input that should carry one logical field."""

    logical_field: str
    #: Input names that map exactly, best first.
    exact_names: tuple[str, ...]
    #: Substrings that suggest a match when no exact name is found.
    partial_names: tuple[str, ...] = ()
    #: Acceptable declared input types; empty means any.
    types: tuple[str, ...] = ()
    #: Input names that must never be chosen for this field.
    excluded_names: tuple[str, ...] = ()


# Ordered so more specific fields claim their input before looser ones.
FIELD_HEURISTICS: tuple[FieldHeuristic, ...] = (
    FieldHeuristic(
        logical_field=job_payload.NEGATIVE_PROMPT,
        exact_names=("negative_prompt", "negative", "negative_text"),
        partial_names=("negative",),
        types=("STRING",),
    ),
    FieldHeuristic(
        logical_field=job_payload.POSITIVE_PROMPT,
        exact_names=("prompt", "positive_prompt", "text", "positive"),
        partial_names=("prompt",),
        types=("STRING",),
        excluded_names=("negative_prompt", "negative", "negative_text"),
    ),
    FieldHeuristic(
        logical_field=job_payload.SEED,
        exact_names=("seed", "noise_seed"),
        partial_names=("seed",),
        types=("INT",),
    ),
    FieldHeuristic(
        logical_field=job_payload.WIDTH,
        exact_names=("width",),
        types=("INT",),
    ),
    FieldHeuristic(
        logical_field=job_payload.HEIGHT,
        exact_names=("height",),
        types=("INT",),
    ),
    FieldHeuristic(
        logical_field=job_payload.FRAMES,
        exact_names=("length", "num_frames", "frames", "video_frames", "frame_count"),
        partial_names=("frame",),
        types=("INT",),
        excluded_names=("frame_rate", "fps", "frame_load_cap"),
    ),
    FieldHeuristic(
        logical_field=job_payload.REFERENCE_IMAGE,
        exact_names=("first_frame", "start_image", "reference_image", "image", "images"),
        partial_names=("image",),
        types=("IMAGE", "COMFY_AUTOGROW_V3", "COMBO"),
        excluded_names=("last_frame", "end_image", "mask"),
    ),
    FieldHeuristic(
        logical_field=job_payload.OUTPUT_PREFIX,
        exact_names=("filename_prefix",),
        partial_names=("filename",),
        types=("STRING",),
    ),
)


@dataclass
class MappingCandidate:
    """A proposed binding for one logical field."""

    logical_field: str
    node_class: str
    input_name: str
    #: Concrete node id, when analysing an API-format workflow.
    node_id: str | None = None
    #: 'exact-name' or 'partial-name'.
    match_kind: str = "exact-name"
    confidence: float = 1.0
    note: str = ""
    #: False when the input exists inside a subgraph but is not promoted to
    #: its interface. Such an input is only addressable after ComfyUI's API
    #: export flattens the subgraph.
    exposed: bool = True
    #: Whether this may be applied without a human confirming it. False for a
    #: proposal that would overwrite a value the graph computes - replacing a
    #: formula with a constant silently changes what the workflow does.
    auto_applicable: bool = True

    def as_mapping_entry(self) -> dict[str, str] | None:
        """The ``{"nodeId": ..., "field": ...}`` our registry stores."""
        if self.node_id is None:
            return None
        return {"nodeId": self.node_id, "field": self.input_name}


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@dataclass
class NodeRef:
    """One executable node found anywhere in a workflow."""

    node_id: str
    node_class: str
    #: "" for the top level, else the subgraph name it lives in.
    container: str = ""
    widgets: list[Any] = field(default_factory=list)


@dataclass
class SubgraphInfo:
    """A subgraph definition and how its interface reaches inner nodes."""

    subgraph_id: str
    name: str
    #: Interface input name -> where it lands, e.g.
    #: ``{"prompt": {"node_class": "MiniMaxH3ImageToVideo", "input_name": "prompt"}}``
    input_bindings: dict[str, dict[str, Any]] = field(default_factory=dict)
    inner_node_classes: list[str] = field(default_factory=list)
    unresolved_inputs: list[str] = field(default_factory=list)


@dataclass
class WorkflowAnalysis:
    """Everything we can say about a workflow without executing it."""

    format: WorkflowFormat
    format_confidence: float
    format_reasons: list[str] = field(default_factory=list)
    submittable: bool = False

    nodes: list[NodeRef] = field(default_factory=list)
    subgraphs: list[SubgraphInfo] = field(default_factory=list)
    #: Executable node classes, excluding editor-only ones.
    required_node_classes: list[str] = field(default_factory=list)
    #: Node classes present only in the editor (notes, reroutes).
    frontend_only_node_classes: list[str] = field(default_factory=list)
    #: Model filenames named by widget values.
    required_models: list[str] = field(default_factory=list)
    #: Best candidate per logical field.
    mapping_candidates: list[MappingCandidate] = field(default_factory=list)
    #: Runner-up candidates, kept so the mapper UI can offer alternatives.
    alternate_candidates: list[MappingCandidate] = field(default_factory=list)
    #: Logical fields no candidate was found for.
    unmapped_logical_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_subgraph_type(node_type: str) -> bool:
    return bool(_UUID_RE.match(node_type or ""))


def _collect_models(widgets: Any) -> list[str]:
    """Widget values that name a model file."""
    found: list[str] = []
    if isinstance(widgets, list):
        for value in widgets:
            if isinstance(value, str) and value.lower().endswith(_MODEL_SUFFIXES):
                found.append(value)
    return found


def _input_type_of(node: dict[str, Any], input_name: str) -> str:
    for spec in node.get("inputs", []) or []:
        if spec.get("name") == input_name:
            return str(spec.get("type") or "")
    return ""


def _match_heuristic(
    heuristic: FieldHeuristic, input_name: str, input_type: str
) -> tuple[bool, str, float]:
    """Test one input against one heuristic. Returns (matched, kind, score)."""
    name = (input_name or "").lower()
    if not name:
        return False, "", 0.0

    # ComfyUI names an autogrow/dynamic input "<group>.<slot>", e.g.
    # "images.image_1" or "format.codec". The group is the meaningful part.
    base_name = name.split(".", 1)[0]

    if name in heuristic.excluded_names or base_name in heuristic.excluded_names:
        return False, "", 0.0

    if heuristic.types:
        # An untyped input still qualifies; a wrongly typed one does not.
        if input_type and input_type.upper() not in heuristic.types:
            return False, "", 0.0

    for candidate_name, penalty in ((name, 0.0), (base_name, 0.02)):
        if candidate_name in heuristic.exact_names:
            # Earlier entries in exact_names are stronger signals.
            rank = heuristic.exact_names.index(candidate_name)
            return True, "exact-name", 1.0 - (rank * 0.05) - penalty

    for fragment in heuristic.partial_names:
        if fragment in name:
            return True, "partial-name", 0.6

    return False, "", 0.0


# ---------------------------------------------------------------------------
# UI-format analysis
# ---------------------------------------------------------------------------

def _analyse_subgraph(
    definition: dict[str, Any],
) -> tuple[SubgraphInfo, list[NodeRef], list[MappingCandidate]]:
    """Inventory a subgraph and trace its interface inputs to inner nodes."""
    name = str(definition.get("name") or definition.get("id") or "subgraph")
    info = SubgraphInfo(
        subgraph_id=str(definition.get("id") or ""),
        name=name,
    )

    inner_nodes = definition.get("nodes") or []
    by_id = {n.get("id"): n for n in inner_nodes if isinstance(n, dict)}

    node_refs: list[NodeRef] = []
    for node in inner_nodes:
        if not isinstance(node, dict):
            continue
        node_class = str(node.get("type") or "")
        node_refs.append(NodeRef(
            node_id=str(node.get("id")),
            node_class=node_class,
            container=name,
            widgets=node.get("widgets_values") or [],
        ))
        info.inner_node_classes.append(node_class)

    # The interface input at index i is driven by links whose origin is the
    # virtual input node (-10) on slot i.
    interface_inputs = definition.get("inputs") or []
    candidates: list[MappingCandidate] = []

    for slot, iface in enumerate(interface_inputs):
        if not isinstance(iface, dict):
            continue
        iface_name = str(iface.get("name") or "")
        targets = [
            link for link in (definition.get("links") or [])
            if isinstance(link, dict)
            and link.get("origin_id") == _SUBGRAPH_INPUT_NODE_ID
            and link.get("origin_slot") == slot
        ]
        if not targets:
            info.unresolved_inputs.append(iface_name)
            continue

        link = targets[0]
        inner = by_id.get(link.get("target_id"))
        if inner is None:
            info.unresolved_inputs.append(iface_name)
            continue

        inner_class = str(inner.get("type") or "")
        inner_inputs = inner.get("inputs") or []
        target_slot = link.get("target_slot")
        inner_input_name = ""
        if isinstance(target_slot, int) and 0 <= target_slot < len(inner_inputs):
            inner_input_name = str(inner_inputs[target_slot].get("name") or "")

        info.input_bindings[iface_name] = {
            "node_class": inner_class,
            "node_id": str(inner.get("id")),
            "input_name": inner_input_name,
            "declared_type": str(iface.get("type") or ""),
        }

        # Propose a logical field for this interface input. The interface name
        # is the better signal: it is what the workflow author chose to expose.
        for heuristic in FIELD_HEURISTICS:
            matched, kind, score = _match_heuristic(
                heuristic, iface_name, str(iface.get("type") or "")
            )
            if not matched:
                continue
            candidates.append(MappingCandidate(
                logical_field=heuristic.logical_field,
                node_class=inner_class,
                input_name=inner_input_name or iface_name,
                match_kind=kind,
                confidence=score,
                exposed=True,
                note=(
                    f"Subgraph '{name}' exposes '{iface_name}', which drives "
                    f"the '{inner_input_name}' input of {inner_class}."
                ),
            ))
            break

    # Inner inputs the subgraph does not promote are still worth reporting:
    # after ComfyUI's API export flattens the subgraph they become directly
    # addressable, and a field like a negative prompt is often only reachable
    # this way.
    exposed_targets = {
        (b["node_id"], b["input_name"]) for b in info.input_bindings.values()
    }
    for node in inner_nodes:
        if not isinstance(node, dict):
            continue
        inner_class = str(node.get("type") or "")
        for spec in node.get("inputs", []) or []:
            input_name = str(spec.get("name") or "")
            if (str(node.get("id")), input_name) in exposed_targets:
                continue
            input_type = str(spec.get("type") or "")
            for heuristic in FIELD_HEURISTICS:
                matched, kind, score = _match_heuristic(
                    heuristic, input_name, input_type
                )
                if not matched:
                    continue
                candidates.append(MappingCandidate(
                    logical_field=heuristic.logical_field,
                    node_class=inner_class,
                    input_name=input_name,
                    match_kind=kind,
                    # Ranked below anything the subgraph actually exposes.
                    confidence=score * 0.5,
                    exposed=False,
                    note=(
                        f"Inside subgraph '{name}': {inner_class} has an "
                        f"'{input_name}' input that the subgraph does not "
                        f"expose. Addressable after API export."
                    ),
                ))
                break

    return info, node_refs, candidates


def analyze_ui_workflow(data: dict[str, Any]) -> WorkflowAnalysis:
    """Inventory a UI-format workflow and propose logical mappings."""
    detection = detect_format(data)
    analysis = WorkflowAnalysis(
        format=detection.format,
        format_confidence=detection.confidence,
        format_reasons=list(detection.reasons),
        submittable=detection.is_submittable,
    )

    subgraph_defs = {
        str(sg.get("id")): sg
        for sg in ((data.get("definitions") or {}).get("subgraphs") or [])
        if isinstance(sg, dict)
    }

    candidates: list[MappingCandidate] = []

    for node in data.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        node_class = str(node.get("type") or "")
        widgets = node.get("widgets_values") or []

        if _is_subgraph_type(node_class):
            definition = subgraph_defs.get(node_class)
            if definition is None:
                analysis.warnings.append(
                    f"Node {node.get('id')} references subgraph "
                    f"{node_class}, which is not defined in this file."
                )
                continue
            info, inner_refs, inner_candidates = _analyse_subgraph(definition)
            analysis.subgraphs.append(info)
            analysis.nodes.extend(inner_refs)
            candidates.extend(inner_candidates)
            continue

        analysis.nodes.append(NodeRef(
            node_id=str(node.get("id")),
            node_class=node_class,
            widgets=widgets,
        ))

        # Top-level nodes can also carry mappable inputs (e.g. an output
        # prefix on a save node).
        for spec in node.get("inputs", []) or []:
            input_name = str(spec.get("name") or "")
            input_type = str(spec.get("type") or "")
            for heuristic in FIELD_HEURISTICS:
                matched, kind, score = _match_heuristic(
                    heuristic, input_name, input_type
                )
                if not matched:
                    continue
                candidates.append(MappingCandidate(
                    logical_field=heuristic.logical_field,
                    node_class=node_class,
                    input_name=input_name,
                    match_kind=kind,
                    # Top-level matches rank below subgraph interface matches.
                    confidence=score * 0.9,
                    note=f"Top-level {node_class} node input '{input_name}'.",
                ))
                break

    _finalise(analysis, candidates)
    return analysis


# ---------------------------------------------------------------------------
# API-format analysis
# ---------------------------------------------------------------------------

def analyze_api_workflow(data: dict[str, Any]) -> WorkflowAnalysis:
    """Inventory an API-format workflow and propose concrete node mappings."""
    detection = detect_format(data)
    analysis = WorkflowAnalysis(
        format=detection.format,
        format_confidence=detection.confidence,
        format_reasons=list(detection.reasons),
        submittable=detection.is_submittable,
    )

    candidates: list[MappingCandidate] = []
    wired_notes: list[str] = []

    for node_id, entry in data.items():
        if not isinstance(entry, dict) or "class_type" not in entry:
            continue
        node_class = str(entry.get("class_type") or "")
        inputs = entry.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue

        analysis.nodes.append(NodeRef(
            node_id=str(node_id),
            node_class=node_class,
            widgets=[v for v in inputs.values() if not isinstance(v, list)],
        ))

        for input_name, value in inputs.items():
            if isinstance(value, list):
                # A list value is a wire from another node, so this input has
                # no settable widget. Writing to it would be silently ignored
                # by ComfyUI, which executes the link instead. Follow one hop
                # upstream and offer the driving node's own widgets, so the
                # field stays reachable.
                candidates.extend(_upstream_candidates(
                    data, node_class, str(node_id), str(input_name), value,
                    wired_notes,
                ))
                continue
            declared_type = {
                str: "STRING", int: "INT", float: "FLOAT", bool: "BOOLEAN",
            }.get(type(value), "")
            for heuristic in FIELD_HEURISTICS:
                matched, kind, score = _match_heuristic(
                    heuristic, str(input_name), declared_type
                )
                if not matched:
                    continue
                candidates.append(MappingCandidate(
                    logical_field=heuristic.logical_field,
                    node_class=node_class,
                    input_name=str(input_name),
                    node_id=str(node_id),
                    match_kind=kind,
                    confidence=score,
                    note=f"{node_class} node {node_id}, input '{input_name}'.",
                ))
                break

    _finalise(analysis, candidates)
    analysis.warnings.extend(wired_notes)
    return analysis


def _upstream_candidates(
    data: dict[str, Any],
    node_class: str,
    node_id: str,
    input_name: str,
    link: list[Any],
    unresolved: list[str],
) -> list[MappingCandidate]:
    """
    Offer the widgets of the node driving a linked input.

    When a logical field's natural target turns out to be wired rather than
    settable - a video node's ``width`` fed by a resolution helper, or its
    ``length`` fed by a math expression - the field is still controllable, just
    one node further upstream. Those proposals are returned marked
    ``exposed=False`` so they rank below a direct hit and read clearly as
    "set this instead".
    """
    if not link or not isinstance(link[0], (str, int)):
        return []
    source_id = str(link[0])
    source = data.get(source_id)
    if not isinstance(source, dict):
        return []
    source_class = str(source.get("class_type") or "")
    source_inputs = source.get("inputs") or {}
    if not isinstance(source_inputs, dict):
        return []

    # Which logical field was this linked input standing in for? Attribution
    # is exact-name only here: the declared type is unavailable for a linked
    # input, so a loose substring match would misfile inputs such as
    # 'first_frame' (a reference image) under 'frames' (a frame count).
    name = input_name.lower()
    base_name = name.split(".", 1)[0]
    logical_field = next(
        (
            h.logical_field for h in FIELD_HEURISTICS
            if name in h.exact_names or base_name in h.exact_names
        ),
        None,
    )
    if logical_field is None:
        return []

    settable = {
        name: value for name, value in source_inputs.items()
        if not isinstance(value, list)
    }
    if not settable:
        return []

    heuristic = next(
        (h for h in FIELD_HEURISTICS if h.logical_field == logical_field), None
    )

    # A source whose own inputs are all settable is a leaf: it holds a value
    # rather than deriving one, so writing to it is safe. A source with
    # incoming links computes its output from them - overwriting that widget
    # (a math expression, say) would silently change the graph's behaviour, so
    # it is proposed for review but never auto-applied.
    source_is_leaf = not any(
        isinstance(v, list) for v in source_inputs.values()
    )

    found: list[MappingCandidate] = []
    for widget_name, value in settable.items():
        declared_type = {
            str: "STRING", int: "INT", float: "FLOAT", bool: "BOOLEAN",
        }.get(type(value), "")
        # Prefer a widget matching the same field; otherwise accept the
        # driving node's single settable value.
        direct = heuristic is not None and _match_heuristic(
            heuristic, widget_name, declared_type
        )[0]
        generic = len(settable) == 1
        if not (direct or generic):
            continue
        found.append(MappingCandidate(
            logical_field=logical_field,
            node_class=source_class,
            input_name=widget_name,
            node_id=source_id,
            match_kind="upstream-widget",
            confidence=0.45 if direct else 0.35,
            exposed=False,
            auto_applicable=source_is_leaf,
            note=(
                f"{node_class} node {node_id} has '{input_name}' wired from "
                f"{source_class} node {source_id}, so it cannot be set "
                f"directly. Set '{widget_name}' on that node instead, or "
                f"detach the link in ComfyUI and re-export."
            ),
        ))

    if not found:
        unresolved.append(
            f"'{logical_field}' would map to {node_class} node {node_id} input "
            f"'{input_name}', but that input is wired from {source_class} node "
            f"{source_id}, which exposes no matching widget "
            f"(has: {', '.join(sorted(settable)) or 'none'}). Drive it from "
            f"that node, or detach the link in ComfyUI and re-export."
        )
    return found


def analyze_workflow(data: dict[str, Any]) -> WorkflowAnalysis:
    """Analyse a workflow, dispatching on its detected format."""
    detection = detect_format(data)
    if detection.format is WorkflowFormat.API:
        return analyze_api_workflow(data)
    if detection.format is WorkflowFormat.UI:
        return analyze_ui_workflow(data)
    return WorkflowAnalysis(
        format=detection.format,
        format_confidence=detection.confidence,
        format_reasons=list(detection.reasons),
        submittable=False,
        warnings=["Unrecognised workflow shape; nothing could be analysed."],
    )


def _finalise(analysis: WorkflowAnalysis, candidates: list[MappingCandidate]) -> None:
    """Populate the derived summary fields on an analysis."""
    required: list[str] = []
    frontend_only: list[str] = []
    models: list[str] = []

    for ref in analysis.nodes:
        if not ref.node_class:
            continue
        if ref.node_class in FRONTEND_ONLY_NODE_TYPES:
            if ref.node_class not in frontend_only:
                frontend_only.append(ref.node_class)
            continue
        if ref.node_class not in required:
            required.append(ref.node_class)
        models.extend(_collect_models(ref.widgets))

    analysis.required_node_classes = sorted(required)
    analysis.frontend_only_node_classes = sorted(frontend_only)
    analysis.required_models = sorted(set(models))

    # Pick the strongest candidate per logical field. Selecting by confidence
    # rather than by encounter order keeps the result independent of how the
    # nodes happen to be ordered in the file.
    ranked = sorted(
        candidates,
        key=lambda c: (
            c.logical_field,
            -c.confidence,
            not c.exposed,          # exposed inputs win ties
            c.node_class,
            c.input_name,
        ),
    )
    best: dict[str, MappingCandidate] = {}
    alternates: list[MappingCandidate] = []
    for candidate in ranked:
        if candidate.logical_field in best:
            alternates.append(candidate)
        else:
            best[candidate.logical_field] = candidate

    analysis.mapping_candidates = sorted(
        best.values(), key=lambda c: (-c.confidence, c.logical_field)
    )
    analysis.alternate_candidates = alternates
    proposed = set(best)
    analysis.unmapped_logical_fields = [
        f for f in job_payload.LOGICAL_FIELDS if f not in proposed
    ]

    hidden_in_subgraph = sorted(
        c.logical_field for c in analysis.mapping_candidates
        if not c.exposed and c.match_kind != "upstream-widget"
    )
    if hidden_in_subgraph:
        analysis.warnings.append(
            "Candidate(s) for "
            + ", ".join(hidden_in_subgraph)
            + " sit inside a subgraph and are not promoted to its interface. "
            "They become directly addressable once ComfyUI's API export "
            "flattens the subgraph."
        )

    via_upstream = sorted(
        c.logical_field for c in analysis.mapping_candidates
        if c.match_kind == "upstream-widget"
    )
    if via_upstream:
        analysis.warnings.append(
            "Candidate(s) for "
            + ", ".join(via_upstream)
            + " target an input that is wired from another node, so the "
            "proposal drives the upstream node's widget instead. Confirm each "
            "one before generating."
        )

    needs_review = sorted(
        c.logical_field for c in analysis.mapping_candidates
        if not c.auto_applicable
    )
    if needs_review:
        analysis.warnings.append(
            "Candidate(s) for "
            + ", ".join(needs_review)
            + " would overwrite a value the graph computes, so they are "
            "excluded from the ready-to-apply mapping. Apply them by hand only "
            "if a constant is genuinely what you want there."
        )

    missing_required = [
        f for f in job_payload.REQUIRED_LOGICAL_FIELDS if f not in proposed
    ]
    if missing_required:
        analysis.warnings.append(
            "No candidate found for required logical field(s): "
            + ", ".join(missing_required)
            + ". These must be mapped by hand before generation."
        )


def suggested_parameter_mapping(analysis: WorkflowAnalysis) -> dict[str, dict[str, str]]:
    """
    Build a ``parameter_mapping`` from an API-format analysis.

    Returns an empty dict for UI-format analyses: their node ids are
    renumbered by ComfyUI's API export, so binding to them would be wrong.

    Candidates that would overwrite a computed value are excluded too; they
    stay in ``mapping_candidates`` for a human to review and apply.
    """
    mapping: dict[str, dict[str, str]] = {}
    for candidate in analysis.mapping_candidates:
        if not candidate.auto_applicable:
            continue
        entry = candidate.as_mapping_entry()
        if entry is not None:
            mapping[candidate.logical_field] = entry
    return mapping
