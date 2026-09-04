"""
Tests for the persistent queue manager.

Covers the recovery and control behaviour the PRD calls for: reconciling jobs
that were in flight when the process stopped (section 19.3), not retrying
errors that retrying cannot fix (section 10.5), honouring a cancel issued
while a job is polling, and driving a job to a Take through the mock provider.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models import GenerationJob, Scene, Shot, Take, Workflow
from app.services import mock_provider as mock_provider_module
from app.services import queue_manager as qm_module
from app.services import revisions
from app.services.comfyui_adapter import JobStatus, JobStatusEnum
from app.services.job_payload import POSITIVE_PROMPT, SEED
from app.services.mock_provider import MockComfyUIProvider
from app.services.queue_manager import QueueManager


@pytest.fixture()
def manager(tmp_path) -> QueueManager:
    """A queue manager backed by an isolated mock provider."""
    return QueueManager(
        provider=MockComfyUIProvider(output_base_dir=str(tmp_path / "generated"))
    )


@pytest.fixture()
def patched_sessions(db_engine, monkeypatch):
    """Point the queue manager's own SessionLocal at the test database.

    The manager opens its own sessions rather than taking an injected one, so
    the test database has to be substituted at module level.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    monkeypatch.setattr(qm_module, "SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


def make_job(db: Session, shot_id: str, status: str = "Queued", **kwargs) -> GenerationJob:
    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        parameter_map={POSITIVE_PROMPT: "a test shot", SEED: 7},
        seed=7,
        status=status,
        **kwargs,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Startup reconciliation
# ---------------------------------------------------------------------------

class TestReconcileOnStartup:
    def test_restores_persisted_project_pause(
        self, db_session, sample_project, manager, patched_sessions
    ):
        sample_project.queue_paused = True
        db_session.commit()

        manager.reconcile_on_startup()

        assert manager.is_project_paused(sample_project.id) is True

    def test_unsubmitted_running_job_is_requeued(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """A job left Running by a crash must come back as Queued so the
        restarted queue picks it up again. Nothing was sent to the provider,
        so there is nothing to reconcile against."""
        job = make_job(db_session, sample_shot.id, status="Running")

        manager.reconcile_on_startup()

        db_session.refresh(job)
        assert job.status == "Queued"
        assert job.comfyui_prompt_id is None
        assert job.started_at is None

    def test_started_submission_without_an_identity_is_quarantined(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """A crash after provider acceptance cannot be treated as never sent."""
        job = make_job(
            db_session,
            sample_shot.id,
            status="Running",
            submitted_at=datetime.now(timezone.utc),
        )

        manager.reconcile_on_startup()

        db_session.refresh(job)
        assert job.status == "Failed"
        assert job.error_code == qm_module.UNRECONCILED_ERROR
        assert "may already have accepted" in job.error_message

    def test_submitted_running_job_keeps_its_provider_prompt_id(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """The prompt id is the only record that real work may be outstanding.

        Dropping it here is what makes the restarted queue submit the same job
        again - a second render, and on a metered provider a second charge, for
        one request.
        """
        job = make_job(
            db_session, sample_shot.id,
            status="Running",
            comfyui_prompt_id="mock-in-flight",
        )

        manager.reconcile_on_startup()

        db_session.refresh(job)
        assert job.status == "Queued"
        assert job.comfyui_prompt_id == "mock-in-flight"

    def test_terminal_jobs_are_untouched(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        completed = make_job(db_session, sample_shot.id, status="Completed")
        failed = make_job(db_session, sample_shot.id, status="Failed")
        cancelled = make_job(db_session, sample_shot.id, status="Cancelled")

        manager.reconcile_on_startup()

        for job, expected in (
            (completed, "Completed"), (failed, "Failed"), (cancelled, "Cancelled")
        ):
            db_session.refresh(job)
            assert job.status == expected

    def test_reconcile_is_idempotent(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        job = make_job(db_session, sample_shot.id, status="Running")
        manager.reconcile_on_startup()
        manager.reconcile_on_startup()
        db_session.refresh(job)
        assert job.status == "Queued"


# ---------------------------------------------------------------------------
# Job selection and pausing
# ---------------------------------------------------------------------------

class TestJobSelection:
    def test_picks_oldest_queued_job(self, db_session, sample_shot, manager):
        first = make_job(db_session, sample_shot.id)
        make_job(db_session, sample_shot.id)
        picked = manager._pick_next_job(db_session)
        assert picked.id == first.id

    def test_skips_jobs_in_a_paused_project(
        self, db_session, sample_project, sample_shot, manager
    ):
        make_job(db_session, sample_shot.id)
        manager.pause(sample_project.id)
        assert manager._pick_next_job(db_session) is None
        manager.resume(sample_project.id)
        assert manager._pick_next_job(db_session) is not None

    def test_global_pause_reported_per_project(self, manager, sample_project):
        manager.pause()
        assert manager.is_project_paused(sample_project.id) is True
        manager.resume()
        assert manager.is_project_paused(sample_project.id) is False


# ---------------------------------------------------------------------------
# Execution through the mock provider
# ---------------------------------------------------------------------------

class TestExecuteJob:
    @pytest.mark.asyncio
    async def test_job_completes_and_creates_a_take(
        self, db_session, sample_shot, manager, patched_sessions, monkeypatch
    ):
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)

        job = make_job(db_session, sample_shot.id)
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Completed"
        assert job.comfyui_prompt_id
        assert job.outputs

        takes = db_session.query(Take).filter(Take.shot_id == sample_shot.id).all()
        assert len(takes) == 1
        assert takes[0].review_status == "Pending"

        db_session.refresh(sample_shot)
        assert sample_shot.status == "NeedsReview"

    @pytest.mark.asyncio
    async def test_take_inherits_revision_and_reference_provenance(
        self, db_session, sample_shot, manager, patched_sessions, monkeypatch
    ):
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)
        job = make_job(
            db_session, sample_shot.id,
            prompt_revision=3, prompt_sha256="b" * 64,
            content_sha256="c" * 64,
            reference_image_ids=["image-1"],
            reference_sha256s=["d" * 64],
            reference_provenance={"images": [{"image_id": "image-1"}]},
            character_set_ids=["set-1"],
            character_set_sha256s=["e" * 64],
            continuity_source_take_id="source-take",
            continuity_source_sha256="f" * 64,
        )
        manager._running = True

        await manager._execute_job(db_session, job)

        take = db_session.query(Take).filter(Take.job_id == job.id).one()
        assert take.prompt_revision == 3
        assert take.prompt_sha256 == "b" * 64
        assert take.content_sha256 == "c" * 64
        assert take.reference_image_ids == ["image-1"]
        assert take.reference_sha256s == ["d" * 64]
        assert take.character_set_ids == ["set-1"]
        assert take.character_set_sha256s == ["e" * 64]
        assert take.continuity_source_take_id == "source-take"
        assert take.continuity_source_sha256 == "f" * 64
        assert take.provenance["references"] == job.reference_provenance

    @pytest.mark.asyncio
    async def test_submission_is_marked_before_the_provider_call_and_not_auto_retried(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """An ambiguous submit exception is not permission to call submit again."""
        job = make_job(db_session, sample_shot.id)
        observed = {}

        async def accepted_then_connection_dropped(payload, job_id, context=None):
            db_session.expire_all()
            durable = db_session.query(GenerationJob).filter(
                GenerationJob.id == job_id
            ).one()
            observed["submitted_at"] = durable.submitted_at
            raise ConnectionError("response lost after provider acceptance")

        manager._provider.submit_job = accepted_then_connection_dropped
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert observed["submitted_at"] is not None
        assert job.status == "Failed"
        assert job.error_code == qm_module.UNRECONCILED_ERROR
        assert job.comfyui_prompt_id is None

    @pytest.mark.asyncio
    async def test_cancel_during_poll_stops_the_job(
        self, db_session, sample_shot, manager, patched_sessions, monkeypatch
    ):
        """A cancel issued through the API while a job polls must win, not be
        overwritten by a later Completed write."""
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)

        job = make_job(db_session, sample_shot.id)

        original = manager._provider.get_job_status
        state = {"polls": 0}

        async def cancelling_status(prompt_id):
            state["polls"] += 1
            if state["polls"] == 1:
                job.status = "Cancelled"
                db_session.commit()
            return await original(prompt_id)

        manager._provider.get_job_status = cancelling_status
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Cancelled"
        assert db_session.query(Take).filter(Take.shot_id == sample_shot.id).count() == 0


# ---------------------------------------------------------------------------
# Resuming a submission across a restart
#
# Everything here is about one question: after a restart, may this job be
# submitted again? Getting it wrong costs real GPU time, or real money.
# ---------------------------------------------------------------------------

class TestResumeAfterRestart:
    @pytest.mark.asyncio
    async def test_a_completed_submission_is_collected_not_resubmitted(
        self, db_session, sample_shot, manager, patched_sessions, monkeypatch
    ):
        """The work finished while the backend was down. It must be harvested."""
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)

        job = make_job(db_session, sample_shot.id)
        manager._running = True
        # Submit through the provider, then simulate the restart: the job goes
        # back to Queued with its prompt id, exactly as reconcile leaves it.
        await manager._execute_job(db_session, job)
        db_session.refresh(job)
        prompt_id = job.comfyui_prompt_id
        db_session.query(Take).delete()
        job.status = "Queued"
        job.outputs = []
        job.completed_at = None
        db_session.commit()

        submissions = []
        original_submit = manager._provider.submit_job

        async def counting_submit(payload, job_id, context=None):
            submissions.append(job_id)
            return await original_submit(payload, job_id, context)

        manager._provider.submit_job = counting_submit
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert submissions == []
        assert job.status == "Completed"
        assert job.comfyui_prompt_id == prompt_id
        assert db_session.query(Take).filter(Take.job_id == job.id).count() == 1

    @pytest.mark.asyncio
    async def test_a_submission_the_provider_disowns_is_submitted_again(
        self, db_session, sample_shot, manager, patched_sessions, monkeypatch
    ):
        """A prompt id the provider has genuinely lost is safe to redo."""
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)

        job = make_job(
            db_session, sample_shot.id, comfyui_prompt_id="mock-forgotten"
        )
        submissions = []
        original_submit = manager._provider.submit_job

        async def counting_submit(payload, job_id, context=None):
            submissions.append(job_id)
            return await original_submit(payload, job_id, context)

        manager._provider.submit_job = counting_submit
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert submissions == [job.id]
        assert job.status == "Completed"
        assert job.comfyui_prompt_id != "mock-forgotten"

    @pytest.mark.asyncio
    async def test_an_unprovable_submission_is_never_blindly_resubmitted(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """A provider that cannot say what happened is not permission to redo it.

        This is the OpenAI Images case after a restart: the image may already
        have been generated and billed. The job stops with an explanation and
        waits for the user to press Retry.
        """
        async def forgotten(prompt_id):
            return JobStatus(
                status=JobStatusEnum.FAILED,
                error_code="UNKNOWN_JOB",
                error_message="not held in memory any more",
            )

        async def cannot_tell(prompt_id):
            return None

        manager._provider.get_job_status = forgotten
        manager._provider.submission_exists = cannot_tell

        submissions = []

        async def counting_submit(payload, job_id, context=None):
            submissions.append(job_id)
            return "should-never-happen"

        manager._provider.submit_job = counting_submit

        job = make_job(
            db_session, sample_shot.id, comfyui_prompt_id="openai-resp-123"
        )
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert submissions == []
        assert job.status == "Failed"
        assert job.error_code == qm_module.UNRECONCILED_ERROR
        assert "openai-resp-123" in job.error_message
        assert db_session.query(Take).filter(Take.job_id == job.id).count() == 0


# ---------------------------------------------------------------------------
# Completion against the revision the job was actually built from
# ---------------------------------------------------------------------------

class TestStaleCompletion:
    @pytest.mark.asyncio
    async def test_first_generation_finishing_after_an_edit_stays_stale(
        self, db_session, sample_project, sample_shot, manager,
        patched_sessions, monkeypatch,
    ):
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)
        revisions.refresh_project(db_session, sample_project.id)
        job = make_job(
            db_session, sample_shot.id,
            prompt_revision=sample_shot.prompt_revision,
            prompt_sha256=sample_shot.prompt_sha256,
            content_sha256=sample_shot.content_sha256,
        )
        sample_shot.action = "changed while the first generation was in flight"
        db_session.commit()
        revisions.refresh_project(db_session, sample_project.id)
        assert sample_shot.generated_revision == 0

        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(sample_shot)
        assert sample_shot.generated_revision == 0
        assert sample_shot.is_stale is True

    @pytest.mark.asyncio
    async def test_completion_clears_staleness_only_for_the_matching_revision(
        self, db_session, sample_project, sample_shot, manager,
        patched_sessions, monkeypatch,
    ):
        """A job that finishes after its shot was edited must not mark the new
        content generated. The take is kept; the shot stays flagged."""
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)
        revisions.refresh_project(db_session, sample_project.id)
        # The shot has been generated once already, so staleness is meaningful.
        revisions.mark_generated(db_session, sample_shot)
        db_session.commit()

        # The job records the shot as it was when Generate was pressed.
        job = make_job(
            db_session, sample_shot.id,
            prompt_revision=sample_shot.prompt_revision,
            prompt_sha256=sample_shot.prompt_sha256,
            content_sha256=sample_shot.content_sha256,
        )
        submitted_revision = sample_shot.prompt_revision

        # ... and the user edits the shot while it is in flight.
        sample_shot.action = "an entirely different action"
        db_session.commit()
        revisions.refresh_project(db_session, sample_project.id)
        db_session.refresh(sample_shot)
        assert sample_shot.prompt_revision > submitted_revision
        assert sample_shot.is_stale is True

        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(sample_shot)
        # The take is kept - it is real output - but it is not evidence that
        # the edited shot has been generated.
        assert db_session.query(Take).filter(Take.job_id == job.id).count() == 1
        assert sample_shot.generated_revision == submitted_revision
        assert sample_shot.generated_revision != sample_shot.prompt_revision
        assert sample_shot.is_stale is True

    @pytest.mark.asyncio
    async def test_completion_of_a_current_job_does_clear_staleness(
        self, db_session, sample_project, sample_shot, manager,
        patched_sessions, monkeypatch,
    ):
        monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
        monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
        monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)
        revisions.refresh_project(db_session, sample_project.id)

        job = make_job(
            db_session, sample_shot.id,
            prompt_revision=sample_shot.prompt_revision,
            prompt_sha256=sample_shot.prompt_sha256,
            content_sha256=sample_shot.content_sha256,
        )
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(sample_shot)
        assert sample_shot.generated_revision == sample_shot.prompt_revision
        assert sample_shot.is_stale is False


# ---------------------------------------------------------------------------
# Non-retryable failures
# ---------------------------------------------------------------------------

class TestPermanentFailure:
    @pytest.mark.asyncio
    async def test_invalid_mapping_fails_without_retrying(
        self, db_session, sample_shot, patched_sessions, sample_workflow_json
    ):
        """A broken workflow mapping is not transient. Retrying it three times
        would just waste GPU time and hide the real problem."""
        from app.services import workflow_registry

        record = workflow_registry.import_workflow(
            raw_bytes=sample_workflow_json, name="Broken", purpose="image"
        )
        workflow = Workflow(**record)
        workflow.parameter_mapping = {
            POSITIVE_PROMPT: {"nodeId": "does-not-exist", "field": "text"},
        }
        db_session.add(workflow)
        db_session.commit()

        # A provider that demands a real mapped payload, like a live instance.
        provider = MockComfyUIProvider()
        provider.requires_workflow_payload = True
        manager = QueueManager(provider=provider)

        job = make_job(db_session, sample_shot.id, workflow_id=workflow.id)
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Failed"
        assert job.error_code == "WorkflowValidationError"
        assert "does-not-exist" in job.error_message
        # attempts pinned at the ceiling so the loop will not pick it up again
        assert job.attempts >= qm_module.MAX_ATTEMPTS

        db_session.refresh(sample_shot)
        assert sample_shot.status == "Failed"


# ---------------------------------------------------------------------------
# Queue status reporting
# ---------------------------------------------------------------------------

class TestQueueStatus:
    def test_counts_by_state(
        self, db_session, sample_project, sample_shot, manager, patched_sessions
    ):
        make_job(db_session, sample_shot.id, status="Queued")
        make_job(db_session, sample_shot.id, status="Running")
        make_job(db_session, sample_shot.id, status="Completed")
        make_job(db_session, sample_shot.id, status="Failed")

        status = manager.get_queue_status(sample_project.id)
        assert status["total_jobs"] == 4
        assert status["queued"] == 1
        assert status["running"] == 1
        assert status["completed"] == 1
        assert status["failed"] == 1

    def test_project_without_shots_reports_zero(
        self, db_session, sample_project, manager, patched_sessions
    ):
        db_session.query(Shot).delete()
        db_session.query(Scene).delete()
        db_session.commit()
        status = manager.get_queue_status(sample_project.id)
        assert status["total_jobs"] == 0


# ---------------------------------------------------------------------------
# Retry policy driven by error category
# ---------------------------------------------------------------------------

class TestRetryPolicy:
    @pytest.mark.asyncio
    async def test_out_of_memory_is_not_retried(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """PRD 10.5: never retry OOM indefinitely. One attempt, then stop with
        an actionable message."""
        async def oom(_payload, _job_id, context=None):
            raise RuntimeError("CUDA out of memory. Tried to allocate 4.00 GiB")

        manager._provider.submit_job = oom
        job = make_job(db_session, sample_shot.id)
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Failed"
        assert job.error_code == "OutOfMemoryError"
        assert job.attempts == qm_module.MAX_ATTEMPTS  # pinned, not consumed
        assert "Suggested action" in job.error_message

    @pytest.mark.asyncio
    async def test_connection_error_after_submit_starts_is_quarantined(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        submissions = []

        async def refused(_payload, _job_id, context=None):
            submissions.append(_job_id)
            raise ConnectionError("All connection attempts failed")

        manager._provider.submit_job = refused
        job = make_job(db_session, sample_shot.id)
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Failed"
        assert submissions == [job.id]
        assert job.comfyui_prompt_id is None
        assert job.error_code == qm_module.UNRECONCILED_ERROR

    @pytest.mark.asyncio
    async def test_connection_error_never_reaches_an_automatic_second_attempt(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        submissions = []

        async def refused(_payload, _job_id, context=None):
            submissions.append(_job_id)
            raise ConnectionError("Cannot connect to ComfyUI")

        manager._provider.submit_job = refused
        job = make_job(db_session, sample_shot.id)
        manager._running = True

        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Failed"
        assert job.error_code == qm_module.UNRECONCILED_ERROR
        assert submissions == [job.id]

    @pytest.mark.asyncio
    async def test_missing_model_is_not_retried(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        async def missing(_payload, _job_id, context=None):
            raise RuntimeError(
                "ckpt_name: 'h3.safetensors' not in list of available checkpoints"
            )

        manager._provider.submit_job = missing
        job = make_job(db_session, sample_shot.id)
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Failed"
        assert job.error_code == "MissingModelError"
