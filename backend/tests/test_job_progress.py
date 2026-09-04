"""A running job says what it is doing, so a long render can be watched.

A shot can take eight minutes here. Until now the queue recorded "Running" and
nothing else, and the only way to tell a slow job from a stuck one was to open
ComfyUI. The provider now reports a real fraction and a stage; these check the
queue keeps them on the job, where the UI can read them.
"""


import uuid

import pytest

from app.models import GenerationJob
from app.services.comfyui_adapter import JobStatus, JobStatusEnum
from app.services.queue_manager import QueueManager


def _job(db, shot):
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=shot.id, status="Running",
        comfyui_prompt_id="p1", parameter_map={}, seed=1,
    )
    db.add(job)
    db.commit()
    return job


class Provider:
    """Reports one running frame, then completion."""

    def __init__(self):
        self.calls = 0

    async def get_job_status(self, prompt_id):
        self.calls += 1
        if self.calls == 1:
            return JobStatus(
                status=JobStatusEnum.RUNNING, progress=0.375,
                stage="step 3 of 8 in KSampler",
            )
        return JobStatus(status=JobStatusEnum.CANCELLED)


@pytest.mark.asyncio
async def test_the_queue_records_how_far_a_running_job_has_got(
    db_session, sample_shot,
):
    job = _job(db_session, sample_shot)
    manager = QueueManager()
    provider = Provider()

    await manager._record_progress(db_session, job, await provider.get_job_status("p1"))

    assert job.progress == 0.375
    assert job.progress_stage == "step 3 of 8 in KSampler"


@pytest.mark.asyncio
async def test_progress_is_cleared_when_the_job_stops_running(
    db_session, sample_shot,
):
    """A finished job showing 37% forever would be worse than showing nothing."""
    job = _job(db_session, sample_shot)
    manager = QueueManager()
    await manager._record_progress(
        db_session, job, JobStatus(status=JobStatusEnum.RUNNING, progress=0.5, stage="x"),
    )
    await manager._record_progress(
        db_session, job, JobStatus(status=JobStatusEnum.COMPLETED, progress=1.0),
    )

    assert job.progress == 1.0
    assert job.progress_stage == ""


def test_a_job_that_never_ran_reports_no_progress(db_session, sample_shot):
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, status="Queued",
        parameter_map={}, seed=1,
    )
    db_session.add(job)
    db_session.commit()
    assert (job.progress or 0.0) == 0.0
    assert (job.progress_stage or "") == ""


