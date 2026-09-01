"""
Generation error classification.

Maps a failure into one of the categories in PRD section 10.5 and decides
whether retrying it can plausibly help. The distinction matters: a dropped
connection is worth retrying, but an out-of-memory failure or a missing model
will fail identically every time, and the PRD is explicit that OOM must not be
retried indefinitely. Retrying those just burns GPU time and buries the real
cause under three identical failures.
"""

from dataclasses import dataclass

# PRD section 10.5 categories.
CONNECTION_ERROR = "ConnectionError"
WORKFLOW_VALIDATION_ERROR = "WorkflowValidationError"
MISSING_MODEL_ERROR = "MissingModelError"
MISSING_CUSTOM_NODE_ERROR = "MissingCustomNodeError"
OUT_OF_MEMORY_ERROR = "OutOfMemoryError"
GENERATION_TIMEOUT = "GenerationTimeout"
OUTPUT_MISSING_ERROR = "OutputMissingError"
MEDIA_VALIDATION_ERROR = "MediaValidationError"
UNKNOWN_ERROR = "UnknownError"


@dataclass(frozen=True)
class Classification:
    """A categorised failure and what to do about it."""

    code: str
    retryable: bool
    #: Operator-facing next step, surfaced in the queue UI.
    suggested_action: str


# Ordered most specific first: an OOM message can also mention "cuda", and a
# missing-node message can also mention "model", so the first match wins.
_RULES: tuple[tuple[tuple[str, ...], Classification], ...] = (
    (
        ("out of memory", "cuda out of memory", "oom", "allocate", "insufficient memory"),
        Classification(
            OUT_OF_MEMORY_ERROR,
            retryable=False,
            suggested_action=(
                "Reduce resolution, frame count or batch size, or lower queue "
                "concurrency, then retry manually. Retrying unchanged will fail "
                "the same way."
            ),
        ),
    ),
    (
        ("custom node", "custom_node", "node type not found", "unknown node",
         "does not exist in this installation"),
        Classification(
            MISSING_CUSTOM_NODE_ERROR,
            retryable=False,
            suggested_action=(
                "Install the custom node this workflow requires in ComfyUI and "
                "restart it, then retry."
            ),
        ),
    ),
    (
        ("checkpoint", "safetensors", "ckpt", "lora", "model not found",
         "value not in list"),
        Classification(
            MISSING_MODEL_ERROR,
            retryable=False,
            suggested_action=(
                "Install the missing checkpoint/LoRA into the ComfyUI models "
                "directory, or point the workflow at a model that is present."
            ),
        ),
    ),
    (
        ("timeout", "timed out", "deadline"),
        Classification(
            GENERATION_TIMEOUT,
            retryable=True,
            suggested_action=(
                "The job exceeded its time budget. It will be retried; if it "
                "keeps timing out, reduce the workload or raise the timeout."
            ),
        ),
    ),
    (
        ("connection", "connect", "unreachable", "refused", "network",
         "temporarily unavailable", "502", "503", "504"),
        Classification(
            CONNECTION_ERROR,
            retryable=True,
            suggested_action=(
                "ComfyUI could not be reached. Confirm it is running and that "
                "COMFYUI_URL is correct; the job will be retried."
            ),
        ),
    ),
    (
        ("no output", "output missing", "no outputs", "empty history"),
        Classification(
            OUTPUT_MISSING_ERROR,
            retryable=False,
            suggested_action=(
                "The workflow completed without producing a file. Check the "
                "output node mapping for this workflow."
            ),
        ),
    ),
    (
        ("invalid prompt", "validation", "mapping", "node id", "field"),
        Classification(
            WORKFLOW_VALIDATION_ERROR,
            retryable=False,
            suggested_action=(
                "ComfyUI rejected the graph. Re-validate the workflow mapping "
                "against its API-format JSON."
            ),
        ),
    ),
    (
        ("codec", "corrupt", "moov atom", "invalid data", "decode"),
        Classification(
            MEDIA_VALIDATION_ERROR,
            retryable=False,
            suggested_action=(
                "The returned media could not be read. Check the workflow's "
                "output format and that the file transferred completely."
            ),
        ),
    ),
)

_UNKNOWN = Classification(
    UNKNOWN_ERROR,
    retryable=True,
    suggested_action=(
        "Unrecognised failure. The job will be retried; check the application "
        "log for the full error."
    ),
)


def classify(message: str | None, exception: BaseException | None = None) -> Classification:
    """
    Categorise a generation failure.

    Parameters
    ----------
    message : str or None
        Error text from the provider, if any.
    exception : BaseException or None
        The originating exception, if the failure came from one. Its type name
        and message are both considered.

    Returns
    -------
    Classification
        The matched category, whether a retry is worth attempting, and the
        suggested operator action.
    """
    haystack = " ".join(
        part for part in (
            message or "",
            type(exception).__name__ if exception is not None else "",
            str(exception) if exception is not None else "",
        ) if part
    ).lower()

    if not haystack.strip():
        return _UNKNOWN

    for needles, classification in _RULES:
        if any(needle in haystack for needle in needles):
            return classification

    return _UNKNOWN
