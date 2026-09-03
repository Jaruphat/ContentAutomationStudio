"""Generation run batch identity.

A "run" is what the user actually pressed: one Generate produces one run, and
every job it created belongs to that run for the rest of its life. The row is
written once and never rewritten - progress lives on the jobs - so a run stays
a truthful record of what was requested even after retries, failures and
regenerations move the jobs around it.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect as sa_inspect

from app import paths
from app.models import GenerationJob, Shot, Take
from app.services import generation_runs


def _utc(offset_sec: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_sec)


def add_job(db, shot_id, *, run_id=None, status="Queued", created_at=None):
    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        run_id=run_id,
        status=status,
        created_at=created_at or _utc(),
    )
    db.add(job)
    db.commit()
    return job


def add_take(db, shot_id, *, job=None, run_id=None, file_path="", review_status="Pending"):
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        job_id=job.id if job else None,
        run_id=run_id,
        file_path=file_path,
        review_status=review_status,
    )
    db.add(take)
    db.commit()
    return take


def snapshot(row) -> dict:
    """Every persisted column value of a row, for immutability assertions."""
    return {
        c.key: getattr(row, c.key)
        for c in sa_inspect(row.__class__).mapper.column_attrs
    }


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_each_generate_gets_its_own_numbered_run(db_session, sample_project, sample_shot):
    first = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    second = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )

    assert first.id != second.id
    assert (first.sequence, second.sequence) == (1, 2)
    assert first.label == "Run 1"
    assert first.requested_job_count == 1
    assert first.shot_ids == [sample_shot.id]


def test_run_numbering_is_per_project(db_session, sample_project, sample_shot):
    from app.models import Project

    other = Project(id=str(uuid.uuid4()), title="Other")
    db_session.add(other)
    db_session.commit()

    generation_runs.create_run(db_session, sample_project.id, kind="batch", shot_ids=[])
    other_run = generation_runs.create_run(db_session, other.id, kind="batch", shot_ids=[])

    assert other_run.sequence == 1


def test_the_run_row_is_never_rewritten_as_its_jobs_progress(
    db_session, sample_project, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    job = add_job(db_session, sample_shot.id, run_id=run.id)
    before = snapshot(run)

    job.status = "Failed"
    db_session.commit()
    generation_runs.summarise_run(db_session, run)
    job.status = "Completed"
    db_session.commit()
    generation_runs.summarise_run(db_session, run)

    db_session.refresh(run)
    assert snapshot(run) == before


def test_a_regeneration_is_its_own_single_job_run(db_session, sample_project, sample_shot):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="regeneration", shot_ids=[sample_shot.id]
    )

    assert run.kind == "regeneration"
    assert run.requested_job_count == 1
    assert run.label == "Run 1 (regenerate)"


# ---------------------------------------------------------------------------
# Run-scoped counts
# ---------------------------------------------------------------------------

def test_counts_are_scoped_to_one_run(db_session, sample_project, sample_shot):
    first = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    second = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    add_job(db_session, sample_shot.id, run_id=first.id, status="Completed")
    add_job(db_session, sample_shot.id, run_id=first.id, status="Failed")
    add_job(db_session, sample_shot.id, run_id=second.id, status="Queued")

    summary = generation_runs.summarise_run(db_session, first)

    assert summary["total_jobs"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 1
    assert summary["queued"] == 0
    assert summary["running"] == 0
    assert summary["status"] == "Failed"
    assert summary["terminal"] is True


def test_a_run_with_queued_work_is_not_terminal(db_session, sample_project, sample_shot):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")
    add_job(db_session, sample_shot.id, run_id=run.id, status="Running")

    summary = generation_runs.summarise_run(db_session, run)

    assert summary["terminal"] is False
    assert summary["status"] == "Running"


def test_terminal_run_reports_takes_still_awaiting_review(
    db_session, sample_project, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    job = add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")
    add_take(db_session, sample_shot.id, job=job, run_id=run.id)
    add_take(
        db_session, sample_shot.id, job=job, run_id=run.id, review_status="Approved"
    )

    summary = generation_runs.summarise_run(db_session, run)

    assert summary["terminal"] is True
    assert summary["pending_take_count"] == 1
    assert summary["ready_for_review"] is True


def test_a_run_with_no_pending_takes_is_not_advertised_for_review(
    db_session, sample_project, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    add_job(db_session, sample_shot.id, run_id=run.id, status="Failed")

    summary = generation_runs.summarise_run(db_session, run)

    assert summary["pending_take_count"] == 0
    assert summary["ready_for_review"] is False


# ---------------------------------------------------------------------------
# Human-readable job rows
# ---------------------------------------------------------------------------

def test_jobs_are_named_by_scene_and_shot_not_only_ids(
    db_session, sample_project, sample_scene, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["scene_name"] == "Opening Scene"
    assert entry["shot_name"].startswith("Shot 1")
    assert "Alice" in entry["shot_name"]
    assert entry["shot_id"] == sample_shot.id
    assert entry["scene_id"] == sample_scene.id


def test_an_untitled_scene_still_gets_a_readable_name(
    db_session, sample_project, sample_scene, sample_shot
):
    sample_scene.title = ""
    sample_shot.subject = ""
    sample_shot.action = ""
    sample_shot.shot_type = ""
    db_session.commit()
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    add_job(db_session, sample_shot.id, run_id=run.id)

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["scene_name"] == "Scene 1"
    assert entry["shot_name"] == "Shot 1"


# ---------------------------------------------------------------------------
# Safe thumbnails
# ---------------------------------------------------------------------------

def test_thumbnail_url_is_offered_only_for_a_real_file_inside_the_data_dir(
    db_session, sample_project, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    job = add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")
    path = os.path.join(paths.generated_dir(), f"{uuid.uuid4()}.png")
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
    take = add_take(db_session, sample_shot.id, job=job, run_id=run.id, file_path=path)

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["take_id"] == take.id
    assert entry["thumbnail_url"] == f"/api/media/takes/{take.id}/file"
    assert entry["take_review_status"] == "Pending"


def test_a_take_outside_the_data_dir_gets_no_thumbnail_url(
    db_session, sample_project, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    job = add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")
    add_take(
        db_session,
        sample_shot.id,
        job=job,
        run_id=run.id,
        file_path=os.path.join(os.path.dirname(paths.data_dir()), "elsewhere.png"),
    )

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["thumbnail_url"] is None


def test_a_missing_file_gets_no_thumbnail_url(db_session, sample_project, sample_shot):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    job = add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")
    add_take(
        db_session,
        sample_shot.id,
        job=job,
        run_id=run.id,
        file_path=os.path.join(paths.generated_dir(), "never-written.png"),
    )

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["thumbnail_url"] is None


def test_a_job_without_a_take_reports_no_thumbnail(
    db_session, sample_project, sample_shot
):
    run = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    add_job(db_session, sample_shot.id, run_id=run.id, status="Queued")

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["take_id"] is None
    assert entry["thumbnail_url"] is None


# ---------------------------------------------------------------------------
# Duplicate active work
# ---------------------------------------------------------------------------

def test_shots_with_queued_or_running_jobs_are_reported_as_busy(
    db_session, sample_project, sample_scene, sample_shot
):
    idle = Shot(id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2)
    db_session.add(idle)
    db_session.commit()
    add_job(db_session, sample_shot.id, status="Running")
    add_job(db_session, idle.id, status="Completed")

    busy = generation_runs.shots_with_active_jobs(
        db_session, [sample_shot.id, idle.id]
    )

    assert busy == {sample_shot.id}


def test_active_job_lookup_can_exclude_the_job_being_retried(
    db_session, sample_project, sample_shot
):
    job = add_job(db_session, sample_shot.id, status="Queued")

    busy = generation_runs.shots_with_active_jobs(
        db_session, [sample_shot.id], exclude_job_id=job.id
    )

    assert busy == set()


def test_no_shot_ids_needs_no_query(db_session):
    assert generation_runs.shots_with_active_jobs(db_session, []) == set()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def test_history_lists_newest_run_first(db_session, sample_project, sample_shot):
    first = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )
    second = generation_runs.create_run(
        db_session, sample_project.id, kind="batch", shot_ids=[sample_shot.id]
    )

    runs = generation_runs.list_runs(db_session, sample_project.id)

    assert [run.id for run in runs] == [second.id, first.id]
    assert generation_runs.current_run(db_session, sample_project.id).id == second.id


def test_current_run_is_none_before_the_first_generate(db_session, sample_project):
    assert generation_runs.current_run(db_session, sample_project.id) is None


def test_video_take_uses_thumbnail_endpoint(db_session, sample_project, sample_shot):
    run = generation_runs.create_run(
        db_session, sample_project.id, shot_ids=[sample_shot.id]
    )
    job = add_job(db_session, sample_shot.id, run_id=run.id, status="Completed")
    video_path = os.path.join(paths.generated_dir(), f"{uuid.uuid4()}.mp4")
    with open(video_path, "wb") as handle:
        handle.write(b"video placeholder")
    take = add_take(
        db_session, sample_shot.id, job=job, run_id=run.id, file_path=video_path
    )

    entry = generation_runs.summarise_run(db_session, run)["jobs"][0]

    assert entry["thumbnail_url"] == f"/api/media/takes/{take.id}/thumbnail"


