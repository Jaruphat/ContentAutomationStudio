"""Establishing a place once, instead of describing it nine times.

The first ODDVERSE episode was nine key images generated independently from
nine paragraphs that all began with the same world description. Four of them
are recognisably the same abandoned station; the rest are a different building
- green weatherboard in one shot, red brick in another, daylight in a third.
No amount of rewriting the paragraph fixes that, because the model is never
asked to match anything. It is asked nine separate times to imagine a station.

Characters solved this: generate a canonical sheet, approve it, hand the
approved image to every shot as a real reference input. A place needed exactly
the same thing and had no way to get it - a reference sheet could hold an
uploaded plate, but nothing in the application could make one.

So a plate is generated *into a reference sheet*. What comes out is an ordinary
reference image on an ordinary sheet, which means binding it to shots, sending
it to the provider and recording it in a job's provenance already work and none
of them need to know it was generated rather than uploaded.

The refusals are the ones the character sheet learned the hard way, because
they are the same mistake in a different place.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from sqlalchemy.orm import Session

from app.models import ReferenceSheet, Workflow
from app.services import job_payload, reference_bible, workflow_registry
from app.services.comfyui_adapter import JobStatusEnum
from app.services.workflow_format import WorkflowFormat

logger = logging.getLogger("cas.reference_generation")

POLL_INTERVAL_SEC = 0.05
MAX_POLLS = 4800  # four minutes at the default interval


class ReferenceGenerationError(Exception):
    """A plate that could not be produced, with the reason."""


def _resolve_workflow(db: Session, workflow_id: str | None) -> Workflow:
    workflow = (
        db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if workflow_id else None
    )
    if workflow is None:
        raise ReferenceGenerationError(
            "Generating a reference plate needs a registered image workflow. "
            "Choose one, or set the project's default image workflow."
        )
    source_format = (workflow.source_format or "unknown").lower()
    if source_format != WorkflowFormat.API.value:
        raise ReferenceGenerationError(
            f"Workflow '{workflow.name}' was imported as {source_format}-format "
            f"JSON, which ComfyUI cannot execute. Export it with "
            f"Workflow -> Export (API) and import that file."
        )
    if not workflow.source_json_path or not (workflow.parameter_mapping or {}):
        raise ReferenceGenerationError(
            f"Workflow '{workflow.name}' has no source JSON or no parameter "
            f"mapping. Map its nodes before generating with it."
        )
    if job_payload.REFERENCE_IMAGE in (workflow.parameter_mapping or {}):
        # A plate establishes a place; it has no reference to supply.
        # Injection replaces only the values it is handed, so this graph would
        # keep whichever image its export baked in and report success - the
        # exact failure the character sheet was caught by.
        raise ReferenceGenerationError(
            f"Workflow '{workflow.name}' expects a reference image, so it edits "
            f"an existing picture rather than establishing one. A plate has no "
            f"reference to supply and would inherit whichever image is baked "
            f"into the workflow. Choose a text-to-image workflow."
        )
    return workflow


async def _await_completion(provider: Any, prompt_id: str) -> tuple[bool, str]:
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
        "The provider did not finish this plate in time. It may still be "
        "running; check the backend before generating again."
    )


async def generate_image(
    db: Session,
    sheet: ReferenceSheet,
    *,
    prompt: str,
    negative_prompt: str = "",
    provider: Any,
    provider_id: str,
    model: str = "",
    workflow_id: str | None = None,
    seed: int | None = None,
    width: int = 1024,
    height: int = 1024,
    caption: str = "",
):
    """Generate one plate and store it on ``sheet``.

    Nothing is written until the provider has produced a file that can be
    read: a half-written plate on the sheet would be bound to shots as if it
    were a finished one.
    """
    text = (prompt or "").strip()
    if not text:
        raise ReferenceGenerationError(
            "A plate needs a prompt. A blank one still produces something, "
            "and whatever it produces becomes the world every later shot is "
            "matched against."
        )

    workflow = _resolve_workflow(db, workflow_id)
    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    values = {
        job_payload.POSITIVE_PROMPT: text,
        job_payload.NEGATIVE_PROMPT: (negative_prompt or "").strip(),
        job_payload.SEED: seed,
        job_payload.WIDTH: width,
        job_payload.HEIGHT: height,
        job_payload.OUTPUT_PREFIX: f"plate_{sheet.id[:8]}",
    }
    try:
        workflow_data = workflow_registry.load_workflow_source(
            workflow.source_json_path
        )
        payload = workflow_registry.apply_parameter_mapping(
            workflow_data=workflow_data,
            parameter_mapping=workflow.parameter_mapping or {},
            values=values,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ReferenceGenerationError(
            f"Cannot load or map the workflow source: {exc}"
        ) from exc

    context = {
        "generation_mode": "image",
        "width": width,
        "height": height,
        "model": model or "",
        "reference_sheet_id": sheet.id,
    }
    try:
        prompt_id = await provider.submit_job(
            payload, f"plate-{sheet.id}", context=context
        )
    except Exception as exc:  # provider transport failure
        raise ReferenceGenerationError(f"Submission failed: {exc}") from exc

    ok, error = await _await_completion(provider, prompt_id)
    if not ok:
        raise ReferenceGenerationError(f"The plate could not be generated: {error}")

    outputs = await provider.get_job_outputs(prompt_id)
    image_output = next(
        (out for out in outputs if (out.file_type or "image") == "image"), None
    )
    if image_output is None:
        raise ReferenceGenerationError(
            "The provider completed this plate but returned no image file."
        )
    try:
        with open(image_output.file_path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise ReferenceGenerationError(
            f"The generated plate could not be read back: {exc}"
        ) from exc

    try:
        return reference_bible.store_image(
            db,
            sheet=sheet,
            data=data,
            original_filename=f"plate_{seed}.png",
            content_type="",
            role="canonical",
            caption=caption or text[:120],
            source="generated",
            source_detail={
                # A world every later shot is conditioned on has to be
                # traceable back to the request that produced it, or the whole
                # film rests on an unknown.
                "provider_id": provider_id,
                "model": model or "",
                "workflow_id": workflow.id,
                "workflow_sha256": workflow.sha256_hash or "",
                "prompt_id": prompt_id,
                "seed": seed,
                "prompt": text,
                "negative_prompt": (negative_prompt or "").strip(),
                "width": width,
                "height": height,
            },
        )
    except reference_bible.ReferenceBibleError as exc:
        raise ReferenceGenerationError(
            f"The generated plate could not be stored: {exc}"
        ) from exc


__all__ = ["ReferenceGenerationError", "generate_image"]
