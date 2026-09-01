"""
Dependency checking against a live ComfyUI instance.

Takes the inventory produced by ``workflow_analysis`` and confirms, against
``GET /object_info``, that the instance can actually run it: every node class
is registered, and every model file the workflow names is installed.

Both checks read the catalogue generically. Node classes are its top-level
keys. Model files are gathered from every COMBO option list in it, because
that is how ComfyUI advertises the files each loader can see - so a new loader
node contributes its files without this module knowing the node exists.
"""

from dataclasses import dataclass, field
from typing import Any

from app.services.workflow_analysis import WorkflowAnalysis
from app.services.workflow_format import FRONTEND_ONLY_NODE_TYPES

# Extensions that mark a catalogue entry as a model file rather than an
# ordinary enum value such as "euler" or "normal".
MODEL_SUFFIXES = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx")


@dataclass
class DependencyReport:
    """Whether a live instance can run the analysed workflow."""

    #: False when the catalogue was unavailable, so nothing could be checked.
    checked: bool = False
    reason: str = ""

    node_classes_present: list[str] = field(default_factory=list)
    node_classes_missing: list[str] = field(default_factory=list)
    #: Editor-only types, reported separately so they never read as missing.
    node_classes_frontend_only: list[str] = field(default_factory=list)

    models_present: list[str] = field(default_factory=list)
    models_missing: list[str] = field(default_factory=list)

    #: Total node classes registered on the instance.
    catalogue_size: int = 0

    @property
    def satisfied(self) -> bool:
        """True when the instance has everything the workflow needs."""
        return (
            self.checked
            and not self.node_classes_missing
            and not self.models_missing
        )

    def summary(self) -> str:
        if not self.checked:
            return f"Dependencies not checked: {self.reason}"
        if self.satisfied:
            return (
                f"All {len(self.node_classes_present)} node class(es) and "
                f"{len(self.models_present)} model file(s) are available."
            )
        parts = []
        if self.node_classes_missing:
            parts.append(
                f"{len(self.node_classes_missing)} missing node class(es): "
                + ", ".join(self.node_classes_missing)
            )
        if self.models_missing:
            parts.append(
                f"{len(self.models_missing)} missing model file(s): "
                + ", ".join(self.models_missing)
            )
        return "; ".join(parts)


def known_model_files(object_info: dict[str, Any]) -> set[str]:
    """
    Every model filename the instance advertises across all loader nodes.

    ComfyUI describes a combo input as ``[[option, ...], {...}]``, so each
    option list is scanned and entries that look like model files are kept.
    """
    found: set[str] = set()

    for node_spec in object_info.values():
        if not isinstance(node_spec, dict):
            continue
        inputs = node_spec.get("input")
        if not isinstance(inputs, dict):
            continue
        for section in ("required", "optional"):
            fields = inputs.get(section)
            if not isinstance(fields, dict):
                continue
            for spec in fields.values():
                if not isinstance(spec, list) or not spec:
                    continue
                options = spec[0]
                if not isinstance(options, list):
                    continue
                for option in options:
                    if isinstance(option, str) and option.lower().endswith(MODEL_SUFFIXES):
                        found.add(option)

    return found


def check_dependencies(
    analysis: WorkflowAnalysis,
    object_info: dict[str, Any] | None,
) -> DependencyReport:
    """
    Check an analysed workflow against a ComfyUI node catalogue.

    Parameters
    ----------
    analysis : WorkflowAnalysis
        Inventory from ``workflow_analysis``.
    object_info : dict or None
        The parsed ``/object_info`` response, or None when it could not be
        fetched (offline instance, or a provider with no catalogue such as the
        mock). None yields an unchecked report rather than a failing one -
        absence of evidence is not evidence of absence.
    """
    report = DependencyReport(
        node_classes_frontend_only=list(analysis.frontend_only_node_classes),
    )

    if not object_info:
        report.reason = (
            "The ComfyUI node catalogue (/object_info) was unavailable, so "
            "node and model availability could not be verified."
        )
        return report

    report.checked = True
    report.catalogue_size = len(object_info)

    for node_class in analysis.required_node_classes:
        if node_class in FRONTEND_ONLY_NODE_TYPES:
            continue
        if node_class in object_info:
            report.node_classes_present.append(node_class)
        else:
            report.node_classes_missing.append(node_class)

    installed = known_model_files(object_info)
    for model in analysis.required_models:
        if model in installed:
            report.models_present.append(model)
        else:
            report.models_missing.append(model)

    report.node_classes_present.sort()
    report.node_classes_missing.sort()
    report.models_present.sort()
    report.models_missing.sort()
    return report
