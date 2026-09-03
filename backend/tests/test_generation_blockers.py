"""POST /generate enforces the same blockers preflight reports.

Preflight is a page the UI visits, not a gate the API enforces. Anything that
can queue a job - a script, a retry loop, a second tab - reaches this endpoint
directly, so the endpoint has to refuse what preflight would have refused.

And it has to refuse the batch, not part of it: queueing the valid half of a
run spends time and money on shots the user cannot use, and leaves a run whose
recorded shot list does not describe what it did.
"""

import os
import uuid

from app.routers import generation as generation_router
from app.models import GenerationJob, GenerationRun, Shot, Workflow
from app.services import job_payload, reference_bible, workflow_registry


def _add_shot(client, project_id, scene_id, **fields) -> str:
    payload = {"order": 2, "subject": "Bob", "image_prompt": "a second prompt"}
    payload.update(fields)
    response = client.post(
        f"/api/projects/{project_id}/scenes/{scene_id}/shots", json=payload
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _counts(db_session) -> tuple[int, int]:
    return (
        db_session.query(GenerationJob).count(),
        db_session.query(GenerationRun).count(),
    )


def test_generate_refuses_a_shot_its_plan_reports_as_blocked(
    client, db_session, monkeypatch, sample_project, sample_scene, sample_shot
):
    """A metered shot with nothing to send is a blocker, confirmed or not."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-redacted")
    sample_shot.image_provider_id = "openai"
    sample_shot.image_model = "gpt-image-1-mini"
    sample_shot.image_prompt = ""
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id], "confirm_paid_generation": True},
    )

    assert response.status_code == 409, response.text
    assert "compiled image prompt" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_generate_refuses_a_comfyui_shot_with_no_prompt(
    client, db_session, sample_project, sample_shot
):
    sample_shot.image_prompt = ""
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "Missing image prompt" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_one_blocked_shot_refuses_the_whole_batch(
    client, db_session, monkeypatch, sample_project, sample_scene, sample_shot
):
    """The valid shots are not queued either: a batch is authorised as one."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-redacted")
    blocked = _add_shot(
        client, sample_project.id, sample_scene.id,
        image_prompt="", image_provider_id="openai",
        image_model="gpt-image-1-mini", status="Ready",
    )

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"confirm_paid_generation": True},
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "1 of 2 selected shot(s)" in detail
    assert _counts(db_session) == (0, 0)
    # And the shot that was fine is untouched, not left mid-flight.
    db_session.refresh(sample_shot)
    assert sample_shot.status != "Generating"
    assert db_session.query(Shot).filter(Shot.id == blocked).one().status != "Generating"


def test_a_missing_reference_file_blocks_before_a_run_is_created(
    client, db_session, sample_project, sample_scene, sample_shot, png_bytes
):
    """A refusal must not leave an empty run behind in the history."""
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Hero"
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="hero.png", content_type="image/png",
    )
    os.remove(image.file_path)
    sample_shot.reference_asset_ids = [image.id]
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert _counts(db_session) == (0, 0)


def test_image_to_video_without_a_reference_is_refused_atomically(
    client, db_session, sample_project, sample_scene, sample_shot
):
    sample_shot.generation_mode = "image-to-video"
    sample_shot.video_prompt = "a slow push in"
    sample_shot.reference_asset_ids = []
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "reference image" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_generate_refuses_an_explicit_needs_review_shot_atomically(
    client, db_session, sample_project, sample_shot
):
    sample_shot.status = "NeedsReview"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "NeedsReview" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_generate_refuses_an_explicit_approved_shot_atomically(
    client, db_session, sample_project, sample_shot
):
    sample_shot.status = "Approved"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "Approved" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_generate_refuses_an_assigned_workflow_with_an_invalid_mapping(
    client, db_session, sample_project, sample_shot, sample_workflow_json
):
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Invalid mapping", purpose="image"
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "missing", "field": "text"}
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    db_session.add(workflow)
    sample_shot.workflow_preset_id = workflow.id
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "mapping" in response.json()["detail"].lower()
    assert _counts(db_session) == (0, 0)


def test_generate_refuses_unmapped_required_workflow_fields_for_live_comfyui(
    client, db_session, monkeypatch, sample_project, sample_shot,
    sample_workflow_json,
):
    monkeypatch.setattr(
        generation_router.queue_manager.provider,
        "requires_workflow_payload",
        True,
    )
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Unmapped fields", purpose="image"
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"}
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    db_session.add(workflow)
    sample_shot.workflow_preset_id = workflow.id
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "not mapped" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_generate_refuses_a_recurring_prop_continuity_failure(
    client, db_session, sample_project, sample_location, sample_shot
):
    sample_location.props = "Exactly one recurring white paper boat throughout."
    sample_shot.subject = "Alice holding the paper boat"
    sample_shot.image_prompt = "Alice holding a boat"
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409, response.text
    assert "recurring prop continuity" in response.json()["detail"]
    assert _counts(db_session) == (0, 0)


def test_mixed_selection_with_active_job_refuses_the_whole_batch(
    client, db_session, sample_project, sample_scene, sample_shot
):
    """A busy shot must not be silently dropped while clean peers are queued."""
    clean_id = _add_shot(
        client,
        sample_project.id,
        sample_scene.id,
        status="Ready",
    )
    first = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert first.status_code == 200, first.text
    before = _counts(db_session)

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id, clean_id]},
    )

    assert response.status_code == 409, response.text
    assert "queued or running" in response.json()["detail"].lower()
    assert _counts(db_session) == before
    assert db_session.query(Shot).filter(Shot.id == clean_id).one().status == "Ready"


def test_a_clean_selection_still_queues_normally(
    client, db_session, sample_project, sample_scene, sample_shot
):
    """The gate must not cost the ordinary run."""
    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert _counts(db_session) == (1, 1)
