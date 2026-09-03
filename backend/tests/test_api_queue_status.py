"""Read-only project queue status API contract."""

from app.routers import generation


def test_get_queue_status_reports_backend_pause_and_counts_without_mutating(
    client, sample_project, monkeypatch
):
    expected = {
        "paused": True,
        "total_jobs": 13,
        "queued": 3,
        "running": 0,
        "completed": 10,
        "failed": 0,
        "cancelled": 0,
    }
    calls = []

    def get_status(project_id: str):
        calls.append(project_id)
        return expected

    monkeypatch.setattr(generation.queue_manager, "get_queue_status", get_status)

    response = client.get(f"/api/projects/{sample_project.id}/queue/status")

    assert response.status_code == 200
    assert response.json() == expected
    assert calls == [sample_project.id]


def test_pause_endpoint_persists_project_state(
    client, db_session, sample_project, monkeypatch
):
    monkeypatch.setattr(
        generation.queue_manager,
        "get_queue_status",
        lambda _project_id: {
            "paused": True,
            "total_jobs": 0,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    try:
        response = client.post(f"/api/projects/{sample_project.id}/queue/pause")
        db_session.refresh(sample_project)

        assert response.status_code == 200
        assert sample_project.queue_paused is True
    finally:
        # Clean only the isolated singleton memory; never call the resume API.
        generation.queue_manager._paused_projects.discard(sample_project.id)


def test_resume_endpoint_clears_persisted_project_pause(
    client, db_session, sample_project, monkeypatch
):
    sample_project.queue_paused = True
    db_session.commit()
    generation.queue_manager.pause(sample_project.id)
    monkeypatch.setattr(
        generation.queue_manager,
        "get_queue_status",
        lambda _project_id: {
            "paused": False,
            "total_jobs": 0,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    try:
        response = client.post(f"/api/projects/{sample_project.id}/queue/resume")
        db_session.refresh(sample_project)

        assert response.status_code == 200
        assert sample_project.queue_paused is False
    finally:
        generation.queue_manager._paused_projects.discard(sample_project.id)
