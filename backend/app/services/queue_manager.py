"""
Persistent Queue Manager.

Manages the lifecycle of generation jobs:
  - Loads pending/running jobs from DB on startup (resume/reconcile).
  - Processes jobs sequentially via the configured ComfyUI provider.
  - Handles state transitions: Queued -> Running -> Completed/Failed.
  - Retry logic with max 3 attempts for transient errors.
  - Pause/resume and cancel support.
  - Runs as a background asyncio task inside the FastAPI process.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import GenerationJob, Project, Scene, Shot, Take, Workflow
from app.services import error_classifier, job_payload, media_providers, revisions
from app.services.comfyui_adapter import ComfyUIProvider, JobStatusEnum, MediaProvider
from app.services.job_payload import WorkflowValidationError, build_payload
from app.services.mock_provider import MockComfyUIProvider

logger = logging.getLogger("cas.queue_manager")

MAX_ATTEMPTS = 3
POLL_INTERVAL_SEC = 1.0
IDLE_INTERVAL_SEC = 2.0

#: What a restart decided to do with a job that was already submitted.
RESUME_HANDLED = "handled"      # the submission reached a terminal state here
RESUME_POLL = "poll"            # it is still with the provider; keep polling
RESUME_RESUBMIT = "resubmit"    # the provider proved it holds no such work

#: Error code for a submission the provider can neither return nor disown.
UNRECONCILED_ERROR = "UnreconciledSubmission"


class QueueManager:
    """
    Singleton-style queue manager that processes generation jobs.

    Designed to be started once during app lifespan and stopped on shutdown.
    """

    def __init__(self, provider: ComfyUIProvider | None = None):
        self._provider: ComfyUIProvider = provider or MockComfyUIProvider()
        self._paused: bool = False
        self._running: bool = False
        self._task: asyncio.Task | None = None
        # Per-project pause state
        self._paused_projects: set[str] = set()

    @property
    def provider(self) -> ComfyUIProvider:
        """The ComfyUI provider currently backing the queue."""
        return self._provider

    @provider.setter
    def provider(self, value: ComfyUIProvider) -> None:
        self._provider = value

    @property
    def paused(self) -> bool:
        return self._paused

    def is_project_paused(self, project_id: str) -> bool:
        return self._paused or project_id in self._paused_projects

    def pause(self, project_id: str | None = None) -> None:
        if project_id:
            self._paused_projects.add(project_id)
        else:
            self._paused = True

    def resume(self, project_id: str | None = None) -> None:
        if project_id:
            self._paused_projects.discard(project_id)
        else:
            self._paused = False

    def start(self) -> None:
        """Start the background processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._process_loop())
        logger.info("Queue manager started")

    async def stop(self) -> None:
        """Gracefully stop the processing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Queue manager stopped")

    def reconcile_on_startup(self) -> None:
        """
        Requeue jobs that were Running when the app last shut down.

        A job that had already been submitted keeps its provider prompt id.
        That id is the only evidence that work may be outstanding - a real
        generation the user is being billed for, or one already finished and
        waiting in the provider's history. Clearing it here would make the
        restarted queue submit the same job a second time, paying for it twice
        and producing two takes for one request. The id is retained and
        :meth:`_resume_submission` decides what to do with it before anything
        is resubmitted.
        """
        db: Session = SessionLocal()
        try:
            self._paused_projects = {
                project.id
                for project in db.query(Project)
                .filter(Project.queue_paused.is_(True))
                .all()
            }
            running_jobs = (
                db.query(GenerationJob)
                .filter(GenerationJob.status == "Running")
                .all()
            )
            for job in running_jobs:
                if job.submitted_at and not (job.comfyui_prompt_id or "").strip():
                    job.status = "Failed"
                    job.error_code = UNRECONCILED_ERROR
                    job.error_message = (
                        "This job began submission before the backend restarted, "
                        "but no provider identity was committed. The provider may "
                        "already have accepted and charged for it, so it was not "
                        "resubmitted automatically. Check the provider, then use "
                        "Retry to submit it again."
                    )
                    job.completed_at = datetime.now(timezone.utc)
                    shot = db.query(Shot).filter(Shot.id == job.shot_id).first()
                    if shot:
                        shot.status = "Failed"
                    continue
                job.status = "Queued"
                if job.comfyui_prompt_id:
                    logger.info(
                        "Reconcile: job %s was submitted as prompt %s; queued for "
                        "reconciliation rather than resubmission",
                        job.id, job.comfyui_prompt_id,
                    )
                else:
                    logger.info(
                        "Reconcile: job %s was never submitted; requeued", job.id
                    )
                    job.started_at = None
            db.commit()
        finally:
            db.close()

    async def _process_loop(self) -> None:
        """Main loop: pick next queued job, submit, poll until done."""
        while self._running:
            if self._paused:
                await asyncio.sleep(IDLE_INTERVAL_SEC)
                continue

            db: Session = SessionLocal()
            try:
                job = self._pick_next_job(db)
                if job is None:
                    db.close()
                    await asyncio.sleep(IDLE_INTERVAL_SEC)
                    continue

                await self._execute_job(db, job)
            except Exception:
                logger.exception("Unexpected error in queue loop")
            finally:
                db.close()

            await asyncio.sleep(0.1)

    def _pick_next_job(self, db: Session) -> GenerationJob | None:
        """Get the oldest Queued job that is not in a paused project."""
        query = (
            db.query(GenerationJob)
            .filter(GenerationJob.status == "Queued")
            .order_by(GenerationJob.created_at)
        )
        for job in query.all():
            # Determine project_id through shot -> scene -> project
            shot = db.query(Shot).filter(Shot.id == job.shot_id).first()
            if shot:
                from app.models import Scene
                scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
                if scene and scene.project_id in self._paused_projects:
                    continue
            return job
        return None

    async def _execute_job(self, db: Session, job: GenerationJob) -> None:
        """Submit a single job, poll for completion, and update DB."""
        now = datetime.now(timezone.utc)

        # A prompt id already on the job means a previous process submitted it
        # and did not see it finish. This run reconciles that submission before
        # it considers making another one.
        resuming_prompt_id = (job.comfyui_prompt_id or "").strip() or None

        # Transition to Running
        job.status = "Running"
        job.started_at = now
        if not resuming_prompt_id:
            job.attempts += 1
        db.commit()

        # Update shot status
        shot = db.query(Shot).filter(Shot.id == job.shot_id).first()
        if shot and shot.status != "Generating":
            shot.status = "Generating"
            db.commit()

        # Which vendor runs this job is a property of the job, not of the
        # queue: an OpenAI still and a ComfyUI video can sit side by side in
        # the same queue and both end up as ordinary takes.
        try:
            provider = self._provider_for_job(job)
        except media_providers.UnknownMediaProviderError as exc:
            self._fail_permanently(db, job, shot, "UnknownMediaProvider", str(exc))
            return

        provider_id = job.media_provider_id or media_providers.COMFYUI
        if not media_providers.is_configured(provider_id):
            self._fail_permanently(
                db, job, shot, "ProviderNotConfigured",
                f"Media provider '{provider_id}' is not configured on this "
                f"machine. Set "
                f"{media_providers.API_KEY_ENV.get(provider_id, 'its credentials')} "
                f"in your local .env and restart the backend.",
            )
            return

        try:
            if resuming_prompt_id:
                outcome = await self._resume_submission(
                    db, job, shot, provider, resuming_prompt_id
                )
                if outcome == RESUME_HANDLED:
                    return
                if outcome == RESUME_POLL:
                    await self._poll_until_terminal(
                        db, job, shot, provider, resuming_prompt_id
                    )
                    return
                # The provider proved it holds no such work, so this is a fresh
                # attempt rather than a continuation of the old one.
                job.comfyui_prompt_id = None
                job.attempts += 1
                db.commit()

            if (
                provider_id == media_providers.COMFYUI
                and provider.requires_workflow_payload
                and any(
                    isinstance(image, dict) and image.get("submitted", True)
                    for image in (job.reference_provenance or {}).get("images", [])
                )
            ):
                await self._prepare_reference_inputs(db, job, provider)

            # Resolve the registered workflow JSON and inject this job's
            # logical parameter values through the workflow's node mapping.
            # No H3 node ID ever reaches this module.
            try:
                built = build_payload(
                    db,
                    job,
                    require_workflow=provider.requires_workflow_payload,
                )
            except WorkflowValidationError as exc:
                self._fail_permanently(
                    db, job, shot, "WorkflowValidationError", "; ".join(exc.errors)
                )
                return

            job.workflow_snapshot_path = built.snapshot_path
            job.workflow_sha256 = built.workflow_sha256
            db.commit()

            # Commit before crossing the provider boundary. If the provider
            # accepts the work and this process dies before receiving/storing
            # its id, restart can now distinguish that ambiguous window from a
            # job that was never submitted and quarantine it instead of paying
            # for a duplicate.
            job.submitted_at = datetime.now(timezone.utc)
            db.commit()
            prompt_id = await provider.submit_job(
                built.payload, job.id, context=self._job_context(db, job, shot)
            )
            job.comfyui_prompt_id = prompt_id
            db.commit()

            await self._poll_until_terminal(db, job, shot, provider, prompt_id)

        except Exception as exc:
            logger.exception("Error executing job %s", job.id)
            classification = error_classifier.classify(str(exc), exc)
            if not classification.retryable:
                # Deterministic provider rejection (invalid model, OOM, etc.)
                # is a known failure, not an unknown accepted submission.
                self._handle_failure(db, job, shot, message=str(exc), exception=exc)
            elif job.submitted_at and not (job.comfyui_prompt_id or "").strip():
                self._fail_permanently(
                    db,
                    job,
                    shot,
                    UNRECONCILED_ERROR,
                    "Submission started but no provider identity was returned. "
                    "The provider may already have accepted and charged for the "
                    "work, so it was not retried automatically. Check the "
                    "provider, then use Retry to submit it again. "
                    f"Provider error: {exc}",
                )
            else:
                self._handle_failure(db, job, shot, message=str(exc), exception=exc)

    async def _poll_until_terminal(
        self,
        db: Session,
        job: GenerationJob,
        shot: Shot | None,
        provider: MediaProvider,
        prompt_id: str,
    ) -> None:
        """Poll one submitted prompt until it completes, fails or is cancelled."""
        while self._running:
            if self._is_cancelled(db, job):
                logger.info("Job %s cancelled while running; stopping poll", job.id)
                return

            status = await provider.get_job_status(prompt_id)

            if status.status == JobStatusEnum.COMPLETED:
                await self._complete_job(db, job, shot, provider, prompt_id)
                return

            if status.status == JobStatusEnum.FAILED:
                self._handle_failure(
                    db, job, shot,
                    message=status.error_message or "Unknown error",
                    fallback_code=status.error_code,
                )
                return

            # Still running or queued -- keep polling
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def _complete_job(
        self,
        db: Session,
        job: GenerationJob,
        shot: Shot | None,
        provider: MediaProvider,
        prompt_id: str,
    ) -> None:
        """Record a finished submission: outputs, takes and shot status."""
        outputs = await provider.get_job_outputs(prompt_id)
        provenance = self._record_provenance(job, provider, prompt_id)
        job.status = "Completed"
        job.completed_at = datetime.now(timezone.utc)
        job.outputs = [
            {
                "file_path": o.file_path,
                "type": o.file_type,
                "width": o.width,
                "height": o.height,
            }
            for o in outputs
        ]
        db.commit()

        # Create Take records for each output. Each one carries the provider,
        # model, request parameters, usage, cost and seed that produced it, so
        # a take's origin stays auditable long after the job row's context is
        # forgotten.
        for o in outputs:
            take = Take(
                id=str(uuid.uuid4()),
                shot_id=job.shot_id,
                job_id=job.id,
                run_id=job.run_id,
                file_path=o.file_path,
                thumbnail_path="",
                duration_sec=o.duration_sec,
                width=o.width,
                height=o.height,
                frame_rate=o.frame_rate,
                codec=o.codec,
                media_provider_id=job.media_provider_id or media_providers.COMFYUI,
                media_model=job.media_model or "workflow",
                request_params=dict(job.request_params or {}),
                usage=dict(job.usage or {}),
                estimated_cost_usd=job.estimated_cost_usd,
                provenance={
                    **dict(provenance),
                    "references": dict(job.reference_provenance or {}),
                },
                prompt_revision=job.prompt_revision,
                prompt_sha256=job.prompt_sha256,
                content_sha256=job.content_sha256,
                reference_image_ids=list(job.reference_image_ids or []),
                reference_sha256s=list(job.reference_sha256s or []),
                character_set_ids=list(job.character_set_ids or []),
                character_set_sha256s=list(job.character_set_sha256s or []),
                continuity_source_take_id=job.continuity_source_take_id,
                continuity_source_sha256=job.continuity_source_sha256 or "",
                lineage={"job_id": job.id},
                review_status="Pending",
            )
            db.add(take)

        if shot:
            shot.status = "NeedsReview"
            # Only the shot this job was actually compiled from may have its
            # staleness cleared. A shot edited while the job was in flight has
            # moved on, and crediting this take to the new revision would hide
            # that the delivered media is out of date.
            current = revisions.mark_generated_if_current(
                db, shot, job.content_sha256 or ""
            )
            if not current:
                logger.info(
                    "Job %s finished against an older revision of shot %s; "
                    "the shot stays flagged for regeneration",
                    job.id, shot.id,
                )
        db.commit()
        logger.info("Job %s completed with %d output(s)", job.id, len(outputs))

    async def _resume_submission(
        self,
        db: Session,
        job: GenerationJob,
        shot: Shot | None,
        provider: MediaProvider,
        prompt_id: str,
    ) -> str:
        """Decide what a restart should do with an already-submitted job.

        Resubmitting is only safe when the provider can show it holds no such
        work. Anything else - finished, still queued, or simply unknowable -
        must not turn into a second generation, because on a metered provider
        that is a second charge for a request the user made once.
        """
        try:
            status = await provider.get_job_status(prompt_id)
        except Exception as exc:  # provider unreachable during reconciliation
            logger.warning(
                "Could not reconcile job %s (prompt %s): %s", job.id, prompt_id, exc
            )
            self._requeue_for_reconciliation(db, job, shot, prompt_id, str(exc))
            return RESUME_HANDLED

        if status.status == JobStatusEnum.COMPLETED:
            logger.info(
                "Job %s was already completed by the provider; collecting its "
                "outputs instead of resubmitting", job.id,
            )
            await self._complete_job(db, job, shot, provider, prompt_id)
            return RESUME_HANDLED

        absent = await self._submission_is_absent(provider, prompt_id)

        if absent is True:
            return RESUME_RESUBMIT

        if absent is None:
            # The provider cannot say whether this prompt ever existed, so the
            # work may have run and been billed - and a reported failure may
            # only mean "I no longer remember this id". Failing permanently
            # keeps the decision with the user: Retry resubmits, nothing else.
            self._fail_permanently(
                db, job, shot, UNRECONCILED_ERROR,
                f"This job was submitted as {prompt_id} before the backend "
                f"restarted, and the provider can no longer say what happened "
                f"to it. It may already have run - and been charged for. "
                f"Check the provider, then use Retry to submit it again.",
            )
            return RESUME_HANDLED

        # The provider still holds this prompt, so its verdict is trustworthy.
        if status.status in (JobStatusEnum.FAILED, JobStatusEnum.CANCELLED):
            self._handle_failure(
                db, job, shot,
                message=status.error_message or "Unknown error",
                fallback_code=status.error_code,
            )
            return RESUME_HANDLED

        return RESUME_POLL

    @staticmethod
    async def _submission_is_absent(
        provider: MediaProvider, prompt_id: str
    ) -> bool | None:
        """True only when the provider positively disowns this prompt id."""
        try:
            known = await provider.submission_exists(prompt_id)
        except Exception:  # pragma: no cover - a provider bug is not proof
            logger.exception("submission_exists failed for prompt %s", prompt_id)
            return None
        if known is None:
            return None
        return not known

    def _requeue_for_reconciliation(
        self,
        db: Session,
        job: GenerationJob,
        shot: Shot | None,
        prompt_id: str,
        reason: str,
    ) -> None:
        """Try the reconciliation again later, keeping the prompt id intact.

        Bounded by the same attempt ceiling as any other failure, so a provider
        that stays unreachable stops the job with an explanation instead of
        holding the queue in a retry loop.
        """
        job.attempts = (job.attempts or 0) + 1
        if job.attempts >= MAX_ATTEMPTS:
            self._fail_permanently(
                db, job, shot, UNRECONCILED_ERROR,
                f"This job was submitted as {prompt_id}, but the provider could "
                f"not be reached to find out what happened to it ({reason}). It "
                f"was not resubmitted, because it may already have run. Bring "
                f"the provider back and use Retry.",
            )
            return
        job.status = "Queued"
        job.started_at = None
        db.commit()

    async def _prepare_reference_inputs(
        self, db: Session, job: GenerationJob, provider: Any
    ) -> None:
        """Upload a job's reference images and bind each to its own slot.

        Slots are filled in the order conditioning resolved them, so the image
        the graph treats as primary - a start frame, before identity - is the
        one that lands in the first input.
        """
        conceptual_images = list(
            (job.reference_provenance or {}).get("images") or []
        )
        images = [
            image
            for image in conceptual_images
            if isinstance(image, dict) and image.get("submitted", True)
        ]
        if not images:
            raise WorkflowValidationError(
                "Reference image provenance is missing from the generation job"
            )
        workflow = db.query(Workflow).filter(Workflow.id == job.workflow_id).first()
        parameter_mapping = (workflow.parameter_mapping or {}) if workflow else {}
        capacity = job_payload.reference_capacity(parameter_mapping)
        if not capacity:
            raise WorkflowValidationError(
                "Workflow is missing the referenceImage mapping"
            )
        if len(images) > capacity:
            # Selection should already have trimmed to capacity. Reaching here
            # means the two disagree, and submitting anyway would render a shot
            # conditioned differently from the one its lineage describes.
            raise WorkflowValidationError(
                f"This workflow mapping accepts {capacity} reference image(s), "
                f"but {len(images)} were marked for submission"
            )

        uploads: dict[int, dict[str, Any]] = {}
        parameter_values: dict[str, Any] = {}
        for index, original in enumerate(images):
            image = dict(original)
            file_path = str(image.get("file_path") or "")
            if not file_path or not os.path.isfile(file_path):
                raise WorkflowValidationError(
                    f"Reference image file is missing: "
                    f"{file_path or image.get('image_id')}"
                )
            field_name = job_payload.reference_image_field(index)
            mapping = parameter_mapping.get(field_name)
            extension = os.path.splitext(file_path)[1].lower()
            upload_name = f"cas/{job.id}/{image.get('image_id')}{extension}"
            uploaded = await provider.upload_reference_image(
                file_path,
                upload_name=upload_name,
                mime_type=str(image.get("mime_type") or "application/octet-stream"),
            )
            image["comfyui"] = {**uploaded, "mapping": dict(mapping or {})}
            uploads[id(original)] = image
            parameter_values[field_name] = uploaded["workflow_value"]

        provenance = dict(job.reference_provenance or {})
        provenance["images"] = [
            uploads.get(id(candidate), candidate) for candidate in conceptual_images
        ]
        job.reference_provenance = provenance
        job.parameter_map = {**dict(job.parameter_map or {}), **parameter_values}
        db.commit()

    def _handle_failure(
        self,
        db: Session,
        job: GenerationJob,
        shot: Shot | None,
        *,
        message: str,
        exception: BaseException | None = None,
        fallback_code: str | None = None,
    ) -> None:
        """Categorise a failure and either requeue it or stop.

        Only errors that a retry could plausibly fix are requeued. An
        out-of-memory or missing-model failure is recorded once with the action
        the operator needs to take, rather than repeated until the attempt
        ceiling (PRD 10.5).
        """
        classification = error_classifier.classify(message, exception)
        code = classification.code
        if code == error_classifier.UNKNOWN_ERROR and fallback_code:
            code = fallback_code

        detail = f"{message} | Suggested action: {classification.suggested_action}"

        if classification.retryable and job.attempts < MAX_ATTEMPTS:
            logger.info(
                "Job %s failed with %s (attempt %d/%d); requeueing",
                job.id, code, job.attempts, MAX_ATTEMPTS,
            )
            job.status = "Queued"
            job.error_code = None
            job.error_message = None
            job.started_at = None
            job.completed_at = None
            job.comfyui_prompt_id = None
            db.commit()
            return

        if not classification.retryable:
            logger.warning(
                "Job %s failed with non-retryable %s: %s", job.id, code, message
            )
            # Pin attempts so the loop treats this as exhausted.
            job.attempts = MAX_ATTEMPTS
        else:
            logger.warning(
                "Job %s failed with %s after %d attempts", job.id, code, MAX_ATTEMPTS
            )

        job.status = "Failed"
        job.error_code = code
        job.error_message = detail[:1000]
        job.completed_at = datetime.now(timezone.utc)
        if shot:
            shot.status = "Failed"
        db.commit()

    def _provider_for_job(self, job: GenerationJob) -> MediaProvider:
        """The adapter that runs this job.

        ComfyUI work uses whichever adapter *this* manager was configured with,
        mock or real, so the queue keeps a single source of truth for local
        generation. Anything else is looked up in the media provider registry.

        Jobs written before per-shot provider selection existed have no
        ``media_provider_id``, so they resolve to ComfyUI - the behaviour they
        were queued with.
        """
        provider_id = job.media_provider_id or media_providers.COMFYUI
        if provider_id == media_providers.COMFYUI:
            return self._provider
        return media_providers.get_provider(provider_id)

    def _record_provenance(
        self, job: GenerationJob, provider: MediaProvider, prompt_id: str
    ) -> dict[str, Any]:
        """Fold whatever the provider knows about the run into the job row.

        A provider that reports nothing leaves the job's own record - provider
        id, model, request parameters, seed - as the whole story, which is the
        ComfyUI case.
        """
        try:
            reported = provider.get_provenance(prompt_id) or {}
        except Exception:  # pragma: no cover - a provider bug must not lose a take
            logger.exception("Provider provenance failed for job %s", job.id)
            reported = {}

        provenance: dict[str, Any] = {
            "provider_id": job.media_provider_id or media_providers.COMFYUI,
            "model": job.media_model or "workflow",
            "prompt_id": prompt_id,
            "workflow_id": job.workflow_id,
            "workflow_version": job.workflow_version or "",
            "workflow_sha256": job.workflow_sha256 or "",
            "workflow_snapshot_path": job.workflow_snapshot_path or "",
            "seed": job.seed,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        provenance.update(reported)

        if reported.get("request_params"):
            merged = dict(job.request_params or {})
            merged.update(reported["request_params"])
            job.request_params = merged
        if reported.get("usage"):
            job.usage = dict(reported["usage"])
        if reported.get("estimated_cost_usd") is not None:
            job.estimated_cost_usd = reported["estimated_cost_usd"]
        job.provenance = provenance
        return provenance

    def _job_context(
        self, db: Session, job: GenerationJob, shot: Shot | None
    ) -> dict[str, Any]:
        """Advisory metadata describing the media this job should produce."""
        params = job.parameter_map or {}
        request_params = job.request_params or {}
        context: dict[str, Any] = {
            "generation_mode": shot.generation_mode if shot else "image",
            "width": params.get("width"),
            "height": params.get("height"),
            "frames": params.get("frames"),
            "duration_sec": shot.planned_duration_sec if shot else 0.0,
            # What the job was authorised with, so the run cannot quietly
            # differ from the cost that was confirmed.
            "provider_id": job.media_provider_id or media_providers.COMFYUI,
            "model": job.media_model or "workflow",
            "size": request_params.get("size"),
            "quality": request_params.get("quality"),
            "reference_inputs": [
                dict(image)
                for image in (job.reference_provenance or {}).get("images", [])
                if isinstance(image, dict) and image.get("submitted", True)
            ],
        }
        if shot:
            scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
            if scene:
                project = (
                    db.query(Project).filter(Project.id == scene.project_id).first()
                )
                if project:
                    context["frame_rate"] = project.frame_rate
        return context

    def _is_cancelled(self, db: Session, job: GenerationJob) -> bool:
        """Re-read the job's status so a cancel issued through the API during
        a long poll actually stops the loop instead of being overwritten by a
        later Completed/Failed write."""
        db.refresh(job)
        return job.status == "Cancelled"

    def _fail_permanently(
        self,
        db: Session,
        job: GenerationJob,
        shot: Shot | None,
        error_code: str,
        error_message: str,
    ) -> None:
        """Fail a job without consuming retries.

        Used for errors that no amount of retrying can fix, such as a missing
        or invalid workflow mapping (PRD 10.5: do not retry non-transient
        errors). The user must fix the mapping and retry explicitly.
        """
        logger.error("Job %s failed permanently (%s): %s", job.id, error_code, error_message)
        job.status = "Failed"
        job.error_code = error_code
        job.error_message = error_message[:1000]
        job.completed_at = datetime.now(timezone.utc)
        job.attempts = MAX_ATTEMPTS
        if shot:
            shot.status = "Failed"
        db.commit()

    def get_queue_status(self, project_id: str | None = None) -> dict[str, Any]:
        """Get counts of jobs in each state, optionally filtered by project."""
        db: Session = SessionLocal()
        try:
            query = db.query(GenerationJob)

            if project_id:
                from app.models import Scene
                shot_ids = (
                    db.query(Shot.id)
                    .join(Scene, Shot.scene_id == Scene.id)
                    .filter(Scene.project_id == project_id)
                    .all()
                )
                shot_id_set = [s[0] for s in shot_ids]
                if shot_id_set:
                    query = query.filter(GenerationJob.shot_id.in_(shot_id_set))
                else:
                    return {
                        "paused": self.is_project_paused(project_id) if project_id else self._paused,
                        "total_jobs": 0,
                        "queued": 0,
                        "running": 0,
                        "completed": 0,
                        "failed": 0,
                        "cancelled": 0,
                    }

            all_jobs = query.all()
            counts = {"Queued": 0, "Running": 0, "Completed": 0, "Failed": 0, "Cancelled": 0}
            for j in all_jobs:
                counts[j.status] = counts.get(j.status, 0) + 1

            return {
                "paused": self.is_project_paused(project_id) if project_id else self._paused,
                "total_jobs": len(all_jobs),
                "queued": counts["Queued"],
                "running": counts["Running"],
                "completed": counts["Completed"],
                "failed": counts["Failed"],
                "cancelled": counts["Cancelled"],
            }
        finally:
            db.close()


# Module-level singleton
queue_manager = QueueManager()
