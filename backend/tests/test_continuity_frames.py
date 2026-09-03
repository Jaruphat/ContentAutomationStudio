"""
End-frame continuity - lifting the hand-off still out of an approved take.

An image-to-video shot has to start somewhere. Making it start on the last
frame of the previous shot is what turns a pile of clips into a sequence, and
it is the one piece of continuity that cannot be expressed as prompt text.

The properties asserted here are what the feature stands on:

* **Only approved video takes hand off.** A pending take is not a decision, and
  a still has no end frame; both are refused with a reason rather than
  silently producing nothing.
* **The frame is a real reference image.** Extracted bytes go through the
  Reference Bible, so a continuity frame conditions a job through the same
  validated, ownership-checked path as a hand-uploaded plate.
* **Binding is explicit.** A shot is never wired to its predecessor by
  position; someone chooses the source take, and reordering shots cannot
  silently rewire the cut.
* **One hand-off per take.** Re-cutting at a different timestamp replaces the
  frame in place, and the hash moving is what makes descendants stale.
"""

import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import ContinuityFrame, Project, Scene, Shot, Take
from app.services import continuity_frames


@pytest.fixture()
def video_take(db_session: Session, sample_shot: Shot, tmp_path, synthesise_clip):
    """An approved video take with a real clip on disk."""
    # A moving pattern, not a flat colour: a test about *which* frame was cut
    # proves nothing against a clip whose frames are all identical.
    path = synthesise_clip(
        os.path.join(str(tmp_path), "take.mp4"),
        with_audio=False, duration=1.0, frame_rate=24.0,
        width=320, height=180, moving=True,
    )
    take = Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=path,
        duration_sec=1.0, width=320, height=180, frame_rate=24.0,
        codec="h264", review_status="Approved",
    )
    db_session.add(take)
    db_session.commit()
    db_session.refresh(take)
    return take


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def test_the_end_frame_of_an_approved_clip_becomes_a_reference_image(
    db_session: Session, sample_project: Project, video_take
):
    frame = continuity_frames.extract_frame(db_session, video_take)

    assert frame.take_id == video_take.id
    assert frame.selection == continuity_frames.SELECTION_LAST
    assert frame.project_id == sample_project.id
    image = frame.image
    assert image is not None
    assert image.project_id == sample_project.id
    assert os.path.isfile(image.file_path)
    # Same dimensions as the clip: a hand-off frame is the final state of the
    # clip, not a thumbnail of it.
    assert (image.width, image.height) == (320, 180)
    assert frame.sha256 == image.sha256


def test_the_frame_lands_on_the_project_continuity_sheet(
    db_session: Session, sample_project: Project, video_take
):
    """Reference Bible storage, so one path conditions every job."""
    frame = continuity_frames.extract_frame(db_session, video_take)
    sheet = continuity_frames.continuity_sheet(db_session, sample_project.id)
    assert frame.image.sheet_id == sheet.id
    assert sheet.kind == "continuity"
    assert frame.image.provenance["source"] == "continuity_frame"
    assert frame.image.provenance["take_id"] == video_take.id


def test_an_explicit_timestamp_is_recorded_as_such(
    db_session: Session, video_take
):
    """Asking for the last frame and asking for one are different promises."""
    frame = continuity_frames.extract_frame(db_session, video_take, at_sec=0.25)
    assert frame.selection == continuity_frames.SELECTION_EXPLICIT
    assert frame.frame_time_sec == pytest.approx(0.25, abs=0.05)


def test_a_timestamp_past_the_end_of_the_clip_is_refused(
    db_session: Session, video_take
):
    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.extract_frame(db_session, video_take, at_sec=9.0)
    assert exc.value.code == "timestamp_out_of_range"


def test_an_unapproved_take_cannot_hand_off(db_session: Session, video_take):
    """A pending take is not a decision, so nothing may be built on it."""
    video_take.review_status = "Pending"
    db_session.commit()
    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.extract_frame(db_session, video_take)
    assert exc.value.code == "take_not_approved"


def test_a_still_take_has_no_end_frame(
    db_session: Session, sample_shot: Shot, png_bytes, tmp_path
):
    path = os.path.join(str(tmp_path), "still.png")
    with open(path, "wb") as f:
        f.write(png_bytes(64, 64))
    take = Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=path,
        duration_sec=0.0, review_status="Approved",
    )
    db_session.add(take)
    db_session.commit()

    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.extract_frame(db_session, take)
    assert exc.value.code == "not_a_video"


def test_recutting_replaces_the_hand_off_instead_of_adding_one(
    db_session: Session, video_take
):
    """One take hands off one frame, or the question has no single answer."""
    first = continuity_frames.extract_frame(db_session, video_take)
    first_sha = first.sha256

    second = continuity_frames.extract_frame(db_session, video_take, at_sec=0.0)

    assert second.id == first.id
    assert db_session.query(ContinuityFrame).filter(
        ContinuityFrame.take_id == video_take.id
    ).count() == 1
    assert second.selection == continuity_frames.SELECTION_EXPLICIT
    # The first frame of a clip is not its last, so the hash must have moved -
    # that movement is what makes every shot seeded from it stale.
    assert second.sha256 != first_sha


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def test_binding_a_source_take_is_explicit_and_reversible(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_shot: Shot, video_take,
):
    continuity_frames.extract_frame(db_session, video_take)
    next_shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
        generation_mode="image-to-video", video_prompt="she keeps walking",
    )
    db_session.add(next_shot)
    db_session.commit()

    continuity_frames.bind_source(
        db_session, sample_project.id, next_shot, video_take.id
    )
    assert next_shot.continuity_source_take_id == video_take.id
    assert next_shot.continuity_source_mode == continuity_frames.MODE_END_FRAME

    continuity_frames.clear_source(db_session, next_shot)
    assert next_shot.continuity_source_take_id is None
    assert next_shot.continuity_source_mode == continuity_frames.MODE_NONE


def test_a_shot_cannot_be_seeded_by_its_own_take(
    db_session: Session, sample_project: Project, sample_shot: Shot, video_take
):
    """Continuity is a hand-off between shots; a self-reference is a loop."""
    continuity_frames.extract_frame(db_session, video_take)
    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.bind_source(
            db_session, sample_project.id, sample_shot, video_take.id
        )
    assert exc.value.code == "self_continuity"


def test_a_take_from_another_project_cannot_seed_this_shot(
    db_session: Session, sample_scene: Scene, video_take
):
    continuity_frames.extract_frame(db_session, video_take)
    other = Project(id=str(uuid.uuid4()), title="Other")
    db_session.add(other)
    db_session.commit()
    shot = Shot(id=str(uuid.uuid4()), scene_id=sample_scene.id, order=3)
    db_session.add(shot)
    db_session.commit()

    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.bind_source(db_session, other.id, shot, video_take.id)
    assert exc.value.code == "take_not_found"


def test_binding_a_take_with_no_extracted_frame_is_refused(
    db_session: Session, sample_project: Project, sample_scene: Scene, video_take
):
    """Binding names a frame that exists, not one that might be cut later."""
    shot = Shot(id=str(uuid.uuid4()), scene_id=sample_scene.id, order=4)
    db_session.add(shot)
    db_session.commit()

    with pytest.raises(continuity_frames.ContinuityFrameError) as exc:
        continuity_frames.bind_source(
            db_session, sample_project.id, shot, video_take.id
        )
    assert exc.value.code == "no_continuity_frame"


# ---------------------------------------------------------------------------
# Candidates and resolution
# ---------------------------------------------------------------------------

def test_candidates_exclude_the_takes_of_the_shot_being_seeded(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_shot: Shot, video_take,
):
    continuity_frames.extract_frame(db_session, video_take)
    next_shot = Shot(id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2)
    db_session.add(next_shot)
    db_session.commit()

    for_next = continuity_frames.candidates(
        db_session, sample_project.id, next_shot
    )
    for_self = continuity_frames.candidates(
        db_session, sample_project.id, sample_shot
    )
    assert [c.take_id for c in for_next] == [video_take.id]
    assert for_self == []


def test_resolving_a_bound_source_yields_the_frame_image(
    db_session: Session, sample_project: Project, sample_scene: Scene, video_take
):
    frame = continuity_frames.extract_frame(db_session, video_take)
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
        generation_mode="image-to-video",
    )
    db_session.add(shot)
    db_session.commit()
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, video_take.id
    )

    image, problems = continuity_frames.resolve_source_image(
        db_session, sample_project.id, shot
    )
    assert problems == []
    assert image is not None
    assert image.id == frame.reference_image_id


def test_a_bound_source_whose_take_vanished_blocks_rather_than_skips(
    db_session: Session, sample_project: Project, sample_scene: Scene, video_take
):
    """A shot asking for continuity stops the run, not renders unconditioned."""
    continuity_frames.extract_frame(db_session, video_take)
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
        generation_mode="image-to-video",
    )
    db_session.add(shot)
    db_session.commit()
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, video_take.id
    )

    db_session.delete(video_take)
    db_session.commit()

    image, problems = continuity_frames.resolve_source_image(
        db_session, sample_project.id, shot
    )
    assert image is None
    assert problems and "continuity" in problems[0].lower()
