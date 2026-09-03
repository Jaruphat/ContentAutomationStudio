"""
Runner that turns a draft character set version into canonical views.

One view is one provider submission. The runner goes through the same
:class:`~app.services.comfyui_adapter.MediaProvider` interface as shot
generation - submit, poll, collect the output file - so a character sheet is
produced by the real backend the project is configured for, not by a parallel
code path that only exists for reference art.

Two things it guarantees:

* **Every view records how it was made.** Provider, model, workflow, request
  parameters, seed and the provider's own prompt id land on the view row, so a
  canonical identity can be traced back to the exact request that produced it.
* **A failure is partial, never silent.** A view that fails is marked failed
  with the provider's reason and the sheet cannot be approved; the views that
  succeeded keep their images so only the broken one needs regenerating.
"""

import asyncio
import logging
import random
from typing import Any

from sqlalchemy.orm import Session

from app.models import CharacterSetVersion, CharacterSetView, Workflow
from app.services import character_sets, job_payload, workflow_registry
from app.services.comfyui_adapter import JobStatusEnum
from app.services.workflow_format import WorkflowFormat

logger = logging.getLogger("cas.character_set_generation")

#: How long one view may take before the runner stops waiting on it.
POLL_INTERVAL_SEC = 0.05
MAX_POLLS = 2400  # 2 minutes at the default interval


class CharacterSetGenerationError(Exception):
    """The version could not be generated at all, with the reason why."""


def _resolve_workflow(
    db: Session, workflow_id: str | None, *, require: bool
) -> Workflow | None:
    """Load the workflow a real provider needs, or refuse the run."""
    workflow = (
        db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if workflow_id
        else None
    )
    if not require:
        return workflow
    if workflow is None:
        raise CharacterSetGenerationError(
            "Generating a character set on ComfyUI needs a registered "
            "image workflow. Assign one as the project's default image "
            "workflow, or choose one for this character set."
        )
    source_format = (workflow.source_format or "unknown").lower()
    if source_format != WorkflowFormat.API.value:
        raise CharacterSetGenerationError(
            f"Workflow '{workflow.name}' was imported as {source_format}-format "
            f"JSON, which ComfyUI cannot execute. Export it with "
            f"Workflow -> Export (API) and import that file."
        )
    if not workflow.source_json_path or not (workflow.parameter_mapping or {}):
        raise CharacterSetGenerationError(
            f"Workflow '{workflow.name}' has no source JSON or no parameter "
            f"mapping. Map its nodes before generating a character set."
        )
    return workflow


def _build_payload(
    workflow: Workflow | None, values: dict[str, Any]
) -> dict[str, Any]:
    """Inject the logical values through the workflow's node mapping.

    Without a workflow the logical values are passed through unchanged, which
    only ever reaches a provider that declares it does not need a graph.
    """
    if workflow is None:
        return dict(values)
    workflow_data = workflow_registry.load_workflow_source(workflow.source_json_path)
    return workflow_registry.apply_parameter_mapping(
        workflow_data=workflow_data,
        parameter_mapping=workflow.parameter_mapping or {},
        values=values,
    )


def _logical_values(
    view: CharacterSetView,
    *,
    negative_prompt: str,
    seed: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    return {
        job_payload.POSITIVE_PROMPT: view.view_prompt or "",
        job_payload.NEGATIVE_PROMPT: negative_prompt,
        job_payload.SEED: seed,
        job_payload.WIDTH: width,
        job_payload.HEIGHT: height,
        job_payload.OUTPUT_PREFIX: f"charset_{view.character_set_id[:8]}_{view.slot}",
    }


async def _await_completion(provider: Any, prompt_id: str) -> tuple[bool, str]:
    """Poll one submission to a terminal state; return (ok, error message)."""
    for _ in range(MAX_POLLS):
        status = await provider.get_job_status(prompt_id)
        if status.status == JobStatusEnum.COMPLETED:
            return True, ""
        if status.status in (JobStatusEnum.FAILED, JobStatusEnum.CANCELLED):
            return False, (
                status.error_message
                or status.error_code
                or "The provider reported a failure with no detail."
            )
        await asyncio.sleep(POLL_INTERVAL_SEC)
    return False, (
        "The provider did not finish this view in time. It may still be "
        "running; check the backend before regenerating."
    )


async def generate_version(
    db: Session,
    version: CharacterSetVersion,
    *,
    provider: Any,
    provider_id: str,
    model: str = "",
    workflow_id: str | None = None,
    seed: int | None = None,
    width: int = 1024,
    height: int = 1024,
) -> CharacterSetVersion:
    """Generate every pending view of ``version`` through ``provider``.

    One seed is shared across the sheet on purpose: the views are meant to be
    the same person, and a per-view seed is the fastest way to get four
    different people.
    """
    character_set = (
        db.query(character_sets.CharacterSet)
        .filter(character_sets.CharacterSet.id == version.character_set_id)
        .first()
    )
    if character_set is None:
        raise CharacterSetGenerationError("This version has no character set.")

    require_workflow = bool(getattr(provider, "requires_workflow_payload", True))
    workflow = _resolve_workflow(db, workflow_id, require=require_workflow)

    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    negative_prompt = (character_set.negative_tokens or "").strip()

    version.status = character_sets.STATUS_GENERATING
    version.provider_id = provider_id
    version.model = model or ""
    version.workflow_id = workflow.id if workflow else None
    version.seed = seed
    db.commit()

    for view in character_sets.list_views(db, version):
        if view.reference_image_id:
            continue
        values = _logical_values(
            view,
            negative_prompt=negative_prompt,
            seed=seed,
            width=width,
            height=height,
        )
        view.status = character_sets.VIEW_GENERATING
        view.provider_id = provider_id
        view.model = model or ""
        view.workflow_id = workflow.id if workflow else None
        view.seed = seed
        view.request_params = dict(values)
        db.commit()

        try:
            payload = _build_payload(workflow, values)
        except (FileNotFoundError, ValueError) as exc:
            raise CharacterSetGenerationError(
                f"Cannot load the workflow source for this character set: {exc}"
            ) from exc

        context = {
            "generation_mode": "image",
            "width": width,
            "height": height,
            "model": model or "",
            "character_set_id": character_set.id,
            "character_set_version": version.version,
            "view_slot": view.slot,
        }

        try:
            prompt_id = await provider.submit_job(
                payload, f"charset-{view.id}", context=context
            )
        except Exception as exc:  # provider transport failure
            character_sets.fail_view(db, view, f"Submission failed: {exc}")
            continue

        ok, error = await _await_completion(provider, prompt_id)
        if not ok:
            character_sets.fail_view(db, view, error)
            continue

        outputs = await provider.get_job_outputs(prompt_id)
        image_output = next(
            (o for o in outputs if (o.file_type or "image") == "image"), None
        )
        if image_output is None:
            character_sets.fail_view(
                db, view,
                "The provider completed this view but returned no image file.",
            )
            continue

        try:
            with open(image_output.file_path, "rb") as f:
                data = f.read()
        except OSError as exc:
            character_sets.fail_view(
                db, view, f"The generated view could not be read back: {exc}",
            )
            continue

        try:
            character_sets.attach_view_image(
                db, view, data=data,
                content_type="",
                original_filename=f"{view.slot}.png",
                provenance={
                    "provider_id": provider_id,
                    "model": model or "",
                    "workflow_id": workflow.id if workflow else "",
                    "workflow_sha256": (workflow.sha256_hash or "") if workflow else "",
                    "prompt_id": prompt_id,
                    "seed": seed,
                    "view_slot": view.slot,
                    "request_params": dict(values),
                },
            )
        except Exception as exc:
            character_sets.fail_view(
                db, view, f"The generated view could not be stored: {exc}",
            )
            continue

    db.refresh(version)
    views = character_sets.list_views(db, version)
    if any(view.status == character_sets.VIEW_FAILED for view in views):
        version.status = character_sets.STATUS_FAILED
    elif all(view.reference_image_id for view in views):
        version.status = character_sets.STATUS_NEEDS_REVIEW
    version.content_sha256 = character_sets.version_content_digest(db, version)
    db.commit()
    db.refresh(version)
    return version
