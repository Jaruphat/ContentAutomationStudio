"""
Generating a character set version through a real media provider.

The runner is the piece that turns a draft version into canonical views. It
must go through the same provider interface as shot generation - submit, poll,
collect the output file - and it must record on every view exactly what made
it: provider, model, workflow, request parameters, seed and provenance.

The provider here is a stand-in that records what it was handed. That is the
point: these tests assert what reaches the provider boundary, not what a
particular vendor does with it.
"""

import asyncio
import os

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project, Workflow
from app.services import character_sets
from app.services.comfyui_adapter import JobStatus, JobStatusEnum, OutputFile


class RecordingProvider:
    """A provider that returns a real PNG and remembers each submission."""

    requires_workflow_payload = False

    def __init__(self, image_path_factory):
        self._image_path_factory = image_path_factory
        self.submissions: list[dict] = []

    async def submit_job(self, workflow_payload, job_id, context=None):
        self.submissions.append({
            "payload": dict(workflow_payload),
            "job_id": job_id,
            "context": dict(context or {}),
        })
        return f"prompt-{len(self.submissions)}"

    async def get_job_status(self, prompt_id):
        return JobStatus(status=JobStatusEnum.COMPLETED, progress=1.0)

    async def get_job_outputs(self, prompt_id):
        return [OutputFile(
            file_path=self._image_path_factory(prompt_id),
            file_type="image",
            width=64,
            height=64,
        )]

    async def check_health(self):  # pragma: no cover - not exercised here
        raise NotImplementedError


@pytest.fixture()
def written_png(tmp_path, png_bytes):
    def _make(name: str) -> str:
        path = os.path.join(str(tmp_path), f"{name}.png")
        with open(path, "wb") as f:
            f.write(png_bytes(64, 64))
        return path

    return _make


@pytest.fixture()
def character_set(
    db_session: Session, sample_project: Project, sample_character: Character
):
    return character_sets.create_set(
        db_session,
        project_id=sample_project.id,
        name="Mara",
        character_id=sample_character.id,
        appearance="Close-cropped silver hair, weathered face.",
        wardrobe="Charcoal field jacket.",
        negative_tokens="blurry, extra limbs",
    )


def test_generation_fills_every_view_and_records_provenance(
    db_session: Session, sample_project: Project, character_set, written_png
):
    from app.services import character_set_generation

    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side"],
    )
    provider = RecordingProvider(written_png)

    result = asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", model="workflow", seed=4242,
    ))

    assert result.status == character_sets.STATUS_NEEDS_REVIEW
    views = character_sets.list_views(db_session, result)
    assert [view.status for view in views] == ["Ready", "Ready"]
    assert all(view.reference_image_id for view in views)

    for view in views:
        assert view.provider_id == "comfyui"
        assert view.model == "workflow"
        assert view.seed == 4242
        assert view.provenance["prompt_id"]
        assert view.provenance["view_slot"] == view.slot
        assert view.request_params["positivePrompt"] == view.view_prompt


def test_each_view_is_submitted_with_its_own_slot_prompt_and_seed(
    db_session: Session, character_set, written_png
):
    """A sheet is only useful when every view is the *same* character.

    The identity text is shared and only the slot directive differs, so the
    submitted prompts must agree on the description and disagree on the view.
    """
    from app.services import character_set_generation

    version = character_sets.create_version(
        db_session, character_set, slots=["front", "back"],
    )
    provider = RecordingProvider(written_png)
    asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", model="workflow", seed=7,
    ))

    prompts = [s["payload"]["positivePrompt"] for s in provider.submissions]
    assert len(prompts) == 2
    assert all("Close-cropped silver hair" in prompt for prompt in prompts)
    assert "front-facing" in prompts[0]
    assert "rear" in prompts[1]
    # Every view of one sheet shares a seed, so the sheet is reproducible.
    assert {s["payload"]["seed"] for s in provider.submissions} == {7}
    assert all(
        s["payload"]["negativePrompt"] == "blurry, extra limbs"
        for s in provider.submissions
    )


def test_a_failing_view_is_recorded_without_losing_the_others(
    db_session: Session, character_set, written_png
):
    from app.services import character_set_generation

    class HalfBrokenProvider(RecordingProvider):
        async def get_job_status(self, prompt_id):
            if prompt_id.endswith("2"):
                return JobStatus(
                    status=JobStatusEnum.FAILED,
                    error_code="OOM",
                    error_message="Out of VRAM",
                )
            return JobStatus(status=JobStatusEnum.COMPLETED, progress=1.0)

    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side"],
    )
    result = asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=HalfBrokenProvider(written_png),
        provider_id="comfyui", model="workflow", seed=1,
    ))

    views = character_sets.list_views(db_session, result)
    assert views[0].status == "Ready"
    assert views[1].status == "Failed"
    assert "Out of VRAM" in views[1].error_message
    assert result.status == character_sets.STATUS_FAILED
    # A failed sheet can never become the canonical identity.
    with pytest.raises(character_sets.CharacterSetError) as exc:
        character_sets.approve_version(db_session, result)
    assert exc.value.code == "views_incomplete"


def test_comfyui_generation_requires_a_registered_image_workflow(
    db_session: Session, character_set, written_png
):
    """A real ComfyUI provider is never handed raw logical values.

    Without a node-mapped workflow there is no submittable graph, so the run is
    refused before anything is generated rather than producing an untraceable
    image.
    """
    from app.services import character_set_generation

    class StrictProvider(RecordingProvider):
        requires_workflow_payload = True

    version = character_sets.create_version(
        db_session, character_set, slots=["front"],
    )
    with pytest.raises(character_set_generation.CharacterSetGenerationError) as exc:
        asyncio.run(character_set_generation.generate_version(
            db_session, version, provider=StrictProvider(written_png),
            provider_id="comfyui", model="workflow",
        ))
    assert "workflow" in str(exc.value).lower()


def test_a_registered_workflow_is_node_mapped_before_submission(
    db_session: Session, sample_project: Project, character_set, written_png, tmp_path
):
    """The submitted payload is a graph, with values injected through mapping."""
    from app.services import character_set_generation

    source = os.path.join(str(tmp_path), "workflow.json")
    with open(source, "w", encoding="utf-8") as f:
        f.write(
            '{"3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},'
            ' "4": {"class_type": "KSampler", "inputs": {"seed": 0}}}'
        )
    workflow = Workflow(
        id="wf-charset",
        name="Charset T2I",
        purpose="image",
        source_json_path=source,
        source_format="api",
        validation_status="valid",
        parameter_mapping={
            "positivePrompt": {"nodeId": "3", "field": "text"},
            "seed": {"nodeId": "4", "field": "seed"},
        },
        output_mapping=[],
    )
    db_session.add(workflow)
    db_session.commit()

    class StrictProvider(RecordingProvider):
        requires_workflow_payload = True

    version = character_sets.create_version(
        db_session, character_set, slots=["front"],
    )
    provider = StrictProvider(written_png)
    asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", model="workflow",
        workflow_id=workflow.id, seed=99,
    ))

    payload = provider.submissions[0]["payload"]
    assert payload["3"]["inputs"]["text"].startswith("front-facing")
    assert payload["4"]["inputs"]["seed"] == 99
    view = character_sets.list_views(db_session, version)[0]
    assert view.workflow_id == workflow.id


def test_a_reference_conditioned_workflow_is_refused_for_a_character_sheet(
    db_session: Session, character_set, written_png, tmp_path
):
    """A sheet has no reference to give, so an edit workflow must be refused.

    Character-set generation supplies a prompt, seed and size - never a
    reference image. Handing those values to a workflow whose graph expects one
    leaves the reference node holding whatever image was baked into the
    exported JSON, and every canonical view would then be conditioned on a
    stranger while reporting success. Refusing is the only honest outcome:
    silently generating the wrong identity is worse than generating nothing.
    """
    from app.services import character_set_generation

    source = os.path.join(str(tmp_path), "edit-workflow.json")
    with open(source, "w", encoding="utf-8") as f:
        f.write(
            '{"3": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},'
            ' "4": {"class_type": "KSampler", "inputs": {"seed": 0}},'
            ' "9": {"class_type": "LoadImage",'
            ' "inputs": {"image": "someone_else.png"}}}'
        )
    workflow = Workflow(
        id="wf-charset-edit",
        name="Boogu Image Edit",
        purpose="image",
        source_json_path=source,
        source_format="api",
        validation_status="valid",
        parameter_mapping={
            "positivePrompt": {"nodeId": "3", "field": "text"},
            "seed": {"nodeId": "4", "field": "seed"},
            "referenceImage": {"nodeId": "9", "field": "image"},
        },
        output_mapping=[],
    )
    db_session.add(workflow)
    db_session.commit()

    class StrictProvider(RecordingProvider):
        requires_workflow_payload = True

    version = character_sets.create_version(
        db_session, character_set, slots=["front"],
    )
    provider = StrictProvider(written_png)
    with pytest.raises(character_set_generation.CharacterSetGenerationError) as exc:
        asyncio.run(character_set_generation.generate_version(
            db_session, version, provider=provider,
            provider_id="comfyui", model="workflow",
            workflow_id="wf-charset-edit",
        ))

    message = str(exc.value)
    assert "reference" in message.lower()
    assert "Boogu Image Edit" in message, "the user has to be told which workflow"
    assert provider.submissions == [], "nothing may reach the GPU"


def test_a_transient_failure_on_one_view_is_retried_before_giving_up(
    db_session: Session, character_set, written_png
):
    """A cold model load can fail once and succeed immediately after.

    Generating a sheet is a single synchronous call with no queue behind it,
    so one flaky view used to lose the whole run - and on a twenty-gigabyte
    model the first view is exactly where a streaming read fails. The queue
    retries transient failures; this path had no such thing.
    """
    from app.services import character_set_generation

    class FlakyOnce(RecordingProvider):
        def __init__(self, factory):
            super().__init__(factory)
            self.attempts = 0

        async def get_job_status(self, prompt_id):
            self.attempts += 1
            if self.attempts == 1:
                return JobStatus(
                    status=JobStatusEnum.FAILED,
                    error_message="RuntimeError: HostBuffer.read_file_slice failed",
                )
            return JobStatus(status=JobStatusEnum.COMPLETED, progress=1.0)

    version = character_sets.create_version(db_session, character_set, slots=["front"])
    provider = FlakyOnce(written_png)

    result = asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", model="workflow",
    ))

    view = result.views[0]
    assert view.status != "Failed", view.error_message
    assert view.reference_image_id, "the retry has to actually produce the image"
    assert len(provider.submissions) == 2, "it should have been submitted again"


def test_a_permanent_failure_is_not_retried_forever(
    db_session: Session, character_set, written_png
):
    """A missing model fails the same way every time; retrying wastes minutes
    of somebody's evening to reach the same answer."""
    from app.services import character_set_generation

    class AlwaysMissing(RecordingProvider):
        async def get_job_status(self, prompt_id):
            return JobStatus(
                status=JobStatusEnum.FAILED,
                error_message="Value not in list: unet_name 'gone.safetensors' not in []",
            )

    version = character_sets.create_version(db_session, character_set, slots=["front"])
    provider = AlwaysMissing(written_png)

    result = asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", model="workflow",
    ))

    assert result.views[0].status == "Failed"
    assert len(provider.submissions) == 1, "a permanent fault is not worth repeating"
