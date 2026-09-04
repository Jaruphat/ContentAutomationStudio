"""
Tests for take review endpoints addressed by global take/shot id.

These routes are what the cockpit's review and inspector panels call, so a
mismatch between the path here and the path the client builds is invisible to
both test suites until someone clicks the button.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import GenerationJob, Take, Workflow
from app.services import (
    character_sets,
    job_payload,
    reference_bible,
    revisions,
    workflow_registry,
)


@pytest.fixture()
def sample_take(db_session: Session, sample_shot) -> Take:
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        file_path="C:/tmp/take.png",
        review_status="Pending",
        width=1920,
        height=1080,
    )
    db_session.add(take)
    db_session.commit()
    db_session.refresh(take)
    return take


class TestGetTake:
    def test_returns_the_take(self, client, sample_take):
        resp = client.get(f"/api/takes/{sample_take.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_take.id

    def test_unknown_take_is_404(self, client):
        assert client.get("/api/takes/nope").status_code == 404


class TestListShotTakes:
    def test_lists_takes_for_a_shot(self, client, sample_shot, sample_take):
        resp = client.get(f"/api/shots/{sample_shot.id}/takes")
        assert resp.status_code == 200
        assert [t["id"] for t in resp.json()] == [sample_take.id]

    def test_unknown_shot_is_404(self, client):
        assert client.get("/api/shots/nope/takes").status_code == 404


class TestApproveReject:
    def test_approve_sets_status_and_timestamp(self, client, sample_take):
        resp = client.post(
            f"/api/takes/{sample_take.id}/approve",
            json={"rating": 5, "notes": "good framing"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["review_status"] == "Approved"
        assert body["rating"] == 5
        assert body["approved_at"] is not None

    def test_approving_twice_is_rejected(self, client, sample_take):
        client.post(f"/api/takes/{sample_take.id}/approve", json={})
        resp = client.post(f"/api/takes/{sample_take.id}/approve", json={})
        assert resp.status_code == 400

    def test_reject_sets_status(self, client, sample_take):
        resp = client.post(
            f"/api/takes/{sample_take.id}/reject", json={"notes": "wrong wardrobe"}
        )
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "Rejected"
        assert resp.json()["notes"] == "wrong wardrobe"

    def test_approve_promotes_the_shot(self, client, sample_shot, sample_take):
        client.post(f"/api/takes/{sample_take.id}/approve", json={})
        resp = client.get(
            f"/api/projects/{sample_shot.scene.project_id}"
            f"/scenes/{sample_shot.scene_id}/shots/{sample_shot.id}"
        )
        assert resp.json()["status"] == "Approved"


class TestApprovingStaleTakes:
    """Approving is what marks a shot delivered, so it cannot outrun the shot.

    A take listed in Review, then approved after the shot was edited in another
    tab, would otherwise promote content nobody looked at - and the promotion
    is what the timeline, the render and every export read.
    """

    @pytest.fixture()
    def generated_take(self, db_session, sample_project, sample_shot) -> Take:
        revisions.refresh_project(db_session, sample_project.id)
        take = Take(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            file_path="C:/tmp/take.png",
            review_status="Pending",
            prompt_revision=sample_shot.prompt_revision,
            prompt_sha256=sample_shot.prompt_sha256,
            content_sha256=sample_shot.content_sha256,
            reference_image_ids=list(sample_shot.reference_asset_ids or []),
            reference_sha256s=list(sample_shot.reference_sha256s or []),
        )
        db_session.add(take)
        db_session.commit()
        db_session.refresh(take)
        return take

    def test_a_take_matching_the_current_shot_is_approved(
        self, client, db_session, sample_shot, generated_take
    ):
        response = client.post(f"/api/takes/{generated_take.id}/approve", json={})

        assert response.status_code == 200, response.text
        db_session.refresh(sample_shot)
        assert sample_shot.status == "Approved"

    def test_a_take_from_before_an_edit_cannot_be_approved(
        self, client, db_session, sample_project, sample_shot, generated_take
    ):
        """The shot moved on while this take sat in the review queue."""
        sample_shot.action = "an entirely different action"
        db_session.commit()

        response = client.post(f"/api/takes/{generated_take.id}/approve", json={})

        assert response.status_code == 409, response.text
        assert "out of date" in response.json()["detail"]
        db_session.refresh(generated_take)
        db_session.refresh(sample_shot)
        assert generated_take.review_status == "Pending"
        assert generated_take.approved_at is None
        assert sample_shot.status != "Approved"

    def test_the_shot_is_re_read_before_the_decision_not_trusted(
        self, client, db_session, sample_project, sample_shot, generated_take
    ):
        """The edit here never went through a revision refresh, which is what a
        second browser tab writing directly to the API looks like."""
        sample_shot.image_prompt = "a rewritten prompt"
        db_session.commit()
        # Deliberately no refresh_project: the endpoint has to do it itself, or
        # it compares the take against a digest that is already out of date.

        response = client.post(f"/api/takes/{generated_take.id}/approve", json={})

        assert response.status_code == 409, response.text

    def test_a_take_with_no_recorded_lineage_is_still_approvable(
        self, client, db_session, sample_shot, sample_take
    ):
        """Migrated work predates lineage, so it can be neither proven current
        nor called stale. Refusing it would strand a whole legacy project."""
        response = client.post(f"/api/takes/{sample_take.id}/approve", json={})

        assert response.status_code == 200, response.text
        db_session.refresh(sample_shot)
        assert sample_shot.status == "Approved"


class TestRegenerate:
    def test_estimate_uses_current_plan_even_for_an_approved_take(
        self, client, db_session, sample_shot, sample_take
    ):
        sample_take.review_status = "Approved"
        sample_take.media_provider_id = "comfyui"
        sample_take.media_model = "old-workflow"
        sample_shot.status = "Approved"
        sample_shot.image_provider_id = "openai"
        sample_shot.image_model = "gpt-image-1-mini"
        db_session.commit()

        response = client.get(f"/api/shots/{sample_shot.id}/regenerate/estimate")

        assert response.status_code == 200, response.text
        estimate = response.json()
        assert estimate["shot_count"] == 1
        assert estimate["paid_shot_count"] == 1
        assert estimate["requires_confirmation"] is True
        assert estimate["shots"][0]["provider_id"] == "openai"
        assert estimate["shots"][0]["model"] == "gpt-image-1-mini"
        assert estimate["estimated_cost_usd"] is not None

    def test_estimate_unknown_shot_is_404(self, client):
        assert client.get("/api/shots/nope/regenerate/estimate").status_code == 404

    def test_creates_a_new_queued_job(self, client, sample_shot):
        resp = client.post(f"/api/shots/{sample_shot.id}/regenerate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "Queued"
        assert body["shot_id"] == sample_shot.id

    def test_parameter_map_includes_the_project_aspect_ratio(
        self, client, db_session, sample_project, sample_shot
    ):
        sample_project.aspect_ratio = "9:16"
        sample_project.target_resolution = "1080x1920"
        db_session.commit()

        response = client.post(f"/api/shots/{sample_shot.id}/regenerate")

        assert response.status_code == 200, response.text
        assert response.json()["parameter_map"][job_payload.ASPECT_RATIO] == (
            "9:16 (Portrait Widescreen)"
        )

    def test_regenerate_uses_a_fresh_seed(
        self, client, db_session, sample_shot
    ):
        first = client.post(f"/api/shots/{sample_shot.id}/regenerate").json()
        # A second active job is intentionally refused; make the first request
        # terminal before checking that a later regeneration gets a new seed.
        job = db_session.query(GenerationJob).filter(GenerationJob.id == first["id"]).one()
        job.status = "Completed"
        db_session.commit()
        second = client.post(f"/api/shots/{sample_shot.id}/regenerate").json()
        assert first["seed"] != second["seed"]

    def test_unknown_shot_is_404(self, client):
        assert client.post("/api/shots/nope/regenerate").status_code == 404

    def test_regenerate_snapshots_current_prompt_revision_and_references(
        self,
        client,
        db_session,
        sample_project,
        sample_shot,
        sample_workflow_json,
        png_bytes,
    ):
        record = workflow_registry.import_workflow(
            raw_bytes=sample_workflow_json,
            name="Reference regeneration",
            purpose="image",
        )
        workflow = Workflow(**record)
        workflow.parameter_mapping = {
            job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
            job_payload.SEED: {"nodeId": "3", "field": "seed"},
            job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "ckpt_name"},
        }
        workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
        workflow.validation_status = "valid"
        db_session.add(workflow)
        sample_project.default_image_workflow_id = workflow.id
        revisions.refresh_project(db_session, sample_project.id)

        historical_take = Take(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            file_path="C:/tmp/historical.png",
            review_status="Approved",
            prompt_revision=sample_shot.prompt_revision,
            prompt_sha256=sample_shot.prompt_sha256,
            content_sha256=sample_shot.content_sha256,
            reference_image_ids=[],
            reference_sha256s=[],
        )
        stale_job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            workflow_id=workflow.id,
            parameter_map={job_payload.POSITIVE_PROMPT: "STALE PARAMETER MAP", job_payload.SEED: 7},
            prompt_revision=sample_shot.prompt_revision,
            content_sha256=sample_shot.content_sha256,
            seed=7,
            status="Completed",
        )
        db_session.add_all([historical_take, stale_job])

        sheet = reference_bible.create_sheet(
            db_session,
            project_id=sample_project.id,
            kind="character",
            name="Alice",
        )
        image = reference_bible.store_image(
            db_session,
            sheet=sheet,
            data=png_bytes(128, 160),
            original_filename="alice-current.png",
            content_type="image/png",
        )
        sample_shot.action = "raising the current silver lantern"
        sample_shot.reference_asset_ids = [image.id]
        db_session.commit()

        response = client.post(f"/api/shots/{sample_shot.id}/regenerate")

        assert response.status_code == 200
        job = response.json()
        assert "raising the current silver lantern" in job["parameter_map"][job_payload.POSITIVE_PROMPT]
        assert "STALE PARAMETER MAP" not in job["parameter_map"][job_payload.POSITIVE_PROMPT]
        assert job["prompt_revision"] == 2
        assert job["prompt_sha256"]
        assert job["content_sha256"]
        assert job["reference_image_ids"] == [image.id]
        assert job["reference_sha256s"] == [image.sha256]
        assert job["reference_provenance"]["images"][0]["sha256"] == image.sha256
        assert db_session.query(Take).filter(Take.id == historical_take.id).count() == 1

    def test_regenerate_uses_the_same_primary_canonical_view_as_generate(
        self,
        client,
        db_session,
        sample_project,
        sample_character,
        sample_shot,
        sample_workflow_json,
        png_bytes,
    ):
        record = workflow_registry.import_workflow(
            raw_bytes=sample_workflow_json,
            name="One-input canonical regeneration",
            purpose="image",
        )
        workflow = Workflow(**record)
        workflow.parameter_mapping = {
            job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
            job_payload.SEED: {"nodeId": "3", "field": "seed"},
            job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "ckpt_name"},
        }
        workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
        db_session.add(workflow)
        sample_project.default_image_workflow_id = workflow.id

        character_set = character_sets.create_set(
            db_session,
            project_id=sample_project.id,
            character_id=sample_character.id,
            name="Mara",
        )
        version = character_sets.create_version(
            db_session, character_set, slots=["front", "full_body"]
        )
        for index, view in enumerate(character_sets.list_views(db_session, version)):
            character_sets.attach_view_image(
                db_session,
                view,
                data=png_bytes(64 + index, 64),
                content_type="image/png",
                original_filename=f"{view.slot}.png",
            )
        character_sets.approve_version(db_session, version)
        sample_shot.character_set_ids = [character_set.id]
        db_session.commit()

        response = client.post(f"/api/shots/{sample_shot.id}/regenerate")

        assert response.status_code == 200, response.text
        images = response.json()["reference_provenance"]["images"]
        assert [item["detail"]["view_slot"] for item in images] == [
            "front", "full_body"
        ]
        assert [item["submitted"] for item in images] == [False, True]
        assert response.json()["character_set_sha256s"] == [
            character_sets.canonical_digest(db_session, character_set)
        ]

    def test_regenerate_refuses_current_reference_without_workflow_mapping(
        self,
        client,
        db_session,
        sample_project,
        sample_shot,
        sample_workflow_json,
        png_bytes,
    ):
        record = workflow_registry.import_workflow(
            raw_bytes=sample_workflow_json,
            name="No reference mapping",
            purpose="image",
        )
        workflow = Workflow(**record)
        workflow.parameter_mapping = {
            job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
            job_payload.SEED: {"nodeId": "3", "field": "seed"},
        }
        workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
        db_session.add(workflow)
        sample_project.default_image_workflow_id = workflow.id
        sheet = reference_bible.create_sheet(
            db_session, project_id=sample_project.id, kind="character", name="Alice"
        )
        image = reference_bible.store_image(
            db_session,
            sheet=sheet,
            data=png_bytes(),
            original_filename="alice.png",
            content_type="image/png",
        )
        sample_shot.reference_asset_ids = [image.id]
        db_session.commit()

        response = client.post(f"/api/shots/{sample_shot.id}/regenerate")

        assert response.status_code == 409
        assert "referenceImage" in response.json()["detail"]
        assert db_session.query(GenerationJob).count() == 0

    def test_regenerate_refuses_a_workflow_mapping_that_no_longer_matches(
        self,
        client,
        db_session,
        sample_project,
        sample_shot,
        sample_workflow_json,
    ):
        record = workflow_registry.import_workflow(
            raw_bytes=sample_workflow_json,
            name="Stale mapping",
            purpose="image",
        )
        workflow = Workflow(**record)
        workflow.parameter_mapping = {
            job_payload.POSITIVE_PROMPT: {"nodeId": "missing", "field": "text"},
            job_payload.SEED: {"nodeId": "3", "field": "seed"},
        }
        workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
        db_session.add(workflow)
        sample_project.default_image_workflow_id = workflow.id
        db_session.commit()

        response = client.post(f"/api/shots/{sample_shot.id}/regenerate")

        assert response.status_code == 409
        assert "mapping" in response.json()["detail"].lower()
        assert db_session.query(GenerationJob).count() == 0
