"""Generation consumes the exact conditioning set that preflight validates."""

import os
import uuid

from app.models import GenerationJob, Take, Workflow
from app.services import (
    character_sets,
    continuity_frames,
    job_payload,
    revisions,
    workflow_registry,
)


def _approved_set(db, project_id, character_id, png_bytes):
    character_set = character_sets.create_set(
        db,
        project_id=project_id,
        character_id=character_id,
        name="Mara",
        appearance="Silver hair",
    )
    version = character_sets.create_version(db, character_set, slots=["front"])
    view = character_sets.list_views(db, version)[0]
    character_sets.attach_view_image(
        db,
        view,
        data=png_bytes(64, 64),
        content_type="image/png",
        original_filename="front.png",
        provenance={"provider_id": "mock", "seed": 7},
    )
    character_sets.approve_version(db, version)
    return character_set, view


def test_preflight_and_generate_block_a_bound_set_with_no_approved_version(
    client, db_session, sample_project, sample_character, sample_shot
):
    character_set = character_sets.create_set(
        db_session,
        project_id=sample_project.id,
        character_id=sample_character.id,
        name="Mara",
    )
    sample_shot.character_set_ids = [character_set.id]
    sample_shot.status = "Ready"
    db_session.commit()

    preflight = client.get(f"/api/projects/{sample_project.id}/preflight").json()
    issues = next(item for item in preflight["issues"] if item["shot_id"] == sample_shot.id)
    assert any("no approved canonical version" in text for text in issues["issues"])

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 409, response.text
    assert "no approved canonical version" in response.json()["detail"]
    assert db_session.query(GenerationJob).count() == 0


def test_generate_records_canonical_images_and_exact_identity_lineage(
    client, db_session, sample_project, sample_character, sample_shot, png_bytes,
    sample_workflow_json,
):
    character_set, view = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes
    )
    sample_shot.character_set_ids = [character_set.id]
    sample_shot.status = "Ready"
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Reference image", purpose="image"
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "ckpt_name"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    db_session.add(workflow)
    sample_shot.workflow_preset_id = workflow.id
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 200, response.text
    job = response.json()[0]
    assert job["character_set_ids"] == [character_set.id]
    assert job["character_set_sha256s"] == [
        character_sets.canonical_digest(db_session, character_set)
    ]
    assert job["reference_image_ids"] == []
    image = job["reference_provenance"]["images"][0]
    assert image["image_id"] == view.reference_image_id
    assert image["source"] == "character_set"
    assert image["detail"]["character_set_id"] == character_set.id
    assert image["detail"]["character_set_version_id"]
    assert image["detail"]["view_slot"] == "front"


def test_only_shots_bound_to_a_reapproved_set_are_invalidated(
    client, db_session, sample_project, sample_scene, sample_character,
    sample_shot, png_bytes
):
    character_set, _ = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes
    )
    sample_shot.character_set_ids = [character_set.id]
    sample_shot.status = "Ready"
    independent = client.post(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots",
        json={"image_prompt": "independent", "status": "Ready"},
    ).json()
    db_session.commit()
    bound_revision = sample_shot.prompt_revision
    independent_revision = independent["prompt_revision"]

    version = character_sets.create_version(db_session, character_set, slots=["front"])
    character_sets.attach_view_image(
        db_session,
        character_sets.list_views(db_session, version)[0],
        data=png_bytes(80, 64),
        content_type="image/png",
        original_filename="new-front.png",
    )
    response = client.post(
        f"/api/projects/{sample_project.id}/character-sets/{character_set.id}"
        f"/versions/{version.id}/approve"
    )
    assert response.status_code == 200, response.text

    db_session.refresh(sample_shot)
    assert sample_shot.prompt_revision == bound_revision + 1
    unchanged = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}"
        f"/shots/{independent['id']}"
    ).json()
    assert unchanged["prompt_revision"] == independent_revision


def test_generate_records_the_bound_end_frame_as_the_i2v_provider_input(
    client, db_session, sample_project, sample_shot, sample_scene,
    sample_workflow_json, tmp_path, synthesise_clip,
):
    path = synthesise_clip(
        os.path.join(str(tmp_path), "source.mp4"),
        with_audio=False,
        duration=1.0,
        frame_rate=24.0,
        moving=True,
    )
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        file_path=path,
        duration_sec=1.0,
        review_status="Approved",
    )
    db_session.add(take)
    db_session.commit()
    frame = continuity_frames.extract_frame(db_session, take)

    next_shot = client.post(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots",
        json={
            "order": 2,
            "generation_mode": "image-to-video",
            "video_prompt": "continue the motion",
            "status": "Ready",
        },
    ).json()
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="I2V reference", purpose="video"
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "ckpt_name"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "video"}]
    db_session.add(workflow)
    sample_project.default_video_workflow_id = workflow.id
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)
    take.prompt_revision = sample_shot.prompt_revision
    take.prompt_sha256 = sample_shot.prompt_sha256
    take.content_sha256 = sample_shot.content_sha256
    db_session.commit()

    bound = client.put(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}"
        f"/shots/{next_shot['id']}/continuity",
        json={"source_take_id": take.id},
    )
    assert bound.status_code == 200, bound.text
    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [next_shot["id"]]},
    )
    assert response.status_code == 200, response.text
    job = response.json()[0]
    assert job["continuity_source_take_id"] == take.id
    assert job["continuity_source_sha256"] == frame.sha256
    image = job["reference_provenance"]["images"][0]
    assert image["image_id"] == frame.reference_image_id
    assert image["source"] == "continuity"
    assert image["detail"]["take_id"] == take.id