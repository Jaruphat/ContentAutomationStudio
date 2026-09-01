"""
Tests for the persistent queue manager.

Covers the recovery and control behaviour the PRD calls for: reconciling jobs
that were in flight when the process stopped (section 19.3), not retrying
errors that retrying cannot fix (section 10.5), honouring a cancel issued
while a job is polling, and driving a job to a Take through the mock provider.
"""

import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models import GenerationJob, Scene, Shot, Take, Workflow
from app.services import mock_provider as mock_provider_module
from app.services import queue_manager as qm_module
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
    def test_running_job_is_requeued(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        """A job left Running by a crash must come back as Queued so the
        restarted queue picks it up again."""
        job = make_job(
            db_session, sample_shot.id,
            status="Running",
            comfyui_prompt_id="mock-stale",
        )

        manager.reconcile_on_startup()

        db_session.refresh(job)
        assert job.status == "Queued"
        assert job.comfyui_prompt_id is None
        assert job.started_at is None

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
    async def test_connection_error_is_requeued(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        async def refused(_payload, _job_id, context=None):
            raise ConnectionError("All connection attempts failed")

        manager._provider.submit_job = refused
        job = make_job(db_session, sample_shot.id)
        manager._running = True
        await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Queued"
        assert job.attempts == 1
        assert job.comfyui_prompt_id is None

    @pytest.mark.asyncio
    async def test_connection_error_stops_at_the_attempt_ceiling(
        self, db_session, sample_shot, manager, patched_sessions
    ):
        async def refused(_payload, _job_id, context=None):
            raise ConnectionError("Cannot connect to ComfyUI")

        manager._provider.submit_job = refused
        job = make_job(db_session, sample_shot.id)
        manager._running = True

        for _ in range(qm_module.MAX_ATTEMPTS):
            db_session.refresh(job)
            if job.status != "Queued":
                break
            await manager._execute_job(db_session, job)

        db_session.refresh(job)
        assert job.status == "Failed"
        assert job.error_code == "ConnectionError"
        assert job.attempts == qm_module.MAX_ATTEMPTS

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
