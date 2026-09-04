"""The frame a clip has to land on.

Continuity so far has been about where a shot *starts*: take the end frame of
the clip before it and begin there. That leaves the other end unconstrained,
so each clip drifts a little and the next shot inherits the drift. When both
ends are already approved - image A opens the shot, image B opens the next one
- the honest thing is to say so, and let the model interpolate between two
fixed points instead of guessing where to finish.

MiniMax H3 has taken a `last_frame` since before any of this was written. What
was missing was a way to say which image belongs there.

The one thing this must not become is another positional reference slot.
`referenceImage2` means "the second image this graph conditions on", and the
resolver fills it with a canonical character view. Wiring that to `last_frame`
would end every clip on a studio portrait of the character against a plain
backdrop - correct hashes, correct lineage, wrong film.
"""

import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project, Scene, Shot, Take
from app.services import character_sets, continuity_frames, job_payload, shot_conditioning


def _shot(db, scene, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=kwargs.pop("order", 2),
        image_prompt="masterpiece", status="Draft", **kwargs,
    )
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


@pytest.fixture()
def approved_video_take(
    db_session: Session, sample_shot: Shot, tmp_path, synthesise_clip
):
    path = synthesise_clip(
        os.path.join(str(tmp_path), "source.mp4"),
        with_audio=False, duration=1.0, frame_rate=24.0, moving=True,
    )
    take = Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=path,
        duration_sec=1.0, review_status="Approved",
    )
    db_session.add(take)
    db_session.commit()
    db_session.refresh(take)
    return take


@pytest.fixture()
def approved_image_take(
    db_session: Session, sample_project: Project, tmp_path, png_bytes,
):
    """An approved still from a shot of its own, so it can be a target frame."""
    scene = db_session.query(Scene).filter(
        Scene.project_id == sample_project.id
    ).first()
    shot = _shot(db_session, scene, order=9)
    path = os.path.join(str(tmp_path), "landing.png")
    with open(path, "wb") as handle:
        handle.write(png_bytes(128, 128))
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path=path,
        width=128, height=128, review_status="Approved",
    )
    db_session.add(take)
    db_session.commit()
    db_session.refresh(take)
    return take


# ---------------------------------------------------------------------------
# The logical field
# ---------------------------------------------------------------------------

def test_the_end_frame_is_its_own_logical_field():
    """Not a reference slot, because it does not mean the same thing.

    A reference conditions the render; the end frame fixes where the clip
    stops. A workflow binds them to different node inputs, so they cannot share
    a name without one silently arriving in the other's place.
    """
    assert job_payload.END_FRAME_IMAGE == "endFrameImage"
    assert job_payload.END_FRAME_IMAGE in job_payload.LOGICAL_FIELDS
    assert job_payload.END_FRAME_IMAGE not in job_payload.REFERENCE_IMAGE_FIELDS


def test_an_end_frame_mapping_is_not_counted_as_reference_capacity():
    """Otherwise a graph taking one reference would claim to take two."""
    mapping = {"referenceImage": {}, "endFrameImage": {}}
    assert job_payload.reference_capacity(mapping) == 1


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def test_a_shot_can_be_told_which_approved_frame_to_land_on(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take,
):
    continuity_frames.extract_frame(db_session, approved_image_take)
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")

    continuity_frames.bind_end_frame(
        db_session, sample_project.id, shot, approved_image_take.id
    )

    assert shot.end_frame_take_id == approved_image_take.id


def test_a_shot_cannot_land_on_its_own_take(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take,
):
    """The clip would have to already exist to end on a frame cut from itself."""
    continuity_frames.extract_frame(db_session, approved_image_take)
    own_shot = db_session.query(Shot).filter(
        Shot.id == approved_image_take.shot_id
    ).first()

    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.bind_end_frame(
            db_session, sample_project.id, own_shot, approved_image_take.id
        )
    assert "own" in str(exc.value).lower()


def test_an_unapproved_take_cannot_be_an_end_frame(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take,
):
    continuity_frames.extract_frame(db_session, approved_image_take)
    approved_image_take.review_status = "Rejected"
    db_session.commit()
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")

    with pytest.raises(continuity_frames.ContinuityFrameError):
        continuity_frames.bind_end_frame(
            db_session, sample_project.id, shot, approved_image_take.id
        )


def test_clearing_an_end_frame_leaves_the_start_frame_alone(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take, approved_video_take,
):
    """The two ends are bound separately and cleared separately."""
    continuity_frames.extract_frame(db_session, approved_image_take)
    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    continuity_frames.bind_end_frame(
        db_session, sample_project.id, shot, approved_image_take.id
    )

    continuity_frames.clear_end_frame(db_session, shot)

    assert shot.end_frame_take_id is None
    assert shot.continuity_source_take_id == approved_video_take.id


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def test_the_end_frame_resolves_beside_the_references_not_among_them(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, approved_image_take, approved_video_take,
    png_bytes,
):
    """It must not consume a reference slot, or identity loses one.

    A shot conditioned on a character set and landing on a known frame needs
    both: the reference inputs carry who this is, and `last_frame` carries
    where it stops. Counting the end frame among the references would push the
    canonical view out of a two-input workflow.
    """
    character_set = character_sets.create_set(
        db_session, project_id=sample_project.id, name="Mara",
        character_id=sample_character.id, appearance="Silver hair",
    )
    version = character_sets.create_version(db_session, character_set, slots=["front"])
    for view in character_sets.list_views(db_session, version):
        character_sets.attach_view_image(
            db_session, view, data=png_bytes(64, 64), content_type="image/png",
            original_filename="front.png", provenance={"provider_id": "mock"},
        )
    character_sets.approve_version(db_session, version)

    continuity_frames.extract_frame(db_session, approved_image_take)
    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(
        db_session, sample_scene, generation_mode="image-to-video",
        character_set_ids=[character_set.id],
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    continuity_frames.bind_end_frame(
        db_session, sample_project.id, shot, approved_image_take.id
    )

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert resolved.problems == []
    assert resolved.end_frame is not None
    assert resolved.end_frame_take_id == approved_image_take.id
    assert resolved.end_frame_sha256
    assert all(
        entry.source != shot_conditioning.SOURCE_END_FRAME
        for entry in resolved.images
    ), "the end frame is not one of the reference images"


def test_an_end_frame_whose_take_lost_approval_blocks_the_shot(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take, approved_video_take,
):
    """Same rule as the start frame: a withdrawn approval stops the run.

    The bytes on disk still hash the same, so nothing else would notice.
    """
    continuity_frames.extract_frame(db_session, approved_image_take)
    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    continuity_frames.bind_end_frame(
        db_session, sample_project.id, shot, approved_image_take.id
    )

    approved_image_take.review_status = "Rejected"
    db_session.commit()

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert resolved.problems, "a rejected end frame must stop the run"
    assert any("end" in problem.lower() for problem in resolved.problems)
    assert resolved.end_frame is None


# ---------------------------------------------------------------------------
# Reaching the provider
# ---------------------------------------------------------------------------

def test_provenance_records_the_landing_apart_from_the_conditioning(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take, approved_video_take,
):
    """Two lists, because they answer two questions.

    ``images`` says what the render was conditioned on and is counted against
    the workflow's reference slots. The landing is neither, so folding it in
    would make a one-reference workflow look over capacity.
    """
    continuity_frames.extract_frame(db_session, approved_image_take)
    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    continuity_frames.bind_end_frame(
        db_session, sample_project.id, shot, approved_image_take.id
    )

    record = shot_conditioning.provenance(
        shot_conditioning.resolve(db_session, sample_project.id, shot)
    )

    assert len(record["images"]) == 1, "only the start frame conditions this shot"
    assert record["images"][0]["source"] == shot_conditioning.SOURCE_CONTINUITY
    assert record["end_frame"]["take_id"] == approved_image_take.id
    assert record["end_frame"]["sha256"]


@pytest.mark.asyncio
async def test_the_queue_sends_the_landing_to_its_own_workflow_input(
    db_session: Session, sample_shot: Shot, sample_workflow_json, tmp_path,
):
    """It must arrive at `last_frame`, not at a reference slot.

    A workflow binding one reference and one end frame takes two images, but
    they are not interchangeable: swapping them would start the clip where it
    was meant to finish.
    """
    import uuid as _uuid

    from app.models import GenerationJob, Workflow
    from app.services import workflow_registry
    from app.services.queue_manager import QueueManager

    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Start and end", purpose="image-to-video"
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "ckpt_name"},
        job_payload.END_FRAME_IMAGE: {"nodeId": "5", "field": "width"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    workflow.validation_status = "valid"
    db_session.add(workflow)
    db_session.commit()

    start = tmp_path / "start.png"
    landing = tmp_path / "landing.png"
    start.write_bytes(b"start frame")
    landing.write_bytes(b"landing frame")
    job = GenerationJob(
        id=str(_uuid.uuid4()), shot_id=sample_shot.id, workflow_id=workflow.id,
        parameter_map={job_payload.POSITIVE_PROMPT: "hero", job_payload.SEED: 5},
        reference_provenance={
            "images": [{
                "image_id": "start", "file_path": str(start),
                "mime_type": "image/png", "submitted": True, "source": "continuity",
            }],
            "end_frame": {
                "image_id": "landing", "file_path": str(landing),
                "mime_type": "image/png", "take_id": "take-b", "sha256": "b" * 64,
            },
        },
        seed=5, status="Queued",
    )
    db_session.add(job)
    db_session.commit()

    class UploadProvider:
        async def upload_reference_image(self, file_path, *, upload_name, mime_type):
            name = os.path.basename(file_path)
            return {
                "name": name, "subfolder": f"cas/{job.id}",
                "type": "input", "workflow_value": f"cas/{job.id}/{name}",
            }

    await QueueManager()._prepare_reference_inputs(db_session, job, UploadProvider())

    assert job.parameter_map[job_payload.REFERENCE_IMAGE] == f"cas/{job.id}/start.png"
    assert job.parameter_map[job_payload.END_FRAME_IMAGE] == f"cas/{job.id}/landing.png"
    assert job.reference_provenance["end_frame"]["comfyui"]["mapping"] == {
        "nodeId": "5", "field": "width",
    }


# ---------------------------------------------------------------------------
# Over HTTP
# ---------------------------------------------------------------------------

def test_the_end_frame_is_bound_and_cleared_over_http(
    client, db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take,
):
    continuity_frames.extract_frame(db_session, approved_image_take)
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")
    path = (
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}"
        f"/shots/{shot.id}/end-frame"
    )

    bound = client.put(path, json={"source_take_id": approved_image_take.id})
    assert bound.status_code == 200, bound.text
    body = bound.json()
    assert body["end_frame_take_id"] == approved_image_take.id
    assert body["end_frame"]["sha256"]
    assert body["end_frame_shot_label"], "the user has to see which shot it came from"

    cleared = client.delete(path)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["end_frame_take_id"] is None


def test_binding_a_take_from_another_project_is_refused_over_http(
    client, db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_image_take,
):
    """A frame from someone else's project must never become this shot's target."""
    continuity_frames.extract_frame(db_session, approved_image_take)
    shot = _shot(db_session, sample_scene, generation_mode="image-to-video")
    other = client.post("/api/projects", json={"title": "Elsewhere"}).json()

    response = client.put(
        f"/api/projects/{other['id']}/scenes/{sample_scene.id}"
        f"/shots/{shot.id}/end-frame",
        json={"source_take_id": approved_image_take.id},
    )
    assert response.status_code in (404, 409), response.text
