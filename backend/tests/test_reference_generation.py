"""Establishing a place once, instead of describing it nine times.

SF01 was nine key images generated independently from nine paragraphs that all
began with the same world description. Four of them are recognisably the same
abandoned station. The other five are a different building - green weatherboard
in one shot, red brick in another, daylight in a third - and no amount of
rewriting the paragraph fixes that, because the model is not being asked to
match anything. It is being asked nine separate times to imagine a station.

Characters solved this a while ago: generate a canonical sheet, approve it, and
hand the approved image to every shot as a real reference input. A place needs
exactly the same thing and had no way to get it - a reference sheet could hold
an uploaded plate, but nothing in the application could *make* one.

So: generate into a reference sheet. The result is an ordinary reference image
on an ordinary sheet, which means everything downstream - binding it to shots,
sending it to the provider, recording it in the job's provenance - already
works and does not need to know it was generated rather than uploaded.

The refusals are the ones the character sheet learned the hard way, because
they are the same mistake: a graph that expects a reference image keeps
whatever was baked into its export, and reports success.
"""

import asyncio
import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Project, ReferenceImage, Workflow
from app.services import job_payload, reference_bible, reference_generation
from app.services.comfyui_adapter import JobStatus, JobStatusEnum, OutputFile


class RecordingProvider:
    requires_workflow_payload = True

    def __init__(self, image_path_factory):
        self._factory = image_path_factory
        self.submissions: list[dict] = []

    async def submit_job(self, workflow_payload, job_id, context=None):
        self.submissions.append({
            "payload": dict(workflow_payload),
            "context": dict(context or {}),
        })
        return f"prompt-{len(self.submissions)}"

    async def get_job_status(self, prompt_id):
        return JobStatus(status=JobStatusEnum.COMPLETED, progress=1.0)

    async def get_job_outputs(self, prompt_id):
        return [OutputFile(
            file_path=self._factory(prompt_id), file_type="image",
            width=768, height=1024,
        )]

    async def check_health(self):  # pragma: no cover
        raise NotImplementedError


class FailingProvider(RecordingProvider):
    async def get_job_status(self, prompt_id):
        return JobStatus(
            status=JobStatusEnum.FAILED, progress=0.0,
            error_message="the sampler ran out of memory",
        )


@pytest.fixture()
def written_png(tmp_path, png_bytes):
    """A distinct image per submission.

    The reference store is content-addressed on purpose, so a factory that
    returned identical bytes would make two plates collapse into one row and
    the test would be measuring the fixture rather than the feature.
    """
    counter = {"n": 0}

    def _make(name: str) -> str:
        counter["n"] += 1
        path = os.path.join(str(tmp_path), f"{name}.png")
        with open(path, "wb") as handle:
            handle.write(png_bytes(64 + counter["n"], 64))
        return path

    return _make


@pytest.fixture()
def sheet(db_session: Session, sample_project: Project):
    return reference_bible.create_sheet(
        db_session,
        project_id=sample_project.id,
        kind="location",
        name="The abandoned station",
        canonical_description=(
            "Small abandoned rural railway station in northern England, "
            "weathered dark brick, faded cream wooden trim, analog clock."
        ),
    )


def _t2i_workflow(db, tmp_path, name="Z-Image Turbo T2I"):
    import json

    path = os.path.join(str(tmp_path), f"{uuid.uuid4()}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
            "5": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": 512, "height": 512}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }, handle)
    workflow = Workflow(
        id=str(uuid.uuid4()), name=name, purpose="image", source_format="api",
        source_json_path=path, validation_status="valid",
        parameter_mapping={
            job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
            job_payload.NEGATIVE_PROMPT: {"nodeId": "7", "field": "text"},
            job_payload.SEED: {"nodeId": "3", "field": "seed"},
            job_payload.WIDTH: {"nodeId": "5", "field": "width"},
            job_payload.HEIGHT: {"nodeId": "5", "field": "height"},
        },
    )
    db.add(workflow)
    db.commit()
    return workflow


def _generate(db, sheet, workflow, provider, **over):
    return asyncio.run(reference_generation.generate_image(
        db, sheet,
        prompt=over.pop("prompt", "the abandoned station at night, wide shot"),
        negative_prompt=over.pop("negative_prompt", "text, watermark"),
        provider=provider, provider_id="comfyui", model="workflow",
        workflow_id=workflow.id if workflow else None,
        seed=over.pop("seed", 4242), width=768, height=1024, **over,
    ))


# ---------------------------------------------------------------------------
# Generating
# ---------------------------------------------------------------------------

def test_a_generated_plate_lands_on_the_sheet_like_an_uploaded_one(
    db_session, sheet, tmp_path, written_png,
):
    """The point of putting it here: everything downstream already works, and
    none of it has to know the plate was generated rather than uploaded."""
    workflow = _t2i_workflow(db_session, tmp_path)

    image = _generate(db_session, sheet, workflow, RecordingProvider(written_png))

    assert image.sheet_id == sheet.id
    assert image.role == "canonical"
    assert os.path.isfile(image.file_path)
    assert image.sha256


def test_the_prompt_and_seed_reach_the_provider_through_the_mapping(
    db_session, sheet, tmp_path, written_png,
):
    """No node id in this module: the graph's own mapping places the values."""
    workflow = _t2i_workflow(db_session, tmp_path)
    provider = RecordingProvider(written_png)

    _generate(db_session, sheet, workflow, provider, prompt="a wet platform at night")

    payload = provider.submissions[0]["payload"]
    assert payload["6"]["inputs"]["text"] == "a wet platform at night"
    assert payload["7"]["inputs"]["text"] == "text, watermark"
    assert payload["3"]["inputs"]["seed"] == 4242
    assert payload["5"]["inputs"]["width"] == 768


def test_the_plate_records_exactly_what_made_it(
    db_session, sheet, tmp_path, written_png,
):
    """A world every later shot is conditioned on has to be traceable back to
    the request that produced it, or the whole film rests on an unknown."""
    workflow = _t2i_workflow(db_session, tmp_path)

    image = _generate(db_session, sheet, workflow, RecordingProvider(written_png))

    provenance = image.provenance or {}
    assert provenance["provider_id"] == "comfyui"
    assert provenance["workflow_id"] == workflow.id
    assert provenance["seed"] == 4242
    assert provenance["prompt"].startswith("the abandoned station")
    assert provenance["prompt_id"]


def test_two_plates_can_live_on_one_sheet(
    db_session, sheet, tmp_path, written_png,
):
    """A place has more than one view - the platform, the ticket office, the
    track. Establishing one must not replace the last."""
    workflow = _t2i_workflow(db_session, tmp_path)
    provider = RecordingProvider(written_png)

    _generate(db_session, sheet, workflow, provider, prompt="the platform", seed=1)
    _generate(db_session, sheet, workflow, provider, prompt="the ticket office", seed=2)

    images = (
        db_session.query(ReferenceImage)
        .filter(ReferenceImage.sheet_id == sheet.id)
        .all()
    )
    assert len(images) == 2


# ---------------------------------------------------------------------------
# Refusals - the same ones the character sheet learned the hard way
# ---------------------------------------------------------------------------

def test_a_reference_conditioned_workflow_is_refused(
    db_session, sheet, tmp_path, written_png,
):
    """A plate establishes a place; it has no reference to supply. Injection
    replaces only the values it is handed, so this graph would keep whichever
    image its export baked in and report success."""
    workflow = _t2i_workflow(db_session, tmp_path, name="Boogu edit")
    workflow.parameter_mapping = {
        **workflow.parameter_mapping,
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
    }
    db_session.commit()

    with pytest.raises(reference_generation.ReferenceGenerationError) as exc:
        _generate(db_session, sheet, workflow, RecordingProvider(written_png))
    assert "reference" in str(exc.value).lower()


def test_a_ui_format_workflow_is_refused_with_the_way_out(
    db_session, sheet, tmp_path, written_png,
):
    workflow = _t2i_workflow(db_session, tmp_path)
    workflow.source_format = "ui"
    db_session.commit()

    with pytest.raises(reference_generation.ReferenceGenerationError) as exc:
        _generate(db_session, sheet, workflow, RecordingProvider(written_png))
    assert "export" in str(exc.value).lower()


def test_no_workflow_at_all_is_refused(db_session, sheet, written_png):
    with pytest.raises(reference_generation.ReferenceGenerationError):
        _generate(db_session, sheet, None, RecordingProvider(written_png))


def test_a_provider_failure_stores_nothing_and_says_why(
    db_session, sheet, tmp_path, written_png,
):
    """A half-written plate on the sheet would be bound to shots as if it were
    a finished one."""
    workflow = _t2i_workflow(db_session, tmp_path)

    with pytest.raises(reference_generation.ReferenceGenerationError) as exc:
        _generate(db_session, sheet, workflow, FailingProvider(written_png))

    assert "memory" in str(exc.value).lower()
    assert (
        db_session.query(ReferenceImage)
        .filter(ReferenceImage.sheet_id == sheet.id)
        .count() == 0
    )


def test_an_empty_prompt_is_refused(db_session, sheet, tmp_path, written_png):
    """A blank prompt against a text-to-image graph produces something, and
    whatever it produces becomes the world every shot is matched to."""
    workflow = _t2i_workflow(db_session, tmp_path)

    with pytest.raises(reference_generation.ReferenceGenerationError):
        _generate(db_session, sheet, workflow, RecordingProvider(written_png),
                  prompt="   ")


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------

def test_the_api_generates_into_a_sheet(
    client, db_session, sample_project, sheet, tmp_path, monkeypatch, written_png,
):
    workflow = _t2i_workflow(db_session, tmp_path)
    provider = RecordingProvider(written_png)
    monkeypatch.setattr(
        "app.services.media_providers.get_provider", lambda _id: provider
    )

    response = client.post(
        f"/api/projects/{sample_project.id}/references/{sheet.id}/generate",
        json={
            "prompt": "the abandoned station at night, wide establishing shot",
            "negative_prompt": "text, watermark",
            "workflow_id": workflow.id,
            "seed": 99,
            "width": 768,
            "height": 1024,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["sheet_id"] == sheet.id


def test_the_api_reports_a_refusal_rather_than_a_500(
    client, db_session, sample_project, sheet,
):
    response = client.post(
        f"/api/projects/{sample_project.id}/references/{sheet.id}/generate",
        json={"prompt": "x", "workflow_id": "no-such-workflow"},
    )

    assert response.status_code == 409, response.text
