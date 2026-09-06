"""Cancelling a render has to give the shot back.

Found in production, on the second beat of an episode. A clip was queued from
a start frame that turned out to be wrong, the job was cancelled, the frame was
corrected - and the shot could never be generated again. Cancel marked the job
Cancelled and left the shot in "Generating", which is not one of the states the
queue accepts, so every later attempt came back:

    Shot status is 'Generating', expected Draft, Failed, Ready

There is no way out of that through the API. Not a retry (the job is the wrong
one now), not a regenerate (it queues against the same stuck shot), not an edit.
The shot is stranded, and the only remedy is a database write.

A cancel that a person can be talked into pressing must therefore be a cancel
they can recover from. The shot goes back to being generatable, unless it has
takes waiting to be looked at - in which case it goes back to needing review,
which is where a shot with unreviewed takes belongs.
"""

import uuid

from app.models import GenerationJob, Take


def _queued_job(db, shot_id: str, status: str = "Running") -> GenerationJob:
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=shot_id, status=status,
        parameter_map={}, seed=1,
    )
    db.add(job)
    db.commit()
    return job


def test_cancelling_the_only_job_makes_the_shot_generatable_again(
    client, db_session, sample_project, sample_shot,
):
    """The production failure, in one test."""
    sample_shot.status = "Generating"
    db_session.commit()
    job = _queued_job(db_session, sample_shot.id)

    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 200

    db_session.refresh(sample_shot)
    assert sample_shot.status == "Ready"

    queued = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert queued.status_code == 200, queued.text


def test_a_shot_with_takes_to_look_at_goes_back_to_needing_review(
    client, db_session, sample_shot,
):
    """Not every cancelled shot is empty. One that already produced a take
    somebody has not judged is not "ready" - it is waiting on a person."""
    sample_shot.status = "Generating"
    db_session.add(Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id,
        file_path="C:/tmp/earlier.png", review_status="Pending",
    ))
    db_session.commit()
    job = _queued_job(db_session, sample_shot.id)

    client.post(f"/api/jobs/{job.id}/cancel")

    db_session.refresh(sample_shot)
    assert sample_shot.status == "NeedsReview"


def test_a_shot_still_rendering_something_else_stays_generating(
    client, db_session, sample_shot,
):
    """Two jobs for one shot is unusual but reachable. Cancelling one of them
    must not tell the queue that the other has stopped."""
    sample_shot.status = "Generating"
    db_session.commit()
    first = _queued_job(db_session, sample_shot.id)
    _queued_job(db_session, sample_shot.id, status="Queued")

    client.post(f"/api/jobs/{first.id}/cancel")

    db_session.refresh(sample_shot)
    assert sample_shot.status == "Generating"


def test_cancelling_does_not_disturb_a_shot_that_was_already_approved(
    client, db_session, sample_shot,
):
    """A stray job against an approved shot is a bookkeeping problem. Undoing
    somebody's approval to tidy it up would be a much larger one."""
    sample_shot.status = "Approved"
    db_session.commit()
    job = _queued_job(db_session, sample_shot.id)

    client.post(f"/api/jobs/{job.id}/cancel")

    db_session.refresh(sample_shot)
    assert sample_shot.status == "Approved"
