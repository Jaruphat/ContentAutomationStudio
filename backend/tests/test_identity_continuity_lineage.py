"""
Lineage for canonical identity and end-frame continuity.

Two new things can change what a shot would generate without any of its own
text moving: the character set it is bound to can have a newer version
approved, and the take it continues from can have its hand-off frame re-cut.
Both must behave exactly like every other dependency already does - fold into
the shot's content digest, advance its revision, and mark it stale - and both
must do so *selectively*.

Selectivity is the whole point. A project has one Story Bible and many scenes;
if approving a new look for one character invalidated every shot in the film,
nobody would ever approve one.

Also asserted here: a shot that uses neither feature hashes exactly as it did
before either existed. Without that, upgrading the application would mark
every previously generated shot in every project stale on first refresh.
"""

import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project, Scene, Shot, Take
from app.services import character_sets, continuity_frames, revisions


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _approved_set(db, project_id, character_id, png_bytes, *, name, seed):
    """A character set with one approved canonical version."""
    character_set = character_sets.create_set(
        db, project_id=project_id, name=name, character_id=character_id,
        appearance="Close-cropped silver hair.",
    )
    _approve_new_version(db, character_set, png_bytes, seed=seed)
    return character_set


def _approve_new_version(db, character_set, png_bytes, *, seed):
    version = character_sets.create_version(
        db, character_set, slots=["front"],
    )
    for view in character_sets.list_views(db, version):
        character_sets.attach_view_image(
            db, view, data=png_bytes(64 + seed, 64),
            content_type="image/png", original_filename="front.png",
            provenance={"provider_id": "mock", "seed": seed},
        )
    return character_sets.approve_version(db, version)


def _shot(db, scene, *, order, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        image_prompt="masterpiece", status="Draft", **kwargs,
    )
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


def _generated(db, shot):
    """Pretend this shot has been generated at its current revision."""
    revisions.mark_generated(db, shot)
    db.commit()
    db.refresh(shot)


# ---------------------------------------------------------------------------
# Backwards compatibility
# ---------------------------------------------------------------------------

def test_a_shot_using_neither_feature_keeps_the_digest_it_already_had(
    db_session: Session, sample_project: Project, sample_shot: Shot
):
    """Upgrading must not mark every existing shot in every project stale.

    An unbound shot has to hash to the same value the previous build produced,
    which is only true if the new dependencies contribute nothing at all when
    there is nothing bound.
    """
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)
    baseline = sample_shot.content_sha256
    assert baseline

    _generated(db_session, sample_shot)
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)

    assert sample_shot.content_sha256 == baseline
    assert sample_shot.prompt_revision == 1
    assert sample_shot.is_stale is False


# ---------------------------------------------------------------------------
# Character set lineage
# ---------------------------------------------------------------------------

def test_binding_a_character_set_advances_the_shots_revision(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, sample_shot: Shot, png_bytes,
):
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", seed=1,
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)
    before = sample_shot.prompt_revision

    sample_shot.character_set_ids = [character_set.id]
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(sample_shot)

    assert sample_shot.prompt_revision == before + 1
    assert list(sample_shot.character_set_sha256s) == [
        character_sets.canonical_digest(db_session, character_set)
    ]


def test_approving_a_new_version_invalidates_only_the_bound_shots(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    """Selective descendant invalidation, which is what makes approval usable.

    A new look for one character must reach the shots that character appears
    in and nothing else. Invalidating the whole film would make re-approving a
    character a decision nobody could afford to take.
    """
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", seed=1,
    )
    bound = _shot(
        db_session, sample_scene, order=1,
        character_set_ids=[character_set.id],
    )
    unbound = _shot(db_session, sample_scene, order=2)

    revisions.refresh_project(db_session, sample_project.id)
    for shot in (bound, unbound):
        db_session.refresh(shot)
        _generated(db_session, shot)
    bound_revision = bound.prompt_revision
    unbound_revision = unbound.prompt_revision

    _approve_new_version(db_session, character_set, png_bytes, seed=9)
    advanced = revisions.refresh_project(db_session, sample_project.id)

    db_session.refresh(bound)
    db_session.refresh(unbound)
    assert advanced == [bound.id]
    assert bound.prompt_revision == bound_revision + 1
    assert bound.is_stale is True
    # The shot that does not use this character is untouched in every respect.
    assert unbound.prompt_revision == unbound_revision
    assert unbound.is_stale is False


def test_editing_the_identity_spec_alone_does_not_invalidate_anything(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    """Approval is what publishes an identity, not editing the text.

    Generation reads the approved version, so a draft edit must not make
    delivered work stale. What it does do is stop the set reading as current,
    which is how the Storyboard offers a regeneration rather than forcing one.
    """
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", seed=1,
    )
    bound = _shot(
        db_session, sample_scene, order=1,
        character_set_ids=[character_set.id],
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(bound)
    _generated(db_session, bound)
    revision = bound.prompt_revision

    character_sets.update_set(
        db_session, character_set, {"wardrobe": "Now a rain-soaked overcoat."}
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(bound)

    assert bound.prompt_revision == revision
    assert bound.is_stale is False
    assert character_sets.approved_version_is_current(
        db_session, character_set
    ) is False


def test_unapproving_a_set_invalidates_the_shots_that_relied_on_it(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    """Withdrawing canonical status removes what the shot was conditioned on."""
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", seed=1,
    )
    bound = _shot(
        db_session, sample_scene, order=1,
        character_set_ids=[character_set.id],
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(bound)
    _generated(db_session, bound)

    character_sets.unapprove_version(
        db_session, character_sets.approved_version(db_session, character_set)
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(bound)

    assert bound.is_stale is True
    assert list(bound.character_set_sha256s) == [""]


# ---------------------------------------------------------------------------
# Continuity lineage
# ---------------------------------------------------------------------------

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


def test_recutting_the_hand_off_frame_invalidates_only_its_dependants(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_video_take,
):
    continuity_frames.extract_frame(db_session, approved_video_take)
    seeded = _shot(
        db_session, sample_scene, order=2,
        generation_mode="image-to-video", video_prompt="she keeps walking",
    )
    independent = _shot(db_session, sample_scene, order=3)
    continuity_frames.bind_source(
        db_session, sample_project.id, seeded, approved_video_take.id
    )

    revisions.refresh_project(db_session, sample_project.id)
    for shot in (seeded, independent):
        db_session.refresh(shot)
        _generated(db_session, shot)
    seeded_revision = seeded.prompt_revision
    independent_revision = independent.prompt_revision

    # Cut the hand-off somewhere else in the clip.
    continuity_frames.extract_frame(
        db_session, approved_video_take, at_sec=0.0
    )
    revisions.refresh_project(db_session, sample_project.id)

    db_session.refresh(seeded)
    db_session.refresh(independent)
    assert seeded.prompt_revision == seeded_revision + 1
    assert seeded.is_stale is True
    assert independent.prompt_revision == independent_revision
    assert independent.is_stale is False


def test_a_vanished_continuity_source_is_a_content_change(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_video_take,
):
    """Pointing at a deleted frame is different from pointing at nothing.

    Both would otherwise hash the same, and a shot whose source disappeared
    would keep reading as current right up until the run failed.
    """
    continuity_frames.extract_frame(db_session, approved_video_take)
    seeded = _shot(
        db_session, sample_scene, order=2, generation_mode="image-to-video",
        video_prompt="she keeps walking",
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, seeded, approved_video_take.id
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(seeded)
    _generated(db_session, seeded)

    db_session.delete(approved_video_take)
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(seeded)

    assert seeded.is_stale is True


# ---------------------------------------------------------------------------
# Take lineage
# ---------------------------------------------------------------------------

def test_a_take_generated_against_an_older_identity_reads_as_stale(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, png_bytes,
):
    """The gate that stops superseded identity work being approved."""
    character_set = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Mara", seed=1,
    )
    shot = _shot(
        db_session, sample_scene, order=1,
        character_set_ids=[character_set.id],
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="C:/data/t.png",
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
        character_set_ids=list(shot.character_set_ids or []),
        character_set_sha256s=list(shot.character_set_sha256s or []),
        lineage={"job_id": "j1"},
        review_status="Pending",
    )
    db_session.add(take)
    db_session.commit()

    assert revisions.take_lineage_state(take, shot) == revisions.LINEAGE_CURRENT

    _approve_new_version(db_session, character_set, png_bytes, seed=9)
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    assert revisions.take_lineage_state(take, shot) == revisions.LINEAGE_STALE


def test_a_take_that_started_from_a_different_frame_reads_as_stale(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    approved_video_take,
):
    frame = continuity_frames.extract_frame(db_session, approved_video_take)
    shot = _shot(
        db_session, sample_scene, order=2, generation_mode="image-to-video",
        video_prompt="she keeps walking",
    )
    continuity_frames.bind_source(
        db_session, sample_project.id, shot, approved_video_take.id
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="C:/data/t.mp4",
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        continuity_source_take_id=approved_video_take.id,
        continuity_source_sha256=frame.sha256,
        lineage={"job_id": "j1"},
        review_status="Pending",
    )
    db_session.add(take)
    db_session.commit()
    assert revisions.take_lineage_state(take, shot) == revisions.LINEAGE_CURRENT

    continuity_frames.extract_frame(
        db_session, approved_video_take, at_sec=0.0
    )
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    assert revisions.take_lineage_state(take, shot) == revisions.LINEAGE_STALE
