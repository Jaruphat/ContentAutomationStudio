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
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import GenerationJob, Project, Scene, Shot, Take
from app.services import error_classifier
from app.services.comfyui_adapter import ComfyUIProvider, JobStatusEnum
from app.services.job_payload import WorkflowValidationError, build_payload
from app.services.mock_provider import MockComfyUIProvider

logger = logging.getLogger("cas.queue_manager")

MAX_ATTEMPTS = 3
POLL_INTERVAL_SEC = 1.0
IDLE_INTERVAL_SEC = 2.0


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
        Mark jobs that were Running when the app last shut down as Queued
        so they will be retried. Called during app startup.
        """
        db: Session = SessionLocal()
        try:
            running_jobs = (
                db.query(GenerationJob)
                .filter(GenerationJob.status == "Running")
                .all()
            )
            for job in running_jobs:
                logger.info(f"Reconcile: resetting Running job {job.id} to Queued")
                job.status = "Queued"
                job.comfyui_prompt_id = None
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

        # Transition to Running
        job.status = "Running"
        job.started_at = now
        job.attempts += 1
        db.commit()

        # Update shot status
        shot = db.query(Shot).filter(Shot.id == job.shot_id).first()
        if shot and shot.status != "Generating":
            shot.status = "Generating"
            db.commit()

        try:
            # Resolve the registered workflow JSON and inject this job's
            # logical parameter values through the workflow's node mapping.
            # No H3 node ID ever reaches this module.
            try:
                built = build_payload(
                    db,
                    job,
                    require_workflow=self._provider.requires_workflow_payload,
                )
            except WorkflowValidationError as exc:
                self._fail_permanently(
                    db, job, shot, "WorkflowValidationError", "; ".join(exc.errors)
                )
                return

            job.workflow_snapshot_path = built.snapshot_path
            job.workflow_sha256 = built.workflow_sha256
            db.commit()

            prompt_id = await self._provider.submit_job(
                built.payload, job.id, context=self._job_context(db, job, shot)
            )
            job.comfyui_prompt_id = prompt_id
            job.submitted_at = datetime.now(timezone.utc)
            db.commit()

            # Poll until terminal state
            while self._running:
                if self._is_cancelled(db, job):
                    logger.info("Job %s cancelled while running; stopping poll", job.id)
                    return

                status = await self._provider.get_job_status(prompt_id)

                if status.status == JobStatusEnum.COMPLETED:
                    outputs = await self._provider.get_job_outputs(prompt_id)
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

                    # Create Take records for each output
                    for o in outputs:
                        take = Take(
                            id=str(uuid.uuid4()),
                            shot_id=job.shot_id,
                            job_id=job.id,
                            file_path=o.file_path,
                            thumbnail_path="",
                            duration_sec=o.duration_sec,
                            width=o.width,
                            height=o.height,
                            frame_rate=o.frame_rate,
                            codec=o.codec,
                            review_status="Pending",
                        )
                        db.add(take)

                    # Update shot status
                    if shot:
                        shot.status = "NeedsReview"
                    db.commit()
                    logger.info(f"Job {job.id} completed with {len(outputs)} output(s)")
                    return

                elif status.status == JobStatusEnum.FAILED:
                    self._handle_failure(
                        db, job, shot,
                        message=status.error_message or "Unknown error",
                        fallback_code=status.error_code,
                    )
                    return

                # Still running or queued -- keep polling
                await asyncio.sleep(POLL_INTERVAL_SEC)

        except Exception as exc:
            logger.exception("Error executing job %s", job.id)
            self._handle_failure(db, job, shot, message=str(exc), exception=exc)

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

    def _job_context(
        self, db: Session, job: GenerationJob, shot: Shot | None
    ) -> dict[str, Any]:
        """Advisory metadata describing the media this job should produce."""
        params = job.parameter_map or {}
        context: dict[str, Any] = {
            "generation_mode": shot.generation_mode if shot else "image",
            "width": params.get("width"),
            "height": params.get("height"),
            "frames": params.get("frames"),
            "duration_sec": shot.planned_duration_sec if shot else 0.0,
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
            }
        finally:
            db.close()


# Module-level singleton
queue_manager = QueueManager()
