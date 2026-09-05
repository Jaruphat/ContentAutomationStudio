"""Establishing an identity from a picture instead of a paragraph.

Until now a character could only be *described*: appearance, proportions,
wardrobe, palette. That works for an invented character and not at all for one
that already exists - a photograph of a person, a drawing somebody made, a
frame from an earlier film. Describing a face well enough for a model to
reproduce it twice is a skill, and it is the wrong tool when the face is
already sitting in a file.

Attaching a source image turns the canonical sheet into an edit of that
picture: every view is generated from it, so the six views are six angles of
the same subject rather than six people who match the same paragraph.

Two guards, and they point in opposite directions on purpose:

* Without a source image, a reference-conditioned workflow is still refused.
  Injection replaces the values it is handed and nothing else, so a graph with
  a reference input nobody filled keeps whichever picture was baked in at
  export - and generates a stranger, reported as success.
* With a source image, a text-to-image workflow is refused too. It has no
  input the picture can go into, so it would silently ignore the thing the
  user chose the feature for.
"""

import asyncio
import os

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project, Workflow
from app.services import character_set_generation, character_sets, job_payload
from app.services.comfyui_adapter import JobStatus, JobStatusEnum, OutputFile


class RecordingProvider:
    """Records submissions and every image uploaded across the boundary."""

    requires_workflow_payload = True

    def __init__(self, image_path_factory):
        self._image_path_factory = image_path_factory
        self.submissions: list[dict] = []
        self.uploads: list[dict] = []

    async def upload_reference_image(self, file_path, *, upload_name, mime_type=""):
        self.uploads.append({
            "file_path": file_path,
            "upload_name": upload_name,
            "mime_type": mime_type,
        })
        return {"workflow_value": upload_name, "name": upload_name}

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
            file_type="image", width=64, height=64,
        )]

    async def check_health(self):  # pragma: no cover
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
        appearance="Close-cropped silver hair.",
    )


def _workflow(db, mapping, name="Boogu edit", path="graph.json"):
    workflow = Workflow(
        name=name, purpose="image", source_format="api",
        source_json_path=path, parameter_mapping=mapping,
        validation_status="valid",
    )
    db.add(workflow)
    db.commit()
    return workflow


def _edit_graph(tmp_path):
    import json

    path = os.path.join(str(tmp_path), "edit.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "4": {"class_type": "LoadImage", "inputs": {"image": "baked-in.png"}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
        }, f)
    return path


EDIT_MAPPING = {
    job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
    job_payload.SEED: {"nodeId": "3", "field": "seed"},
    job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
}
TEXT_MAPPING = {
    job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
    job_payload.SEED: {"nodeId": "3", "field": "seed"},
}


# ---------------------------------------------------------------------------
# Attaching the picture
# ---------------------------------------------------------------------------

def test_a_source_image_is_stored_on_the_set_and_is_not_a_canonical_view(
    db_session, character_set, png_bytes,
):
    """It is the input to the sheet, not part of it. A photograph filed among
    the canonical views would be handed to shots as one."""
    character_sets.attach_source_image(
        db_session, character_set,
        data=png_bytes(96, 96), content_type="image/png",
        original_filename="mara.png",
    )

    db_session.refresh(character_set)
    assert character_set.source_image_id
    from app.models import ReferenceImage
    image = (
        db_session.query(ReferenceImage)
        .filter(ReferenceImage.id == character_set.source_image_id)
        .first()
    )
    assert image is not None
    assert image.role == "source", "a canonical role would make it a view"


def test_replacing_the_source_image_moves_the_identity_spec(
    db_session, character_set, png_bytes,
):
    """Changing the picture changes who the character is, so an already
    approved sheet has to read as out of date rather than stay canonical."""
    character_sets.attach_source_image(
        db_session, character_set, data=png_bytes(96, 96),
        content_type="image/png", original_filename="one.png",
    )
    before = character_sets.spec_digest(character_set)

    character_sets.attach_source_image(
        db_session, character_set, data=png_bytes(97, 97),
        content_type="image/png", original_filename="two.png",
    )

    assert character_sets.spec_digest(character_set) != before


# ---------------------------------------------------------------------------
# The two guards
# ---------------------------------------------------------------------------

def test_a_text_to_image_workflow_is_refused_once_a_photo_is_attached(
    db_session, character_set, png_bytes, tmp_path, written_png,
):
    """It has nowhere to put the picture, so it would ignore it in silence."""
    character_sets.attach_source_image(
        db_session, character_set, data=png_bytes(96, 96),
        content_type="image/png", original_filename="mara.png",
    )
    workflow = _workflow(
        db_session, TEXT_MAPPING, name="Z-Image Turbo",
        path=_edit_graph(tmp_path),
    )
    version = character_sets.create_version(db_session, character_set, slots=["front"])

    with pytest.raises(character_set_generation.CharacterSetGenerationError) as exc:
        asyncio.run(character_set_generation.generate_version(
            db_session, version,
            provider=RecordingProvider(written_png),
            provider_id="comfyui", workflow_id=workflow.id,
        ))

    assert "referenceimage" in str(exc.value).lower()


def test_a_reference_workflow_is_still_refused_with_no_photo_attached(
    db_session, character_set, tmp_path, written_png,
):
    """Unchanged: the graph would keep whatever image the export baked in and
    generate a stranger with every hash and lineage entry correct."""
    workflow = _workflow(db_session, EDIT_MAPPING, path=_edit_graph(tmp_path))
    version = character_sets.create_version(db_session, character_set, slots=["front"])

    with pytest.raises(character_set_generation.CharacterSetGenerationError):
        asyncio.run(character_set_generation.generate_version(
            db_session, version,
            provider=RecordingProvider(written_png),
            provider_id="comfyui", workflow_id=workflow.id,
        ))


# ---------------------------------------------------------------------------
# Generating from it
# ---------------------------------------------------------------------------

def test_every_view_is_generated_from_the_attached_photo(
    db_session, character_set, png_bytes, tmp_path, written_png,
):
    character_sets.attach_source_image(
        db_session, character_set, data=png_bytes(96, 96),
        content_type="image/png", original_filename="mara.png",
    )
    workflow = _workflow(db_session, EDIT_MAPPING, path=_edit_graph(tmp_path))
    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side"],
    )
    provider = RecordingProvider(written_png)

    asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", workflow_id=workflow.id,
    ))

    assert len(provider.submissions) == 2
    for submission in provider.submissions:
        loader = submission["payload"]["4"]["inputs"]["image"]
        assert loader != "baked-in.png", "the export's image must be replaced"
        assert loader == provider.uploads[0]["upload_name"]


def test_the_photo_crosses_the_boundary_once_for_the_whole_sheet(
    db_session, character_set, png_bytes, tmp_path, written_png,
):
    """Six views is one picture, not six copies of it. Uploading per view
    would also give each view a different filename for the same bytes, which
    makes the provenance read as six different sources."""
    character_sets.attach_source_image(
        db_session, character_set, data=png_bytes(96, 96),
        content_type="image/png", original_filename="mara.png",
    )
    workflow = _workflow(db_session, EDIT_MAPPING, path=_edit_graph(tmp_path))
    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side", "full_body"],
    )
    provider = RecordingProvider(written_png)

    asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=provider,
        provider_id="comfyui", workflow_id=workflow.id,
    ))

    assert len(provider.uploads) == 1


def test_each_view_records_which_picture_it_came_from(
    db_session, character_set, png_bytes, tmp_path, written_png,
):
    """Otherwise a sheet cannot be traced back to its subject, which is the
    whole reason for supplying one."""
    source = character_sets.attach_source_image(
        db_session, character_set, data=png_bytes(96, 96),
        content_type="image/png", original_filename="mara.png",
    )
    workflow = _workflow(db_session, EDIT_MAPPING, path=_edit_graph(tmp_path))
    version = character_sets.create_version(db_session, character_set, slots=["front"])

    asyncio.run(character_set_generation.generate_version(
        db_session, version, provider=RecordingProvider(written_png),
        provider_id="comfyui", workflow_id=workflow.id,
    ))

    view = character_sets.list_views(db_session, version)[0]
    assert view.provenance.get("source_image_id") == source.id
    assert view.provenance.get("source_image_sha256") == source.sha256
