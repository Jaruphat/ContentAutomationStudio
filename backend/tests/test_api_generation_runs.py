"""Generation run API contract.

What the Generate page needs to answer honestly: which run is happening now,
what happened in the ones before it, and which of its jobs are still to be
reviewed. Runs are read-only over the API - only Generate, Regenerate and the
queue ever write them.
"""

import uuid

import pytest

from app.models import GenerationJob, GenerationRun, Shot, Take


def second_shot(client, project_id, scene_id) -> str:
    response = client.post(
        f"/api/projects/{project_id}/scenes/{scene_id}/shots",
        json={"order": 2, "subject": "Bob", "image_prompt": "a second prompt"},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


# ---------------------------------------------------------------------------
# One Generate, one run
# ---------------------------------------------------------------------------

def test_all_jobs_from_one_generate_share_a_run_id(
    client, db_session, sample_project, sample_scene, sample_shot
):
    other = second_shot(client, sample_project.id, sample_scene.id)

    response = client.post(f"/api/projects/{sample_project.id}/generate", json={})

    assert response.status_code == 200, response.text
    jobs = response.json()
    assert len(jobs) == 2
    run_ids = {job["run_id"] for job in jobs}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    assert run_id
    run = db_session.query(GenerationRun).filter(GenerationRun.id == run_id).one()
    assert run.project_id == sample_project.id
    assert run.kind == "batch"
    assert run.requested_job_count == 2
    assert sorted(run.shot_ids) == sorted([sample_shot.id, other])


def test_a_second_generate_starts_a_new_run(
    client, db_session, sample_project, sample_scene, sample_shot
):
    first = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    first_run = first.json()[0]["run_id"]

    # The first run's job has to leave the queue before its shot can be
    # generated again; a run boundary is not an excuse to double-queue a shot.
    job = db_session.query(GenerationJob).one()
    job.status = "Completed"
    shot = db_session.query(Shot).filter(Shot.id == sample_shot.id).one()
    shot.status = "NeedsReview"
    db_session.commit()

    second = client.post(f"/api/projects/{sample_project.id}/generate", json={})

    assert second.status_code == 200, second.text
    assert second.json()[0]["run_id"] != first_run


def test_regeneration_is_its_own_single_job_run(
    client, db_session, sample_project, sample_scene, sample_shot
):
    batch = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    batch_run = batch.json()[0]["run_id"]
    job = db_session.query(GenerationJob).one()
    job.status = "Completed"
    db_session.commit()

    response = client.post(f"/api/shots/{sample_shot.id}/regenerate", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] and body["run_id"] != batch_run
    run = (
        db_session.query(GenerationRun)
        .filter(GenerationRun.id == body["run_id"])
        .one()
    )
    assert run.kind == "regeneration"
    assert run.requested_job_count == 1
    assert run.shot_ids == [sample_shot.id]


def test_retrying_a_job_keeps_it_in_its_original_run(
    client, db_session, sample_project, sample_scene, sample_shot
):
    created = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    job_id = created.json()[0]["id"]
    run_id = created.json()[0]["run_id"]
    job = db_session.query(GenerationJob).filter(GenerationJob.id == job_id).one()
    job.status = "Failed"
    db_session.commit()

    response = client.post(f"/api/jobs/{job_id}/retry")

    assert response.status_code == 200, response.text
    assert response.json()["run_id"] == run_id
    assert response.json()["status"] == "Queued"


def test_retry_refuses_when_another_job_for_the_shot_is_active(
    client, db_session, sample_project, sample_scene, sample_shot
):
    created = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    failed = db_session.query(GenerationJob).filter(
        GenerationJob.id == created.json()[0]["id"]
    ).one()
    failed.status = "Failed"
    competing = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        run_id=failed.run_id,
        status="Running",
    )
    db_session.add(competing)
    db_session.commit()

    response = client.post(f"/api/jobs/{failed.id}/retry")

    assert response.status_code == 409
    assert "another" in response.json()["detail"].lower()
    db_session.refresh(failed)
    assert failed.status == "Failed"
    assert db_session.query(GenerationJob).count() == 2


# ---------------------------------------------------------------------------
# Duplicate active jobs
# ---------------------------------------------------------------------------

def test_generate_does_not_queue_a_shot_that_is_already_running(
    client, db_session, sample_project, sample_scene, sample_shot
):
    other = second_shot(client, sample_project.id, sample_scene.id)
    client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    # Put the shot back in an eligible state while its job is still queued:
    # exactly the drift a duplicate-job guard exists to catch.
    shot = db_session.query(Shot).filter(Shot.id == sample_shot.id).one()
    shot.status = "Ready"
    db_session.commit()

    response = client.post(f"/api/projects/{sample_project.id}/generate", json={})

    assert response.status_code == 200, response.text
    queued_shots = [job["shot_id"] for job in response.json()]
    assert queued_shots == [other]
    assert (
        db_session.query(GenerationJob)
        .filter(GenerationJob.shot_id == sample_shot.id)
        .count()
        == 1
    )


def test_generate_refuses_when_every_selected_shot_is_already_active(
    client, db_session, sample_project, sample_scene, sample_shot
):
    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    shot = db_session.query(Shot).filter(Shot.id == sample_shot.id).one()
    shot.status = "Ready"
    db_session.commit()

    response = client.post(f"/api/projects/{sample_project.id}/generate", json={})

    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()
    assert db_session.query(GenerationJob).count() == 1


def test_regenerate_refuses_while_the_shot_still_has_an_active_job(
    client, db_session, sample_project, sample_scene, sample_shot
):
    client.post(f"/api/projects/{sample_project.id}/generate", json={})

    response = client.post(f"/api/shots/{sample_shot.id}/regenerate", json={})

    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()
    assert db_session.query(GenerationJob).count() == 1
    # A refused regeneration must not leave an orphan run behind.
    assert db_session.query(GenerationRun).count() == 1


# ---------------------------------------------------------------------------
# Current run and history
# ---------------------------------------------------------------------------

def test_current_run_is_the_newest_one_with_scoped_counts(
    client, db_session, sample_project, sample_scene, sample_shot
):
    other = second_shot(client, sample_project.id, sample_scene.id)
    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    jobs = db_session.query(GenerationJob).all()
    jobs[0].status = "Completed"
    jobs[1].status = "Failed"
    db_session.commit()

    response = client.get(f"/api/projects/{sample_project.id}/runs/current")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_jobs"] == 2
    assert body["completed"] == 1
    assert body["failed"] == 1
    assert body["queued"] == 0
    assert body["terminal"] is True
    assert body["label"] == "Run 1"
    assert {entry["shot_id"] for entry in body["jobs"]} == {sample_shot.id, other}


def test_completed_and_cancelled_run_reports_cancelled_not_completed(
    client, db_session, sample_project, sample_scene, sample_shot
):
    second_shot(client, sample_project.id, sample_scene.id)
    created = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    jobs = db_session.query(GenerationJob).all()
    jobs[0].status = "Completed"
    jobs[1].status = "Cancelled"
    db_session.commit()

    body = client.get(f"/api/runs/{created.json()[0]['run_id']}").json()

    assert body["status"] == "Cancelled"
    assert body["completed"] == 1
    assert body["cancelled"] == 1


def test_current_run_is_null_before_anything_was_generated(client, sample_project):
    response = client.get(f"/api/projects/{sample_project.id}/runs/current")

    assert response.status_code == 200
    assert response.json() is None


def test_run_jobs_carry_scene_and_shot_names_and_a_safe_thumbnail_url(
    client, db_session, sample_project, sample_scene, sample_shot
):
    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    job = db_session.query(GenerationJob).one()
    job.status = "Completed"
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        job_id=job.id,
        run_id=job.run_id,
        file_path="C:/somewhere/outside/the/data/dir.png",
        review_status="Pending",
    )
    db_session.add(take)
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/runs/current").json()
    entry = body["jobs"][0]

    assert entry["scene_name"] == "Opening Scene"
    assert "Alice" in entry["shot_name"]
    assert entry["take_id"] == take.id
    # The file is outside the runtime data directory, so no URL is published.
    assert entry["thumbnail_url"] is None
    assert body["pending_take_count"] == 1
    assert body["ready_for_review"] is True


def test_history_returns_every_run_newest_first(
    client, db_session, sample_project, sample_scene, sample_shot
):
    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    job = db_session.query(GenerationJob).one()
    job.status = "Completed"
    db_session.commit()
    client.post(f"/api/shots/{sample_shot.id}/regenerate", json={})

    response = client.get(f"/api/projects/{sample_project.id}/runs")

    assert response.status_code == 200, response.text
    runs = response.json()
    assert len(runs) == 2
    assert [run["sequence"] for run in runs] == [2, 1]
    assert [run["kind"] for run in runs] == ["regeneration", "batch"]


def test_history_can_be_filtered_by_run_status(
    client, db_session, sample_project, sample_scene, sample_shot
):
    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    first_job = db_session.query(GenerationJob).one()
    first_job.status = "Failed"
    db_session.commit()
    client.post(f"/api/shots/{sample_shot.id}/regenerate", json={})

    failed = client.get(
        f"/api/projects/{sample_project.id}/runs", params={"status": "failed"}
    ).json()
    active = client.get(
        f"/api/projects/{sample_project.id}/runs", params={"status": "active"}
    ).json()

    assert [run["sequence"] for run in failed] == [1]
    assert [run["sequence"] for run in active] == [2]


def test_a_single_run_can_be_fetched_and_its_jobs_filtered_by_status(
    client, db_session, sample_project, sample_scene, sample_shot
):
    second_shot(client, sample_project.id, sample_scene.id)
    created = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    run_id = created.json()[0]["run_id"]
    jobs = db_session.query(GenerationJob).all()
    jobs[0].status = "Completed"
    jobs[1].status = "Failed"
    db_session.commit()

    whole = client.get(f"/api/runs/{run_id}").json()
    only_failed = client.get(f"/api/runs/{run_id}", params={"status": "Failed"}).json()

    assert len(whole["jobs"]) == 2
    assert [entry["status"] for entry in only_failed["jobs"]] == ["Failed"]
    # Filtering the view must not change the run's own counts.
    assert only_failed["total_jobs"] == 2
    assert only_failed["completed"] == 1


def test_unknown_run_is_a_404(client):
    assert client.get(f"/api/runs/{uuid.uuid4()}").status_code == 404


def test_jobs_endpoint_accepts_run_and_status_filters(
    client, db_session, sample_project, sample_scene, sample_shot
):
    second_shot(client, sample_project.id, sample_scene.id)
    created = client.post(f"/api/projects/{sample_project.id}/generate", json={})
    run_id = created.json()[0]["run_id"]
    jobs = db_session.query(GenerationJob).all()
    jobs[0].status = "Failed"
    db_session.commit()

    everything = client.get(f"/api/projects/{sample_project.id}/jobs").json()
    scoped = client.get(
        f"/api/projects/{sample_project.id}/jobs",
        params={"run_id": run_id, "status": "Failed"},
    ).json()

    assert len(everything) == 2
    assert len(scoped) == 1
    assert scoped[0]["status"] == "Failed"
    assert scoped[0]["run_id"] == run_id


# ---------------------------------------------------------------------------
# Review filtering
# ---------------------------------------------------------------------------

def test_takes_can_be_filtered_to_one_run(
    client, db_session, sample_project, sample_scene, sample_shot
):
    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    job = db_session.query(GenerationJob).one()
    job.status = "Completed"
    run_id = job.run_id
    kept = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        job_id=job.id,
        run_id=run_id,
        review_status="Pending",
    )
    older = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        job_id=None,
        run_id=None,
        review_status="Pending",
    )
    db_session.add_all([kept, older])
    db_session.commit()

    scoped = client.get(
        f"/api/projects/{sample_project.id}/takes", params={"run": run_id}
    ).json()
    everything = client.get(f"/api/projects/{sample_project.id}/takes").json()

    assert [take["id"] for take in scoped] == [kept.id]
    assert len(everything) == 2
    assert scoped[0]["run_id"] == run_id


@pytest.mark.asyncio
async def test_a_completed_take_records_the_run_that_produced_it(
    client, db_session, sample_project, sample_scene, sample_shot, tmp_path, monkeypatch
):
    """The queue copies the run onto the take, so Review can filter by run."""
    from app.services import mock_provider as mock_provider_module
    from app.services import queue_manager as qm_module
    from app.services.mock_provider import MockComfyUIProvider
    from app.services.queue_manager import QueueManager

    monkeypatch.setattr(qm_module, "POLL_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(mock_provider_module, "QUEUED_SEC", 0.0)
    monkeypatch.setattr(mock_provider_module, "RUNNING_SEC", 0.0)

    client.post(f"/api/projects/{sample_project.id}/generate", json={})
    job = db_session.query(GenerationJob).one()
    run_id = job.run_id

    manager = QueueManager(
        provider=MockComfyUIProvider(output_base_dir=str(tmp_path / "generated"))
    )
    manager._running = True
    await manager._execute_job(db_session, job)

    take = db_session.query(Take).filter(Take.job_id == job.id).one()
    assert take.run_id == run_id

