"""Animating an approved still, without doing the bookkeeping by hand.

Building a moving episode by hand needed four things that are about the shape
of the data rather than about the film, and every one was learned by getting it
wrong: a still and its clip cannot be the same shot; the still has to come off
the cut; the clip has to be told which frame it starts on; and clips cannot
exist before their stills are drawn.

None of that is a decision. The decision is "animate this picture, for this
long, doing this" - so that is what the endpoint takes, and these are the
things it must get right on the caller's behalf.
"""

import os
import uuid

import pytest

from app.models import Take
from app.services import continuity_frames, motion, revisions


def _approved_still(db, shot, path, data) -> Take:
    with open(path, "wb") as handle:
        handle.write(data)
    revisions.refresh_project(db, shot.scene.project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path=path,
        duration_sec=0.0, width=96, height=64, review_status="Approved",
        prompt_revision=shot.prompt_revision, prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256, lineage={"job_id": "image-job"},
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
        character_set_ids=list(shot.character_set_ids or []),
        character_set_sha256s=list(shot.character_set_sha256s or []),
    )
    db.add(take)
    db.commit()
    db.refresh(take)
    return take


@pytest.fixture()
def still(db_session, sample_shot, tmp_path, png_bytes):
    sample_shot.dialogue = "I am a marshmallow."
    sample_shot.planned_duration_sec = 6.0
    db_session.add(sample_shot)
    db_session.commit()
    return _approved_still(
        db_session, sample_shot,
        os.path.join(str(tmp_path), "still.png"), png_bytes(96, 64),
    )


def test_it_offers_every_approved_still(db_session, sample_project, still):
    rows = motion.candidates(db_session, sample_project.id)

    assert [row["take_id"] for row in rows] == [still.id]
    assert rows[0]["clip_shot_id"] is None
    assert rows[0]["dialogue"] == "I am a marshmallow."


def test_animating_a_still_makes_a_second_shot(
    db_session, sample_project, sample_shot, still
):
    clip = motion.create_clip(
        db_session, sample_project.id, still.id,
        video_prompt="The little marshmallow waves and the fire flickers.",
        duration_sec=6.0, workflow_id="wf-i2v",
    )

    # A still and the clip made from it cannot be one shot: changing a shot to
    # image-to-video moves its content revision, which would put the frame
    # captured from its own still out of date the moment it was bound.
    assert clip.id != sample_shot.id
    assert clip.generation_mode == motion.VIDEO_MODE
    assert clip.workflow_preset_id == "wf-i2v"
    assert clip.planned_duration_sec == 6.0
    assert clip.continuity_source_take_id == still.id


def test_the_clip_carries_the_line_and_the_still_leaves_the_cut(
    db_session, sample_project, sample_shot, still
):
    clip = motion.create_clip(
        db_session, sample_project.id, still.id,
        video_prompt="He walks away down the path.",
        duration_sec=6.0, workflow_id="wf-i2v",
    )

    db_session.refresh(sample_shot)
    # Otherwise the film plays the picture and then the clip made from it.
    assert sample_shot.include_in_cut is False
    assert clip.include_in_cut is True
    # The line belongs to whatever is on the cut.
    assert clip.dialogue == "I am a marshmallow."


def test_it_captures_the_start_frame_itself(
    db_session, sample_project, still
):
    assert continuity_frames.get_frame(db_session, still.id) is None

    motion.create_clip(
        db_session, sample_project.id, still.id,
        video_prompt="The reeds sway.", duration_sec=5.0, workflow_id="wf-i2v",
    )

    frame = continuity_frames.get_frame(db_session, still.id)
    assert frame is not None
    assert frame.selection == continuity_frames.SELECTION_SOURCE_IMAGE


def test_a_still_that_is_already_moving_is_not_animated_twice(
    db_session, sample_project, still
):
    motion.create_clip(
        db_session, sample_project.id, still.id,
        video_prompt="He waves.", duration_sec=5.0, workflow_id="wf-i2v",
    )

    with pytest.raises(motion.MotionError) as exc:
        motion.create_clip(
            db_session, sample_project.id, still.id,
            video_prompt="He waves again.", duration_sec=5.0,
            workflow_id="wf-i2v",
        )
    assert exc.value.code == "clip_exists"

    rows = motion.candidates(db_session, sample_project.id)
    assert rows[0]["clip_shot_id"] is not None


def test_an_unapproved_still_cannot_be_animated(
    db_session, sample_project, sample_shot, tmp_path, png_bytes
):
    take = _approved_still(
        db_session, sample_shot, os.path.join(str(tmp_path), "pending.png"),
        png_bytes(96, 64),
    )
    take.review_status = "Pending"
    db_session.add(take)
    db_session.commit()

    with pytest.raises(motion.MotionError) as exc:
        motion.create_clip(
            db_session, sample_project.id, take.id,
            video_prompt="He waves.", duration_sec=5.0, workflow_id="wf-i2v",
        )
    assert exc.value.code == "take_not_approved"


def test_a_clip_needs_to_say_what_happens(db_session, sample_project, still):
    # A blank prompt still produces motion, and whatever it produces is what
    # the film gets.
    with pytest.raises(motion.MotionError) as exc:
        motion.create_clip(
            db_session, sample_project.id, still.id,
            video_prompt="   ", duration_sec=5.0, workflow_id="wf-i2v",
        )
    assert exc.value.code == "missing_prompt"


def test_a_clip_needs_a_length(db_session, sample_project, sample_shot, still):
    sample_shot.planned_duration_sec = 0.0
    db_session.add(sample_shot)
    db_session.commit()

    # The length is the frame count as much as the hold, so it is what the
    # clip costs to generate.
    with pytest.raises(motion.MotionError) as exc:
        motion.create_clip(
            db_session, sample_project.id, still.id,
            video_prompt="He waves.", duration_sec=0.0, workflow_id="wf-i2v",
        )
    assert exc.value.code == "missing_duration"


def test_the_endpoint_animates_and_reports(client, db_session, sample_project, still):
    listed = client.get(f"/api/projects/{sample_project.id}/motion")
    assert listed.status_code == 200
    assert [row["take_id"] for row in listed.json()] == [still.id]

    created = client.post(
        f"/api/projects/{sample_project.id}/motion/clips",
        json={
            "take_id": still.id,
            "video_prompt": "The little marshmallow waves.",
            "duration_sec": 6.0,
            "workflow_id": "wf-i2v",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["generation_mode"] == motion.VIDEO_MODE

    again = client.get(f"/api/projects/{sample_project.id}/motion")
    assert again.json()[0]["clip_shot_id"] == created.json()["id"]
