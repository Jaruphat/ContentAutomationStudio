"""
What actually conditions one shot's generation, resolved in one place.

A shot can now be conditioned from three directions at once: images someone
attached by hand, the canonical views of the character sets it binds, and the
end frame of the take it continues from. Generation, regeneration and preflight
all have to agree about which images those are and in what order, or the run
the user confirmed is not the run that executes.

The properties asserted here:

* **One ordered answer.** The continuity frame comes first because for an
  image-to-video shot it *is* the first frame; identity views follow, then the
  hand-attached plates.
* **Every refusal is a blocker, never a skip.** A shot naming a character set
  with nothing approved, or continuing from a take that was rejected after the
  frame was cut, must stop the run rather than quietly render something else.
* **Provenance is exact.** Ids, hashes and which of the three roles each image
  is playing are recorded, so a take can be explained without guessing.
"""

import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project, Scene, Shot, Take
from app.services import (
    character_sets,
    continuity_frames,
    reference_bible,
    shot_conditioning,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _approved_set(
    db, project_id, character_id, png_bytes, *, name, seed=1, slots=None
):
    character_set = character_sets.create_set(
        db, project_id=project_id, name=name, character_id=character_id,
        appearance="Close-cropped silver hair.",
    )
    version = character_sets.create_version(
        db, character_set, slots=slots or ["front"]
    )
    for index, view in enumerate(character_sets.list_views(db, version)):
        character_sets.attach_view_image(
            db, view, data=png_bytes(64 + seed + index, 64),
            content_type="image/png", original_filename="front.png",
            provenance={"provider_id": "mock", "seed": seed},
        )
    character_sets.approve_version(db, version)
    return character_set


def _shot(db, scene, *, order=2, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
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
def uploaded_plate(db_session: Session, sample_project: Project, png_bytes):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Lantern",
    )
    return reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(96, 96),
        original_filename="lantern.png", content_type="image/png",
    )


# ---------------------------------------------------------------------------
# Nothing bound
# ---------------------------------------------------------------------------

def test_a_shot_with_no_conditioning_resolves_to_nothing(
    db_session: Session, sample_project: Project, sample_shot: Shot
):
    resolved = shot_conditioning.resolve(
        db_session, sample_project.id, sample_shot
    )
    assert resolved.images == []
    assert resolved.problems == []
    assert resolved.reference_image_ids == []
    assert resolved.character_set_ids == []
    assert resolved.continuity_source_take_id == ""


# ---------------------------------------------------------------------------
# Ordering and provenance
# ---------------------------------------------------------------------------

def test_the_hand_off_frame_leads_then_identity_then_hand_attached_plates(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, approved_video_take, uploaded_plate, png_bytes,
):
    """Order is not cosmetic: for image-to-video the first image is the frame."""
    frame = continuity_frames.extract_frame(db_session, approved_video_take)
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes, name="Mara",
    )
    shot = _shot(
        db_session, sample_scene, generation_mode="image-to-video",
        video_prompt="she keeps walking",
        character_set_ids=[character_set.id],
        reference_asset_ids=[uploaded_plate.id],
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert resolved.problems == []
    assert [entry.source for entry in resolved.images] == [
        shot_conditioning.SOURCE_CONTINUITY,
        shot_conditioning.SOURCE_CHARACTER_SET,
        shot_conditioning.SOURCE_REFERENCE,
    ]
    assert resolved.images[0].image.id == frame.reference_image_id
    assert resolved.images[2].image.id == uploaded_plate.id
    assert resolved.continuity_source_take_id == approved_video_take.id
    assert resolved.continuity_source_sha256 == frame.sha256
    assert resolved.character_set_ids == [character_set.id]
    assert resolved.character_set_sha256s == [
        character_sets.canonical_digest(db_session, character_set)
    ]
    # The hand-attached plates stay the shot's own reference list, unmixed with
    # what identity and continuity contributed - take lineage compares that
    # list against the shot's, and folding the others in would read as a
    # permanent mismatch.
    assert resolved.reference_image_ids == [uploaded_plate.id]


def test_provenance_names_every_image_and_the_role_it_played(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes, name="Mara",
    )
    shot = _shot(db_session, sample_scene, character_set_ids=[character_set.id])

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)
    provenance = shot_conditioning.provenance(resolved)

    assert len(provenance["images"]) == 1
    entry = provenance["images"][0]
    assert entry["source"] == shot_conditioning.SOURCE_CHARACTER_SET
    assert entry["sha256"] == resolved.images[0].image.sha256
    assert entry["detail"]["character_set_id"] == character_set.id
    assert entry["detail"]["view_slot"] == "front"
    # The queue uploads from this record, so the path has to be in it.
    assert entry["file_path"] == resolved.images[0].image.file_path


def test_single_input_scene_selects_full_body_but_preserves_all_conceptual_views(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    character_set = _approved_set(
        db_session,
        sample_project.id,
        sample_character.id,
        png_bytes,
        name="Mara",
        slots=["front", "expression", "full_body"],
    )
    shot = _shot(db_session, sample_scene, character_set_ids=[character_set.id])
    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    selected = shot_conditioning.select_for_submission(resolved, max_images=1)
    provenance = shot_conditioning.provenance(selected)

    assert selected.problems == []
    assert [entry.detail["view_slot"] for entry in selected.submitted_images] == [
        "full_body"
    ]
    assert [item["detail"]["view_slot"] for item in provenance["images"]] == [
        "front", "expression", "full_body"
    ]
    assert [item["submitted"] for item in provenance["images"]] == [False, False, True]
    assert provenance["images"][2]["selection_reason"] == (
        "primary canonical character-set view (full_body preferred)"
    )
    assert selected.character_set_sha256s == [
        character_sets.canonical_digest(db_session, character_set)
    ]


def test_single_input_continuity_is_sole_submission_while_identity_stays_conceptual(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, approved_video_take, png_bytes,
):
    frame = continuity_frames.extract_frame(db_session, approved_video_take)
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", slots=["front", "full_body"],
    )
    shot = _shot(
        db_session, sample_scene, generation_mode="image-to-video",
        video_prompt="continue", character_set_ids=[character_set.id],
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=1
    )
    provenance = shot_conditioning.provenance(selected)

    assert selected.problems == []
    assert [entry.image.id for entry in selected.submitted_images] == [
        frame.reference_image_id
    ]
    assert [item["submitted"] for item in provenance["images"]] == [True, False, False]
    assert provenance["images"][0]["selection_reason"] == (
        "explicit continuity frame is the workflow input"
    )
    assert selected.character_set_sha256s == [
        character_sets.canonical_digest(db_session, character_set)
    ]


def test_single_input_blocks_multiple_character_sets_without_continuity(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    first = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes, name="Mara"
    )
    second = _approved_set(
        db_session, sample_project.id, None, png_bytes, name="Ivo", seed=2
    )
    shot = _shot(
        db_session, sample_scene, character_set_ids=[first.id, second.id]
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=1
    )

    assert selected.submitted_images == []
    assert any("multiple character sets" in problem for problem in selected.problems)


def test_single_input_blocks_conflicting_hand_references(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    uploaded_plate, png_bytes,
):
    sheet = reference_bible.create_sheet(
        db_session, project_id=sample_project.id, kind="prop", name="Compass"
    )
    second = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(80, 80),
        original_filename="compass.png", content_type="image/png",
    )
    shot = _shot(
        db_session, sample_scene,
        reference_asset_ids=[uploaded_plate.id, second.id],
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=1
    )

    assert selected.submitted_images == []
    assert any("multiple hand references" in problem for problem in selected.problems)


def test_multi_reference_capability_submits_every_resolved_image_unchanged(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, uploaded_plate, png_bytes,
):
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", slots=["front", "full_body"],
    )
    shot = _shot(
        db_session, sample_scene, character_set_ids=[character_set.id],
        reference_asset_ids=[uploaded_plate.id],
    )
    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    selected = shot_conditioning.select_for_submission(resolved, max_images=None)

    assert [entry.image.id for entry in selected.submitted_images] == [
        entry.image.id for entry in selected.images
    ]
    assert all(item["submitted"] for item in shot_conditioning.provenance(selected)["images"])


# ---------------------------------------------------------------------------
# Character set blockers
# ---------------------------------------------------------------------------

def test_a_set_with_nothing_approved_blocks_rather_than_generating_unconditioned(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character,
):
    character_set = character_sets.create_set(
        db_session, project_id=sample_project.id, name="Mara",
        character_id=sample_character.id,
    )
    shot = _shot(db_session, sample_scene, character_set_ids=[character_set.id])

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert resolved.images == []
    assert resolved.problems
    assert "no approved canonical version" in resolved.problems[0]


def test_a_character_set_from_another_project_cannot_condition_this_shot(
    db_session: Session, sample_project: Project, sample_scene: Scene, png_bytes,
):
    other = Project(id=str(uuid.uuid4()), title="Other")
    db_session.add(other)
    db_session.commit()
    foreign = _approved_set(db_session, other.id, None, png_bytes, name="Intruder")
    shot = _shot(db_session, sample_scene, character_set_ids=[foreign.id])

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert resolved.images == []
    assert any("another project" in problem for problem in resolved.problems)


# ---------------------------------------------------------------------------
# Continuity blockers
# ---------------------------------------------------------------------------

def test_a_source_take_rejected_after_the_cut_blocks_the_shot_that_follows(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_video_take,
):
    """Approval is what a hand-off rests on, and it can be withdrawn later."""
    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(
        db_session, sample_scene, generation_mode="image-to-video",
        video_prompt="she keeps walking",
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )

    approved_video_take.review_status = "Rejected"
    db_session.commit()

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)
    assert resolved.images == []
    assert any("no longer approved" in problem for problem in resolved.problems)


def test_a_source_take_left_behind_by_its_own_shot_blocks_its_descendants(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_shot: Shot, approved_video_take,
):
    """Recutting upstream invalidates the shots that continue from it.

    The frame itself is still on disk and still hashes the same, so nothing
    about the downstream shot's own content moved. What moved is the work the
    frame was lifted out of, and continuing from a superseded clip would put a
    hand-off in the cut that the delivered footage never contained.
    """
    from app.services import revisions

    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(
        db_session, sample_scene, generation_mode="image-to-video",
        video_prompt="she keeps walking",
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)
    approved_video_take.prompt_revision = sample_shot.prompt_revision
    approved_video_take.prompt_sha256 = sample_shot.prompt_sha256
    approved_video_take.content_sha256 = sample_shot.content_sha256
    db_session.commit()

    assert shot_conditioning.resolve(
        db_session, sample_project.id, shot
    ).problems == []

    # Edit the upstream shot: its approved take is now of a superseded revision.
    sample_shot.image_prompt = "a completely different opening"
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)
    assert resolved.images == []
    assert any("out of date" in problem for problem in resolved.problems)


def test_a_shot_set_to_continue_from_nothing_says_so(
    db_session: Session, sample_project: Project, sample_scene: Scene
):
    shot = _shot(
        db_session, sample_scene,
        continuity_source_mode=continuity_frames.MODE_END_FRAME,
    )
    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)
    assert resolved.images == []
    assert resolved.problems


def test_clearing_continuity_removes_the_blocker_with_it(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_video_take,
):
    continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(
        db_session, sample_scene, generation_mode="image-to-video",
        video_prompt="she keeps walking",
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    approved_video_take.review_status = "Rejected"
    db_session.commit()
    assert shot_conditioning.resolve(db_session, sample_project.id, shot).problems

    continuity_frames.clear_source(db_session, shot)
    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)
    assert resolved.problems == []
    assert resolved.images == []


# ---------------------------------------------------------------------------
# Several inputs: identity and the hand-off together
# ---------------------------------------------------------------------------

def test_two_inputs_carry_identity_and_the_hand_off_at_the_same_time(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, approved_video_take, png_bytes,
):
    """The point of a second slot: who it is, and where the last shot left off.

    With one input these compete and the frame wins, so identity survives only
    as far as the previous clip carried it and drifts a little further every
    hand-off. Given two, the canonical view holds the face and wardrobe while
    the frame holds the pose and lighting, which is the whole reason for
    keeping a character set at all.
    """
    frame = continuity_frames.extract_frame(db_session, approved_video_take)
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", slots=["full_body"],
    )
    shot = _shot(
        db_session, sample_scene, character_set_ids=[character_set.id],
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=2
    )

    assert selected.problems == []
    submitted = selected.submitted_images
    assert [entry.source for entry in submitted] == [
        shot_conditioning.SOURCE_CONTINUITY,
        shot_conditioning.SOURCE_CHARACTER_SET,
    ], "the frame leads because it is the start frame; identity rides alongside"
    assert submitted[0].image.id == frame.reference_image_id


def test_overflow_past_the_last_slot_stays_conceptual_and_says_why(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, approved_video_take, png_bytes,
):
    """Fewer slots than images is a truncation, and it has to be visible.

    Dropping a view silently would leave a take whose lineage claims more
    conditioning than the provider ever saw.
    """
    continuity_frames.extract_frame(db_session, approved_video_take)
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", slots=["full_body", "front", "side"],
    )
    shot = _shot(db_session, sample_scene, character_set_ids=[character_set.id])
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=2
    )

    assert selected.problems == []
    assert len(selected.submitted_images) == 2
    dropped = [entry for entry in selected.images if not entry.submitted]
    assert dropped, "a four-image shot cannot fit two slots"
    assert all(
        "not submitted" in entry.selection_reason for entry in dropped
    ), [entry.selection_reason for entry in dropped]


def test_a_hand_attached_plate_is_never_the_one_silently_dropped(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, uploaded_plate, approved_video_take, png_bytes,
):
    """Someone chose that picture for this shot, so losing it is a refusal.

    Canonical views past the first are interchangeable and dropping one costs
    nothing the user asked for. A hand-attached plate is a deliberate act, and
    quietly discarding it would render a different shot than the one approved.
    """
    continuity_frames.extract_frame(db_session, approved_video_take)
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", slots=["full_body"],
    )
    shot = _shot(
        db_session, sample_scene, character_set_ids=[character_set.id],
        reference_asset_ids=[uploaded_plate.id],
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=2
    )

    assert selected.problems, "dropping an explicit plate must block, not truncate"
    assert any("reference" in problem.lower() for problem in selected.problems)
    assert selected.submitted_images == []


def test_a_workflow_that_binds_no_reference_input_submits_nothing(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    """Zero slots is a real answer, not a missing one.

    A text-to-image graph has nowhere to put a reference. Treating zero as
    "unlimited" would send images into a workflow with no input bound to them,
    and treating it as one would submit into a mapping that does not exist.
    """
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes, name="Mara",
    )
    shot = _shot(db_session, sample_scene, character_set_ids=[character_set.id])

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=0
    )

    assert selected.submitted_images == []
    assert selected.images, "the binding is still real lineage, just not submitted"
