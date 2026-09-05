"""How long a run will take, from how long the same route took before.

Cost is answered before a run and time is not, which on local hardware is the
wrong way round: nothing here is billed and a shot takes minutes. Twenty-three
shots is an hour on this machine, and the only way to find that out was to
start one and watch.

The estimate is measured, never assumed. It comes from the completed jobs of
the same workflow, and where there is no history it says so rather than
guessing - an invented duration is worse than an absent one, because somebody
plans an evening around it.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models import GenerationJob
from app.services import run_duration


def _job(db, shot_id, workflow_id, seconds, *, status="Completed", offset_min=0):
    started = datetime.now(timezone.utc) - timedelta(minutes=offset_min)
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=shot_id, workflow_id=workflow_id,
        parameter_map={}, seed=1, status=status,
        started_at=started,
        completed_at=started + timedelta(seconds=seconds) if seconds else None,
    )
    db.add(job)
    db.commit()
    return job


def test_a_route_nobody_has_run_has_no_estimate(db_session, sample_shot):
    """Silence rather than a guess: an evening gets planned around this."""
    assert run_duration.seconds_for_workflow(db_session, "never-run") is None


def test_the_estimate_is_the_median_of_what_that_workflow_actually_took(
    db_session, sample_shot,
):
    for seconds in (150, 160, 170):
        _job(db_session, sample_shot.id, "wf-1", seconds)
    assert run_duration.seconds_for_workflow(db_session, "wf-1") == 160


def test_one_slow_outlier_does_not_move_the_estimate_much(
    db_session, sample_shot,
):
    """A median, not a mean: one job that waited behind a model load should
    not make every later prediction wrong."""
    for seconds in (150, 155, 160, 165, 4000):
        _job(db_session, sample_shot.id, "wf-2", seconds)
    assert run_duration.seconds_for_workflow(db_session, "wf-2") == 160


def test_only_completed_jobs_count(db_session, sample_shot):
    """A failed job's elapsed time measures how long it took to break."""
    _job(db_session, sample_shot.id, "wf-3", 150)
    _job(db_session, sample_shot.id, "wf-3", 5, status="Failed")
    _job(db_session, sample_shot.id, "wf-3", None, status="Running")
    assert run_duration.seconds_for_workflow(db_session, "wf-3") == 150


def test_recent_runs_are_preferred_over_old_ones(db_session, sample_shot):
    """Hardware, models and step counts change; last week is not evidence."""
    for _ in range(6):
        _job(db_session, sample_shot.id, "wf-4", 600, offset_min=60 * 24 * 30)
    for _ in range(6):
        _job(db_session, sample_shot.id, "wf-4", 150, offset_min=1)
    assert run_duration.seconds_for_workflow(db_session, "wf-4") == 150


def test_a_whole_run_is_the_sum_of_its_shots(db_session, sample_shot):
    for seconds in (150, 160, 170):
        _job(db_session, sample_shot.id, "wf-5", seconds)

    estimate = run_duration.estimate_run(db_session, ["wf-5", "wf-5", "wf-5"])

    assert estimate["seconds"] == 480
    assert estimate["known_shots"] == 3
    assert estimate["unknown_shots"] == 0


def test_shots_on_an_unmeasured_route_are_counted_but_not_invented(
    db_session, sample_shot,
):
    """A partial total is never presented as a complete one."""
    for seconds in (150, 160, 170):
        _job(db_session, sample_shot.id, "wf-6", seconds)

    estimate = run_duration.estimate_run(db_session, ["wf-6", "wf-unmeasured"])

    assert estimate["seconds"] == 160
    assert estimate["known_shots"] == 1
    assert estimate["unknown_shots"] == 1


def test_a_run_with_no_history_at_all_reports_no_time(db_session, sample_shot):
    estimate = run_duration.estimate_run(db_session, ["wf-new", "wf-new"])
    assert estimate["seconds"] is None
    assert estimate["unknown_shots"] == 2
