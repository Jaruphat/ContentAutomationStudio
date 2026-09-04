"""Generation consumes the exact conditioning set that preflight validates."""

import os
import uuid

from app.models import GenerationJob, Shot, Take, Workflow
from app.services import (
    character_sets,
    continuity_frames,
    job_payload,
    revisions,
    workflow_registry,
)


def _approved_set(db, project_id, character_id, png_bytes, *, slots=None):
    character_set = character_sets.create_set(
        db,
        project_id=project_id,
        character_id=character_id,
        name="Mara",
        appearance="Silver hair",
    )
    version = character_sets.create_version(
        db, character_set, slots=slots or ["front"]
    )
    views = character_sets.list_views(db, version)
    for index, view in enumerate(views):
        character_sets.attach_view_image(
            db,
            view,
            data=png_bytes(64 + index, 64),
            content_type="image/png",
            original_filename=f"{view.slot}.png",
            provenance={"provider_id": "mock", "seed": 7 + index},
        )
    character_sets.approve_version(db, version)
    return character_set, views[0]


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


def test_real_e2e_scene_topology_preflights_and_queues_one_primary_view(
    client, db_session, sample_project, sample_character, sample_shot, png_bytes,
    sample_workflow_json,
):
    character_set, _ = _approved_set(
        db_session,
        sample_project.id,
        sample_character.id,
        png_bytes,
        slots=["front", "full_body"],
    )
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Boogu one-input edit", purpose="image"
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
    sample_shot.character_set_ids = [character_set.id]
    sample_shot.status = "Ready"
    db_session.commit()

    preflight = client.get(f"/api/projects/{sample_project.id}/preflight").json()
    assert not any(
        issue["shot_id"] == sample_shot.id for issue in preflight["issues"]
    ), preflight

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 200, response.text
    job = response.json()[0]
    images = job["reference_provenance"]["images"]
    assert [item["detail"]["view_slot"] for item in images] == ["front", "full_body"]
    assert [item["submitted"] for item in images] == [False, True]
    assert job["character_set_sha256s"] == [
        character_sets.canonical_digest(db_session, character_set)
    ]


def test_preflight_and_generate_keep_multiple_character_sets_as_an_explicit_blocker(
    client, db_session, sample_project, sample_character, sample_shot, png_bytes,
    sample_workflow_json,
):
    first, _ = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes
    )
    second, _ = _approved_set(
        db_session, sample_project.id, None, png_bytes
    )
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="One-input edit", purpose="image"
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
    sample_shot.character_set_ids = [first.id, second.id]
    sample_shot.status = "Ready"
    db_session.commit()

    preflight = client.get(f"/api/projects/{sample_project.id}/preflight").json()
    issues = next(
        issue for issue in preflight["issues"] if issue["shot_id"] == sample_shot.id
    )
    assert any("multiple character sets" in issue for issue in issues["issues"])

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 409, response.text
    assert "multiple character sets" in response.json()["detail"]
    assert db_session.query(GenerationJob).count() == 0


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


def test_generate_uses_the_exact_approved_scene_image_as_first_i2v_reference(
    client, db_session, sample_project, sample_shot, sample_scene,
    sample_character, sample_workflow_json, tmp_path, png_bytes,
):
    path = os.path.join(str(tmp_path), "scene-image.png")
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
    db_session.add(take)
    db_session.commit()
    frame = continuity_frames.extract_frame(db_session, take)
    character_set, _ = _approved_set(
        db_session,
        sample_project.id,
        sample_character.id,
        png_bytes,
        slots=["front", "full_body"],
    )

    next_shot = client.post(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots",
        json={"order": 2, "generation_mode": "image-to-video",
              "video_prompt": "animate exact still", "status": "Ready"},
    ).json()
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="I2V image", purpose="video"
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
    next_shot_row = db_session.query(Shot).filter(Shot.id == next_shot["id"]).one()
    next_shot_row.character_set_ids = [character_set.id]
    db_session.commit()
    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [next_shot["id"]]},
    )
    assert response.status_code == 200, response.text
    job = response.json()[0]
    assert job["continuity_source_take_id"] == take.id
    assert job["continuity_source_sha256"] == frame.sha256
    images = job["reference_provenance"]["images"]
    first = images[0]
    assert first["image_id"] == frame.reference_image_id
    assert first["sha256"] == frame.sha256
    assert first["source"] == "continuity"
    assert first["detail"]["source_type"] == "approved_image_take"
    assert first["detail"]["selection"] == "source_image"
    assert [item["submitted"] for item in images] == [True, False, False]
    assert [item["detail"]["view_slot"] for item in images[1:]] == [
        "front", "full_body"
    ]
    assert job["character_set_sha256s"] == [
        character_sets.canonical_digest(db_session, character_set)
    ]

def test_an_i2v_shot_refuses_to_animate_the_canonical_identity_sheet(
    client, db_session, sample_project, sample_character, sample_shot, png_bytes,
):
    """The frame an image-to-video run animates is never a character sheet.

    For image-to-video the single submitted image is not conditioning, it is
    the first frame of the clip. A canonical view is a studio portrait on a
    plain backdrop, so animating it produces a shot of the reference sheet
    instead of the scene - and the run reports success, because every hash and
    lineage entry is correct. Only an explicitly chosen start frame (this
    shot's own approved image, or a bound continuity frame) can be the one
    that moves, so with none bound the run is refused rather than guessed.
    """
    character_set, _view = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes
    )
    sample_shot.character_set_ids = [character_set.id]
    sample_shot.generation_mode = "image-to-video"
    sample_shot.status = "Ready"
    db_session.commit()

    preflight = client.get(f"/api/projects/{sample_project.id}/preflight").json()
    issues = next(
        item for item in preflight["issues"] if item["shot_id"] == sample_shot.id
    )
    assert any("no start frame" in text for text in issues["issues"]), issues["issues"]

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 409, response.text
    assert "no start frame" in response.json()["detail"]
    assert db_session.query(GenerationJob).count() == 0
