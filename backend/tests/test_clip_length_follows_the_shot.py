"""A clip should be as long as the shot that asked for it.

Every clip in a delivered episode was 5.167 seconds, because the workflow's
frame count was baked into the graph and never mapped. The cut then trimmed
each one to the length the edit wanted - 4, 3, 3, 4, 3, 4, 3, 3, 5 seconds - so
the film's pacing was right and **31% of the GPU time rendered frames nobody
would ever see**: 14.5 of the 46.5 seconds generated.

It also put a ceiling on the edit. No shot could run past 5.167 seconds, and
the episode's closing shot wanted 5.0, which left a sixth of a second of
headroom on the payoff.

The length is computed from the shot's planned duration and the frame rate the
*graph* renders at, not the project's delivery rate. A graph tagged 24 fps
given a project's 30 makes a clip a quarter longer than the shot asked for,
which is the same waste with an extra step. When a workflow does not say what
rate it runs at, the project's rate is the only estimate available and is used
as one.

Both the queue and Regenerate compute this. They are one function, because the
last time two paths built the same request separately, one of them fell behind
and nine clips were generated with no motion described.
"""

import uuid

import pytest

from app.models import Shot, Workflow
from app.services import generation_planning


@pytest.mark.parametrize("planned,rate,expected", [
    (3.0, 24.0, 72),
    (4.0, 24.0, 96),
    (5.0, 24.0, 120),
    (3.0, 30.0, 90),
    (0.5, 24.0, 12),
])
def test_the_frame_count_is_the_shot_length_at_the_graphs_rate(
    planned, rate, expected,
):
    assert generation_planning.frames_for(
        planned_duration_sec=planned, workflow_frame_rate=rate,
        project_frame_rate=30.0,
    ) == expected


def test_the_projects_rate_is_used_only_when_the_graph_does_not_say():
    """An estimate, and named as one. A graph tagged 24 fps handed a project's
    30 produces a clip a quarter longer than the shot asked for."""
    assert generation_planning.frames_for(
        planned_duration_sec=3.0, workflow_frame_rate=0.0,
        project_frame_rate=30.0,
    ) == 90


def test_a_shot_with_no_planned_duration_still_gets_a_clip():
    assert generation_planning.frames_for(
        planned_duration_sec=0.0, workflow_frame_rate=24.0,
        project_frame_rate=30.0,
    ) == 72


def test_at_least_one_frame_is_always_asked_for():
    assert generation_planning.frames_for(
        planned_duration_sec=0.01, workflow_frame_rate=1.0,
        project_frame_rate=1.0,
    ) == 1


# ---------------------------------------------------------------------------
# What actually reaches a queued job
# ---------------------------------------------------------------------------

def _video_workflow(db, sample_workflow_json, frame_rate: float) -> Workflow:
    from app.services import job_payload, workflow_registry

    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="H3 I2V", purpose="text-to-video",
    )
    workflow = Workflow(**record)
    workflow.frame_rate = frame_rate
    workflow.validation_status = "valid"
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.FRAMES: {"nodeId": "3", "field": "steps"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "video"}]
    db.add(workflow)
    db.commit()
    return workflow


def _video_shot(db, scene, seconds: float) -> Shot:
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=1, status="Ready",
        generation_mode="video", planned_duration_sec=seconds,
        subject_motion="The door swings open.",
    )
    db.add(shot)
    db.commit()
    return shot


def test_a_three_second_shot_asks_for_three_seconds_of_frames(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    from app.services import job_payload

    workflow = _video_workflow(db_session, sample_workflow_json, 24.0)
    sample_project.default_video_workflow_id = workflow.id
    sample_project.frame_rate = 30.0
    shot = _video_shot(db_session, sample_scene, 3.0)
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [shot.id]},
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["parameter_map"][job_payload.FRAMES] == 72


def test_regenerating_asks_for_the_same_length_as_generating(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    """Two paths, one answer. The last time they were computed separately, one
    of them fell behind and nobody found out until the clips came back."""
    from app.models import Take
    from app.services import job_payload

    workflow = _video_workflow(db_session, sample_workflow_json, 24.0)
    sample_project.default_video_workflow_id = workflow.id
    sample_project.frame_rate = 30.0
    shot = _video_shot(db_session, sample_scene, 4.0)
    db_session.add(Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="C:/tmp/old.mp4",
        review_status="Rejected",
    ))
    db_session.commit()

    regenerated = client.post(f"/api/shots/{shot.id}/regenerate")

    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["parameter_map"][job_payload.FRAMES] == 96


def test_a_still_asks_for_no_frames_at_all(
    client, db_session, sample_project, sample_shot,
):
    from app.services import job_payload

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 200, response.text
    assert job_payload.FRAMES not in response.json()[0]["parameter_map"]


def test_a_workflow_written_before_the_column_reads_back_as_unknown(
    client, db_session, sample_workflow_json,
):
    """ADD COLUMN can only be NULL, so every workflow registered before this
    carries None and must not fail a plain GET."""
    from sqlalchemy import text

    workflow = _video_workflow(db_session, sample_workflow_json, 24.0)
    db_session.execute(
        text("UPDATE workflows SET frame_rate = NULL WHERE id = :id"),
        {"id": workflow.id},
    )
    db_session.commit()

    response = client.get(f"/api/workflows/{workflow.id}")

    assert response.status_code == 200, response.text
    assert response.json()["frame_rate"] == 0.0
