"""
Selective, revision-aware invalidation.

A generation dependency changing must invalidate exactly the shots it reaches
and nothing else. Blanket invalidation would throw away approved work every
time a typo was fixed; no invalidation would let a stale approved take be
delivered as if it matched the current brief. These tests pin the boundary
between the two, and that approved takes are kept as history either way.
"""

import uuid

import pytest

from app.models import Character, Scene, Shot, Take
from app.services import reference_bible, revisions


# ---------------------------------------------------------------------------
# Fixtures: two scenes, each with its own character and shots
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_scene_project(db_session, sample_project, sample_style):
    """A project with two independent scenes, so isolation is observable."""
    characters = []
    scenes = []
    shots = []
    for index in (0, 1):
        character = Character(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            name=f"Character {index}",
            appearance=f"appearance {index}",
        )
        db_session.add(character)
        db_session.flush()
        characters.append(character)

        scene = Scene(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            order=index,
            title=f"Scene {index}",
            summary=f"summary {index}",
            character_ids=[character.id],
        )
        db_session.add(scene)
        db_session.flush()
        scenes.append(scene)

        shot = Shot(
            id=str(uuid.uuid4()),
            scene_id=scene.id,
            order=1,
            subject=f"subject {index}",
            action=f"action {index}",
            image_prompt=f"prompt {index}",
            generation_mode="image",
        )
        db_session.add(shot)
        shots.append(shot)

    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    return {
        "project": sample_project,
        "characters": characters,
        "scenes": scenes,
        "shots": shots,
    }


def _generated(db_session, shot: Shot) -> Take:
    """Put a shot in the state it would be in after an approved generation."""
    revisions.mark_generated(db_session, shot)
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=shot.id,
        file_path=f"/tmp/{shot.id}.png",
        review_status="Approved",
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
    )
    db_session.add(take)
    shot.status = "Approved"
    db_session.commit()
    return take


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def test_a_fresh_shot_starts_at_revision_one_and_is_not_stale(two_scene_project):
    for shot in two_scene_project["shots"]:
        assert shot.prompt_revision == 1
        assert shot.content_sha256
        assert shot.prompt_sha256
        assert shot.is_stale is False


def test_refreshing_twice_changes_nothing(db_session, two_scene_project):
    changed = revisions.refresh_project(
        db_session, two_scene_project["project"].id
    )
    assert changed == []


# ---------------------------------------------------------------------------
# Selectivity
# ---------------------------------------------------------------------------

def test_editing_one_shot_advances_only_that_shot(db_session, two_scene_project):
    first, second = two_scene_project["shots"]
    before = second.prompt_revision

    first.action = "a completely different action"
    db_session.commit()
    changed = revisions.refresh_project(db_session, two_scene_project["project"].id)

    assert changed == [first.id]
    assert first.prompt_revision == 2
    assert second.prompt_revision == before


def test_editing_a_scene_advances_only_its_shots(db_session, two_scene_project):
    scenes = two_scene_project["scenes"]
    first, second = two_scene_project["shots"]

    scenes[0].summary = "a rewritten summary"
    db_session.commit()
    changed = revisions.refresh_project(db_session, two_scene_project["project"].id)

    assert changed == [first.id]
    assert second.prompt_revision == 1


def test_editing_a_character_advances_only_the_scenes_it_appears_in(
    db_session, two_scene_project
):
    characters = two_scene_project["characters"]
    first, second = two_scene_project["shots"]

    characters[1].clothing = "a new coat"
    db_session.commit()
    changed = revisions.refresh_project(db_session, two_scene_project["project"].id)

    assert changed == [second.id]
    assert first.prompt_revision == 1
    assert second.prompt_revision == 2


def test_editing_a_style_advances_every_shot(db_session, two_scene_project, sample_style):
    """A project-wide style is genuinely a dependency of every shot."""
    sample_style.visual_keywords = "muted, overcast"
    db_session.commit()
    changed = revisions.refresh_project(db_session, two_scene_project["project"].id)
    assert set(changed) == {s.id for s in two_scene_project["shots"]}


# ---------------------------------------------------------------------------
# Reference dependencies
# ---------------------------------------------------------------------------

def test_assigning_a_reference_advances_only_that_shot(
    db_session, two_scene_project, png_bytes
):
    project = two_scene_project["project"]
    first, second = two_scene_project["shots"]

    sheet = reference_bible.create_sheet(
        db_session, project_id=project.id, kind="character", name="Hero",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="hero.png", content_type="image/png",
    )
    first.reference_asset_ids = [image.id]
    db_session.commit()

    changed = revisions.refresh_project(db_session, project.id)
    assert changed == [first.id]
    assert first.reference_sha256s == [image.sha256]
    assert second.prompt_revision == 1


def test_editing_a_reference_sheet_advances_only_shots_that_use_it(
    db_session, two_scene_project, png_bytes
):
    project = two_scene_project["project"]
    first, second = two_scene_project["shots"]

    sheet = reference_bible.create_sheet(
        db_session, project_id=project.id, kind="character", name="Hero",
        canonical_description="Short hair.",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="hero.png", content_type="image/png",
    )
    first.reference_asset_ids = [image.id]
    db_session.commit()
    revisions.refresh_project(db_session, project.id)
    baseline = first.prompt_revision

    reference_bible.update_sheet(
        db_session, sheet, {"canonical_description": "Long hair."}
    )
    changed = revisions.refresh_project(db_session, project.id)

    assert changed == [first.id]
    assert first.prompt_revision == baseline + 1
    assert second.prompt_revision == 1


def test_replacing_a_reference_image_advances_the_using_shot(
    db_session, two_scene_project, png_bytes
):
    project = two_scene_project["project"]
    first, _second = two_scene_project["shots"]

    sheet = reference_bible.create_sheet(
        db_session, project_id=project.id, kind="prop", name="Lantern",
    )
    original = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 128),
        original_filename="a.png", content_type="image/png",
    )
    first.reference_asset_ids = [original.id]
    db_session.commit()
    revisions.refresh_project(db_session, project.id)
    baseline = first.prompt_revision

    replacement = reference_bible.store_image(
        db_session, sheet=sheet, data=png_bytes(128, 160),
        original_filename="b.png", content_type="image/png",
    )
    first.reference_asset_ids = [replacement.id]
    db_session.commit()

    changed = revisions.refresh_project(db_session, project.id)
    assert changed == [first.id]
    assert first.prompt_revision == baseline + 1


def test_reuploading_identical_reference_bytes_is_not_a_change(
    db_session, two_scene_project, png_bytes
):
    """The digest covers content, so re-uploading the same plate is a no-op."""
    project = two_scene_project["project"]
    first, _second = two_scene_project["shots"]
    data = png_bytes(128, 128)

    sheet = reference_bible.create_sheet(
        db_session, project_id=project.id, kind="prop", name="Lantern",
    )
    image = reference_bible.store_image(
        db_session, sheet=sheet, data=data,
        original_filename="a.png", content_type="image/png",
    )
    first.reference_asset_ids = [image.id]
    db_session.commit()
    revisions.refresh_project(db_session, project.id)
    baseline = first.prompt_revision

    reference_bible.store_image(
        db_session, sheet=sheet, data=data,
        original_filename="a-again.png", content_type="image/png",
    )
    assert revisions.refresh_project(db_session, project.id) == []
    assert first.prompt_revision == baseline


# ---------------------------------------------------------------------------
# Staleness against generated work
# ---------------------------------------------------------------------------

def test_a_change_after_generation_marks_only_that_shot_stale(
    db_session, two_scene_project
):
    first, second = two_scene_project["shots"]
    first_take = _generated(db_session, first)
    second_take = _generated(db_session, second)

    first.action = "a different action"
    db_session.commit()
    revisions.refresh_project(db_session, two_scene_project["project"].id)

    assert first.is_stale is True
    assert second.is_stale is False

    # Approved work is history, not garbage: both takes survive untouched.
    assert db_session.query(Take).count() == 2
    db_session.refresh(first_take)
    db_session.refresh(second_take)
    assert first_take.review_status == "Approved"
    assert second_take.review_status == "Approved"
    assert second.status == "Approved"


def test_a_change_before_any_generation_is_not_staleness(
    db_session, two_scene_project
):
    """Nothing has been produced yet, so there is nothing to be stale against."""
    first, _second = two_scene_project["shots"]
    first.action = "edited before generating"
    db_session.commit()
    revisions.refresh_project(db_session, two_scene_project["project"].id)
    assert first.prompt_revision == 2
    assert first.is_stale is False


def test_regenerating_clears_staleness(db_session, two_scene_project):
    first, _second = two_scene_project["shots"]
    _generated(db_session, first)
    first.action = "changed"
    db_session.commit()
    revisions.refresh_project(db_session, two_scene_project["project"].id)
    assert first.is_stale is True

    revisions.mark_generated(db_session, first)
    db_session.commit()
    assert first.is_stale is False
    assert first.generated_revision == first.prompt_revision


def test_reverting_a_change_still_counts_as_a_new_revision(
    db_session, two_scene_project
):
    """Revisions count edits, not distinct texts, so lineage stays monotonic."""
    first, _second = two_scene_project["shots"]
    original = first.action

    first.action = "temporary"
    db_session.commit()
    revisions.refresh_project(db_session, two_scene_project["project"].id)

    first.action = original
    db_session.commit()
    revisions.refresh_project(db_session, two_scene_project["project"].id)

    assert first.prompt_revision == 3


# ---------------------------------------------------------------------------
# Digest contents
# ---------------------------------------------------------------------------

def test_digest_exposes_the_compiled_prompt_it_hashed(db_session, two_scene_project):
    first = two_scene_project["shots"][0]
    digest = revisions.shot_digest(db_session, first)
    assert "subject 0" in digest.positive_prompt
    assert digest.prompt_sha256 and digest.content_sha256
    assert digest.reference_image_ids == []


def test_generation_mode_is_part_of_the_content_digest(
    db_session, two_scene_project
):
    first = two_scene_project["shots"][0]
    before = revisions.shot_digest(db_session, first).content_sha256
    first.generation_mode = "video"
    first.video_prompt = "a moving shot"
    db_session.commit()
    assert revisions.shot_digest(db_session, first).content_sha256 != before


def test_seed_policy_is_not_a_content_change(db_session, two_scene_project):
    """Re-rolling a seed is a new take, not a new revision."""
    first = two_scene_project["shots"][0]
    before = revisions.shot_digest(db_session, first).content_sha256
    first.seed_policy = "fixed"
    db_session.commit()
    assert revisions.shot_digest(db_session, first).content_sha256 == before
