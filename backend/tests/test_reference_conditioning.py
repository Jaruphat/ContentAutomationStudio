"""End-to-end contracts for reference-conditioned ComfyUI jobs."""

import os
import uuid
import hashlib
import json

import pytest

from app.models import GenerationJob, Workflow
from app.services import job_payload, reference_bible, workflow_registry
from app.services.queue_manager import QueueManager


def _workflow_with_reference(db_session, sample_workflow_json):
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
    workflow.validation_status = "valid"
    db_session.add(workflow)
    db_session.commit()
    return workflow


def test_generation_job_snapshots_reference_identity(
    client, db_session, sample_project, sample_scene, sample_shot, png_bytes,
    sample_workflow_json,
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    sample_project.default_image_workflow_id = workflow.id
    sample_project.aspect_ratio = "9:5"
    sample_project.target_resolution = "864x480"
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Hero"
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 160),
        original_filename="hero.png", content_type="image/png",
    )
    sample_shot.reference_asset_ids = [image.id]
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 200
    body = response.json()[0]
    assert body["reference_image_ids"] == [image.id]
    assert body["reference_sha256s"] == [image.sha256]
    assert body["parameter_map"]["aspectRatio"] == "16:9 (Widescreen)"
    db_session.refresh(sample_shot)
    assert body["prompt_revision"] == sample_shot.prompt_revision
    assert body["content_sha256"] == sample_shot.content_sha256
    assert body["reference_provenance"]["images"][0]["file_path"] == image.file_path
    assert body["reference_provenance"]["images"][0]["sha256"] == image.sha256


def test_reference_payload_uses_uploaded_comfyui_name(
    db_session, sample_shot, sample_workflow_json
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, workflow_id=workflow.id,
        parameter_map={
            job_payload.POSITIVE_PROMPT: "hero portrait",
            job_payload.SEED: 9,
            job_payload.REFERENCE_IMAGE: "cas/job/hero.png",
        },
        seed=9, status="Queued",
    )
    db_session.add(job)
    db_session.commit()

    built = job_payload.build_payload(db_session, job, require_workflow=True)

    assert built.payload["4"]["inputs"]["ckpt_name"] == "cas/job/hero.png"


def test_i2v_preflight_requires_reference_mapping(
    client, db_session, sample_project, sample_shot, sample_workflow_json,
    png_bytes,
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    workflow.parameter_mapping = {
        key: value for key, value in workflow.parameter_mapping.items()
        if key != job_payload.REFERENCE_IMAGE
    }
    sample_project.default_video_workflow_id = workflow.id
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Hero"
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="hero.png", content_type="image/png",
    )
    sample_shot.generation_mode = "image-to-video"
    sample_shot.video_prompt = "hero turns toward camera"
    sample_shot.reference_asset_ids = [image.id]
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    issue = next(item for item in body["issues"] if item["shot_id"] == sample_shot.id)
    assert any("referenceImage" in text for text in issue["issues"])


def test_job_creation_refuses_reference_without_workflow_mapping(
    client, db_session, sample_project, sample_shot, sample_workflow_json, png_bytes
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    workflow.parameter_mapping = {
        key: value for key, value in workflow.parameter_mapping.items()
        if key != job_payload.REFERENCE_IMAGE
    }
    sample_project.default_image_workflow_id = workflow.id
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="character", name="Hero"
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="hero.png", content_type="image/png",
    )
    sample_shot.reference_asset_ids = [image.id]
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409
    assert "referenceImage" in response.json()["detail"]
    assert db_session.query(GenerationJob).count() == 0


def test_job_creation_refuses_i2v_without_a_reference(
    client, db_session, sample_project, sample_shot, sample_workflow_json
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    sample_project.default_video_workflow_id = workflow.id
    sample_shot.generation_mode = "image-to-video"
    sample_shot.video_prompt = "turn toward camera"
    sample_shot.status = "Ready"
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )

    assert response.status_code == 409
    assert "requires a reference image" in response.json()["detail"]
    assert db_session.query(GenerationJob).count() == 0


@pytest.mark.asyncio
async def test_real_provider_uploads_reference_to_comfyui_input(
    tmp_path, monkeypatch, png_bytes
):
    from app.services import comfyui_provider

    source = tmp_path / "hero.png"
    source.write_bytes(png_bytes(128, 128))
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"name": "hero.png", "subfolder": "cas/job-1", "type": "input"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, files, data):
            captured.update(url=url, files=files, data=data)
            assert files["image"][0] == "hero.png"
            assert files["image"][2] == "image/png"
            assert files["image"][1].read() == source.read_bytes()
            return Response()

    monkeypatch.setattr(comfyui_provider.httpx, "AsyncClient", Client)
    provider = comfyui_provider.RealComfyUIProvider(
        base_url="http://comfy.test", output_base_dir=str(tmp_path / "output")
    )

    uploaded = await provider.upload_reference_image(
        str(source), upload_name="cas/job-1/hero.png", mime_type="image/png"
    )

    assert captured["url"] == "http://comfy.test/upload/image"
    assert captured["data"] == {
        "type": "input",
        "subfolder": "cas/job-1",
        "overwrite": "true",
    }
    assert uploaded["workflow_value"] == "cas/job-1/hero.png"
    assert uploaded["type"] == "input"


def test_h3_i2v_api_graph_maps_reference_to_load_image():
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    graph_path = os.path.join(
        root, "workflows", "source", "api", "video_minimax_h3_i2v.api.json"
    )
    graph = workflow_registry.load_workflow_source(graph_path)
    mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "105:104", "field": "prompt"},
        job_payload.SEED: {"nodeId": "105:15", "field": "noise_seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "114", "field": "image"},
        job_payload.OUTPUT_PREFIX: {"nodeId": "92", "field": "filename_prefix"},
    }
    valid, errors, _warnings = workflow_registry.validate_mapping(
        graph, mapping, [{"nodeId": "92", "type": "video"}]
    )
    assert valid, errors
    payload = workflow_registry.apply_parameter_mapping(
        graph, mapping, {job_payload.REFERENCE_IMAGE: "cas/job/first.png"}
    )
    assert payload["114"]["inputs"]["image"] == "cas/job/first.png"


def test_h3_i2v_registration_persists_reference_input_mapping():
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    source_path = os.path.join(
        root, "workflows", "source", "api", "video_minimax_h3_i2v.api.json"
    )
    registration_path = os.path.join(
        root, "workflows", "derived", "video_minimax_h3_i2v.reference.provenance.json"
    )
    with open(source_path, "rb") as source_file:
        source_bytes = source_file.read()
    with open(registration_path, encoding="utf-8") as registration_file:
        provenance = json.load(registration_file)
    assert provenance["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    registration = provenance["registration"]
    assert registration["purpose"] == "image-to-video"
    assert registration["parameter_mapping"][job_payload.REFERENCE_IMAGE] == {
        "nodeId": "114", "field": "image"
    }
    assert registration["parameter_mapping"][job_payload.ASPECT_RATIO] == {
        "nodeId": "115", "field": "aspect_ratio"
    }
    graph = workflow_registry.parse_workflow_json(source_bytes)
    valid, errors, _warnings = workflow_registry.validate_mapping(
        graph, registration["parameter_mapping"], registration["output_mapping"]
    )
    assert valid, errors


def test_boogu_derivative_has_registration_and_hash_provenance():
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    source_path = os.path.join(root, "image_boogu_image_0_1_edit_int8.json")
    derived_path = os.path.join(
        root, "workflows", "derived",
        "image_boogu_image_0_1_edit_int8.reference.api.json",
    )
    provenance_path = os.path.join(
        root, "workflows", "derived",
        "image_boogu_image_0_1_edit_int8.reference.provenance.json",
    )
    with open(source_path, "rb") as source_file:
        source_bytes = source_file.read()
    with open(derived_path, "rb") as derived_file:
        derived_bytes = derived_file.read()
    with open(provenance_path, encoding="utf-8") as provenance_file:
        provenance = json.load(provenance_file)

    assert provenance["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert provenance["derived_sha256"] == hashlib.sha256(derived_bytes).hexdigest()
    registration = provenance["registration"]
    assert registration["purpose"] == "image"
    assert registration["version"] == "1.0-reference.1"
    mapping = registration["parameter_mapping"]
    assert mapping[job_payload.REFERENCE_IMAGE] == {"nodeId": "32", "field": "image"}
    graph = workflow_registry.parse_workflow_json(derived_bytes)
    valid, errors, _warnings = workflow_registry.validate_mapping(
        graph, mapping, registration["output_mapping"]
    )
    assert valid, errors


@pytest.mark.asyncio
async def test_queue_uploads_reference_before_payload_build(
    db_session, sample_shot, sample_workflow_json, tmp_path
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    source = tmp_path / "hero.png"
    source.write_bytes(b"image bytes already validated by the reference store")
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, workflow_id=workflow.id,
        parameter_map={job_payload.POSITIVE_PROMPT: "hero", job_payload.SEED: 5},
        reference_image_ids=["image-1"], reference_sha256s=["a" * 64],
        reference_provenance={
            "images": [{
                "image_id": "image-1", "file_path": str(source),
                "mime_type": "image/png", "sha256": "a" * 64,
                "width": 128, "height": 128,
            }]
        },
        seed=5, status="Queued",
    )
    db_session.add(job)
    db_session.commit()

    class UploadProvider:
        async def upload_reference_image(self, file_path, *, upload_name, mime_type):
            assert file_path == str(source)
            assert upload_name.startswith(f"cas/{job.id}/")
            assert mime_type == "image/png"
            return {
                "name": "hero.png", "subfolder": f"cas/{job.id}",
                "type": "input", "workflow_value": f"cas/{job.id}/hero.png",
            }

    manager = QueueManager()
    await manager._prepare_reference_inputs(db_session, job, UploadProvider())

    assert job.parameter_map[job_payload.REFERENCE_IMAGE] == f"cas/{job.id}/hero.png"
    uploaded = job.reference_provenance["images"][0]["comfyui"]
    assert uploaded["workflow_value"] == f"cas/{job.id}/hero.png"
    assert uploaded["mapping"] == {"nodeId": "4", "field": "ckpt_name"}


@pytest.mark.asyncio
async def test_queue_uploads_only_the_reference_marked_submitted(
    db_session, sample_shot, sample_workflow_json, tmp_path
):
    workflow = _workflow_with_reference(db_session, sample_workflow_json)
    front = tmp_path / "front.png"
    full_body = tmp_path / "full_body.png"
    front.write_bytes(b"front")
    full_body.write_bytes(b"full body")
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, workflow_id=workflow.id,
        parameter_map={job_payload.POSITIVE_PROMPT: "hero", job_payload.SEED: 5},
        reference_provenance={
            "images": [
                {
                    "image_id": "front", "file_path": str(front),
                    "mime_type": "image/png", "submitted": False,
                    "selection_reason": "conceptual identity dependency",
                },
                {
                    "image_id": "full-body", "file_path": str(full_body),
                    "mime_type": "image/png", "submitted": True,
                    "selection_reason": "primary canonical character-set view",
                },
            ]
        },
        seed=5, status="Queued",
    )
    db_session.add(job)
    db_session.commit()
    uploaded_paths = []

    class UploadProvider:
        async def upload_reference_image(self, file_path, *, upload_name, mime_type):
            uploaded_paths.append(file_path)
            return {
                "name": "full_body.png", "subfolder": f"cas/{job.id}",
                "type": "input", "workflow_value": f"cas/{job.id}/full_body.png",
            }

    manager = QueueManager()
    await manager._prepare_reference_inputs(db_session, job, UploadProvider())

    assert uploaded_paths == [str(full_body)]
    assert [item["submitted"] for item in job.reference_provenance["images"]] == [
        False, True
    ]
    assert "comfyui" not in job.reference_provenance["images"][0]
    assert job.reference_provenance["images"][1]["comfyui"]["workflow_value"] == (
        f"cas/{job.id}/full_body.png"
    )


def test_provider_context_contains_only_physically_submitted_references(
    db_session, sample_shot
):
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=sample_shot.id,
        parameter_map={job_payload.POSITIVE_PROMPT: "hero", job_payload.SEED: 5},
        reference_provenance={
            "images": [
                {"image_id": "front", "submitted": False},
                {"image_id": "full-body", "submitted": True},
            ]
        },
        seed=5, status="Queued",
    )
    db_session.add(job)
    db_session.commit()

    context = QueueManager()._job_context(db_session, job, sample_shot)

    assert [item["image_id"] for item in context["reference_inputs"]] == ["full-body"]
