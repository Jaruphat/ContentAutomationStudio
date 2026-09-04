"""
Job Payload Builder.

Turns a persisted GenerationJob into a concrete ComfyUI API-format payload by
combining:

  1. the registered workflow's source JSON,
  2. the workflow's logical-field to node/field parameter mapping, and
  3. the job's logical parameter values (compiled prompt, seed, dimensions).

Business logic never references H3 node IDs. The only place node IDs appear is
the workflow record's ``parameter_mapping``, which is authored through the
workflow mapper UI and validated against the workflow JSON before use.

Each built payload is written to a snapshot file so a job stays reproducible
even if the registered workflow is later re-imported with different node IDs
(PRD sections 10.2/10.4, FR-11, NFR-10).

Only API-format workflows can produce a submittable payload. An editor/UI
graph is refused here rather than at the HTTP boundary, so no code path can
post one to /prompt.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import GenerationJob, Workflow
from app.services import workflow_registry
from app.services.workflow_format import WorkflowFormat

logger = logging.getLogger("cas.job_payload")


# Canonical logical field names. These are the keys used both in a workflow's
# parameter_mapping and in a job's parameter_map, so the two always line up.
# They mirror the adapter example in PRD section 10.2.
POSITIVE_PROMPT = "positivePrompt"
NEGATIVE_PROMPT = "negativePrompt"
SEED = "seed"
WIDTH = "width"
HEIGHT = "height"
FRAMES = "frames"
REFERENCE_IMAGE = "referenceImage"
ASPECT_RATIO = "aspectRatio"
OUTPUT_PREFIX = "outputPrefix"

#: The most reference inputs any node this project drives will accept. Boogu's
#: editor grows to sixteen; MiniMax H3's reference-to-video to nine; Qwen's
#: edit encoder to three. The ceiling is the largest of them, and what a given
#: run may actually use is read off that workflow's mapping, never assumed.
MAX_REFERENCE_IMAGES = 16


def reference_image_field(index: int) -> str:
    """Logical name of the nth reference slot, counting from zero.

    The first slot keeps the original ``referenceImage`` name so that every
    mapping already stored in the database, and every job already generated
    from one, keeps meaning what it meant.
    """
    return REFERENCE_IMAGE if index == 0 else f"{REFERENCE_IMAGE}{index + 1}"


REFERENCE_IMAGE_FIELDS: tuple[str, ...] = tuple(
    reference_image_field(i) for i in range(MAX_REFERENCE_IMAGES)
)


def reference_capacity(parameter_mapping: dict[str, Any] | None) -> int:
    """How many reference images this workflow can actually be given.

    Slots are filled in order, so the answer is the length of the run starting
    at the first: a mapping that binds slots 1 and 3 but not 2 cannot take a
    third image, because it would have to go into an input nothing is bound to.
    """
    mapping = parameter_mapping or {}
    count = 0
    for name in REFERENCE_IMAGE_FIELDS:
        if name not in mapping:
            break
        count += 1
    return count


LOGICAL_FIELDS: tuple[str, ...] = (
    POSITIVE_PROMPT,
    NEGATIVE_PROMPT,
    SEED,
    WIDTH,
    HEIGHT,
    FRAMES,
    *REFERENCE_IMAGE_FIELDS,
    ASPECT_RATIO,
    OUTPUT_PREFIX,
)

# Fields a workflow must map before it can drive a real generation. Without a
# prompt and a seed the run is neither controllable nor reproducible.
REQUIRED_LOGICAL_FIELDS: tuple[str, ...] = (POSITIVE_PROMPT, SEED)


class WorkflowValidationError(Exception):
    """Raised when a job cannot be turned into a submittable payload."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


@dataclass
class BuiltPayload:
    """A payload ready for submission, with its provenance."""

    payload: dict[str, Any]
    snapshot_path: str = ""
    workflow_sha256: str = ""
    #: Logical fields carried by the job but absent from the workflow mapping.
    unmapped_fields: list[str] = field(default_factory=list)
    #: True when no usable workflow was registered and the raw logical values
    #: are being passed through (mock provider only).
    passthrough: bool = False


def logical_values_for_job(job: GenerationJob) -> dict[str, Any]:
    """Extract the canonical logical parameter values carried by a job."""
    raw = dict(job.parameter_map or {})
    values = {k: v for k, v in raw.items() if k in LOGICAL_FIELDS}
    # The seed column is authoritative; keep the payload consistent with it.
    if job.seed is not None:
        values[SEED] = job.seed
    return values


def write_snapshot(job_id: str, payload: dict[str, Any]) -> str:
    """Persist the exact submitted payload; return its absolute path.

    Written via temp-and-rename so an interrupted write never leaves a
    truncated snapshot behind (NFR-07).
    """
    dest = os.path.join(paths.snapshots_dir(), f"{job_id}.json")
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, dest)
    return dest


def build_payload(
    db: Session,
    job: GenerationJob,
    *,
    require_workflow: bool,
) -> BuiltPayload:
    """
    Build the ComfyUI payload for a job.

    Parameters
    ----------
    db : Session
        Session used to load the registered workflow.
    job : GenerationJob
        The job to build a payload for.
    require_workflow : bool
        When True (a real ComfyUI provider), a registered workflow with a
        valid, complete mapping is mandatory and anything missing raises
        WorkflowValidationError. When False (mock provider), a job without a
        usable workflow falls back to passing the logical values through so the
        product flow can still be exercised end to end.

    Raises
    ------
    WorkflowValidationError
        If require_workflow is True and no submittable payload can be built.
    """
    values = logical_values_for_job(job)

    workflow: Workflow | None = None
    if job.workflow_id:
        workflow = db.query(Workflow).filter(Workflow.id == job.workflow_id).first()

    if workflow is None:
        msg = (
            f"Job {job.id} has no registered workflow "
            f"(workflow_id={job.workflow_id!r}). Assign an image/video workflow "
            f"to the shot or set a project default."
        )
        if require_workflow:
            raise WorkflowValidationError(msg)
        logger.debug("%s - passing logical values through to mock provider", msg)
        return BuiltPayload(payload=values, passthrough=True)

    # An editor/UI graph is never submittable, whatever its mapping says.
    # ComfyUI's /prompt endpoint only accepts the flattened API shape, so this
    # is refused before any mapping work happens.
    source_format = (workflow.source_format or "unknown").lower()
    if source_format != WorkflowFormat.API.value:
        msg = (
            f"Workflow '{workflow.name}' was imported as "
            f"{source_format}-format JSON, which ComfyUI cannot execute. "
            f"Open it in ComfyUI and use Workflow -> Export (API), then "
            f"import that file and map its nodes."
        )
        if require_workflow:
            raise WorkflowValidationError(msg)
        logger.debug("%s - passing logical values through to mock provider", msg)
        return BuiltPayload(payload=values, passthrough=True)

    mapping = workflow.parameter_mapping or {}
    if not workflow.source_json_path or not mapping:
        msg = (
            f"Workflow '{workflow.name}' has no source JSON or no parameter "
            f"mapping. Import the API-format JSON and map its nodes before "
            f"generating."
        )
        if require_workflow:
            raise WorkflowValidationError(msg)
        logger.debug("%s - passing logical values through to mock provider", msg)
        return BuiltPayload(payload=values, passthrough=True)

    try:
        workflow_data = workflow_registry.load_workflow_source(workflow.source_json_path)
    except (FileNotFoundError, ValueError) as exc:
        msg = f"Cannot load workflow source for '{workflow.name}': {exc}"
        if require_workflow:
            raise WorkflowValidationError(msg) from exc
        logger.warning("%s - passing logical values through to mock provider", msg)
        return BuiltPayload(payload=values, passthrough=True)

    # Re-validate the mapping against the JSON at submit time. The workflow may
    # have been re-imported with different node IDs since it was last marked
    # valid, which is exactly the H3 risk called out in the PRD.
    is_valid, errors, _warnings = workflow_registry.validate_mapping(
        workflow_data=workflow_data,
        parameter_mapping=mapping,
        output_mapping=workflow.output_mapping or [],
    )
    if not is_valid:
        msg = f"Workflow '{workflow.name}' mapping no longer matches its JSON"
        if require_workflow:
            raise WorkflowValidationError(msg, errors)
        logger.warning("%s: %s - passing values through to mock provider", msg, errors)
        return BuiltPayload(payload=values, passthrough=True)

    if require_workflow:
        missing = [f for f in REQUIRED_LOGICAL_FIELDS if f not in mapping]
        if missing:
            raise WorkflowValidationError(
                f"Workflow '{workflow.name}' is missing required field "
                f"mapping(s): {', '.join(missing)}",
                [f"Unmapped required field: {f}" for f in missing],
            )

    payload = workflow_registry.apply_parameter_mapping(
        workflow_data=workflow_data,
        parameter_mapping=mapping,
        values=values,
    )
    unmapped = sorted(k for k in values if k not in mapping)
    if unmapped:
        logger.info(
            "Job %s: logical field(s) %s not mapped by workflow '%s'; "
            "the workflow's own defaults apply.",
            job.id, ", ".join(unmapped), workflow.name,
        )

    return BuiltPayload(
        payload=payload,
        snapshot_path=write_snapshot(job.id, payload),
        workflow_sha256=workflow.sha256_hash or "",
        unmapped_fields=unmapped,
    )
