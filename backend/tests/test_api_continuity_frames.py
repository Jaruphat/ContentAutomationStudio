"""HTTP contracts for explicit end-frame continuity."""

import os
import uuid

import pytest

from app.models import Project, Scene, Shot, Take
from app.services import revisions


@pytest.fixture()
def continuity_storyboard(
    db_session, sample_project, sample_scene, sample_shot, tmp_path, synthesise_clip
):
    source_path = synthesise_clip(
        os.path.join(str(tmp_path), "source.mp4"),
        with_audio=False,
        duration=1.0,
        frame_rate=24.0,
        moving=True,
    )
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        file_path=source_path,
        duration_sec=1.0,
        review_status="Approved",
    )
    next_shot = Shot(
        id=str(uuid.uuid4()),
        scene_id=sample_scene.id,
        order=2,
        generation_mode="image-to-video",
        video_prompt="continue the movement",
        status="Ready",
    )
    db_session.add_all([take, next_shot])
    db_session.commit()
    return take, next_shot


def _shot_continuity_url(project, scene, shot):
    return (
        f"/api/projects/{project.id}/scenes/{scene.id}/shots/{shot.id}/continuity"
    )


def test_extract_list_bind_and_clear_a_continuity_frame_over_http(
    client, sample_project, sample_scene, continuity_storyboard
):
    take, next_shot = continuity_storyboard
    extract = client.post(
        f"/api/projects/{sample_project.id}/takes/{take.id}/continuity-frame",
        json={},
    )
    assert extract.status_code == 201, extract.text
    frame = extract.json()
    assert frame["take_id"] == take.id
    assert frame["selection"] == "last"
    assert frame["sha256"]
    assert client.get(frame["url"]).status_code == 200

    url = _shot_continuity_url(sample_project, sample_scene, next_shot)
    initial = client.get(url)
    assert initial.status_code == 200, initial.text
    assert [item["take_id"] for item in initial.json()["candidates"]] == [take.id]

    bound = client.put(url, json={"source_take_id": take.id})
    assert bound.status_code == 200, bound.text
    assert bound.json()["mode"] == "end_frame"
    assert bound.json()["source_take_id"] == take.id
    assert bound.json()["frame"]["sha256"] == frame["sha256"]

    cleared = client.delete(url)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["mode"] == "none"
    assert cleared.json()["source_take_id"] is None


def test_a_foreign_project_cannot_extract_or_bind_a_take(
    client, db_session, sample_project, sample_scene, continuity_storyboard
):
    take, next_shot = continuity_storyboard
    other = Project(id=str(uuid.uuid4()), title="Other")
    other_scene = Scene(id=str(uuid.uuid4()), project_id=other.id, title="Other")
    db_session.add_all([other, other_scene])
    db_session.commit()

    extracted = client.post(
        f"/api/projects/{other.id}/takes/{take.id}/continuity-frame", json={}
    )
    assert extracted.status_code == 404

    url = _shot_continuity_url(sample_project, sample_scene, next_shot)
    # The source remains project-scoped even if a caller guesses a real id.
    foreign_take = Take(
        id=str(uuid.uuid4()),
        shot_id=Shot(
            id=str(uuid.uuid4()), scene_id=other_scene.id, order=1,
            image_prompt="foreign",
        ).id,
        file_path=take.file_path,
        review_status="Approved",
    )
    # Persist the owning shot and take together.
    db_session.add(Shot(
        id=foreign_take.shot_id, scene_id=other_scene.id, order=1,
        image_prompt="foreign",
    ))
    db_session.add(foreign_take)
    db_session.commit()
    response = client.put(url, json={"source_take_id": foreign_take.id})
    assert response.status_code == 404


def test_extract_refuses_an_unapproved_take_without_creating_a_frame(
    client, db_session, sample_project, continuity_storyboard
):
    take, _ = continuity_storyboard
    take.review_status = "Rejected"
    db_session.commit()
    response = client.post(
        f"/api/projects/{sample_project.id}/takes/{take.id}/continuity-frame",
        json={},
    )
    assert response.status_code == 409
    assert "approved" in response.json()["detail"].lower()


def test_capture_and_bind_an_approved_scene_image_over_the_same_routes(
    client, db_session, sample_project, sample_scene, sample_shot, png_bytes,
    tmp_path,
):
    path = os.path.join(str(tmp_path), "approved-scene.png")
    data = png_bytes(96, 64)
    with open(path, "wb") as f:
        f.write(data)
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=path,
        review_status="Approved", prompt_revision=sample_shot.prompt_revision,
        prompt_sha256=sample_shot.prompt_sha256,
        content_sha256=sample_shot.content_sha256,
        lineage={"job_id": "scene-image"},
    )
    target = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
        generation_mode="image-to-video", video_prompt="animate exact still",
    )
    db_session.add_all([take, target])
    db_session.commit()

    url = _shot_continuity_url(sample_project, sample_scene, target)
    before_capture = client.get(url)
    assert before_capture.status_code == 200, before_capture.text
    option = before_capture.json()["candidates"][0]
    assert option["take_id"] == take.id
    assert option["source_type"] == "approved_image_take"
    assert option["captured"] is False
    assert option["frame"] is None

    captured = client.post(
        f"/api/projects/{sample_project.id}/takes/{take.id}/continuity-frame",
        json={},
    )
    assert captured.status_code == 201, captured.text
    assert captured.json()["selection"] == "source_image"
    assert captured.json()["source_type"] == "approved_image_take"
    assert captured.json()["frame_time_sec"] == 0.0

    status = client.get(url)
    assert status.status_code == 200, status.text
    candidate = status.json()["candidates"][0]
    assert candidate["captured"] is True
    assert candidate["source_type"] == "approved_image_take"
    assert candidate["source_label"] == "Approved scene image"

    bound = client.put(url, json={"source_take_id": take.id})
    assert bound.status_code == 200, bound.text
    assert bound.json()["mode"] == "start_frame"
    assert bound.json()["source_type"] == "approved_image_take"
