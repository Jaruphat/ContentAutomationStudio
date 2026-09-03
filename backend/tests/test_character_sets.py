"""
Character Set Generator - versioned identity sheets and canonical approval.

A character set is the project's answer to "what does this person look like?".
It holds the identity spec once and generates a *version* of canonical view
images from it. Versions accumulate; exactly one may be approved as canonical,
and that approved version is what every downstream generation is conditioned
on.

The properties asserted here are the ones the rest of the feature stands on:

* a version is immutable history - approving a new one never deletes an old,
* exactly one version is canonical at a time, and
* resolving "the canonical identity references" returns the approved version's
  images, in view order, or nothing at all when no version is approved.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project
from app.services import character_sets


@pytest.fixture()
def character_set(
    db_session: Session, sample_project: Project, sample_character: Character
):
    return character_sets.create_set(
        db_session,
        project_id=sample_project.id,
        name="Mara",
        character_id=sample_character.id,
        appearance="Tall, close-cropped silver hair, weathered face.",
        proportions="Athletic, 8-head heroic proportions.",
        wardrobe="Charcoal field jacket, oxblood scarf.",
        palette="charcoal, oxblood, bone",
    )


def test_create_set_provisions_a_backing_reference_sheet(
    db_session: Session, sample_project: Project, character_set
):
    """The set owns a reference sheet, so generated views are real references.

    Reusing the Visual Reference Bible storage is what lets a canonical view be
    fed to a provider through the same validated, ownership-checked path as a
    hand-uploaded plate.
    """
    assert character_set.project_id == sample_project.id
    assert character_set.reference_sheet_id
    sheet = character_sets.backing_sheet(db_session, character_set)
    assert sheet is not None
    assert sheet.kind == "character"
    assert sheet.project_id == sample_project.id


def test_new_set_has_no_canonical_version(db_session: Session, character_set):
    assert character_set.approved_version_id is None
    images = character_sets.resolve_canonical_images(
        db_session, character_set.project_id, [character_set.id]
    )
    assert images == []


def test_draft_version_creates_one_view_per_requested_slot(
    db_session: Session, character_set
):
    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side", "back", "full_body"],
    )
    assert version.version == 1
    assert version.status == character_sets.STATUS_DRAFT
    slots = [view.slot for view in character_sets.list_views(db_session, version)]
    assert slots == ["front", "side", "back", "full_body"]


def test_version_numbers_increment_per_set(db_session: Session, character_set):
    first = character_sets.create_version(db_session, character_set, slots=["front"])
    second = character_sets.create_version(db_session, character_set, slots=["front"])
    assert [first.version, second.version] == [1, 2]


def test_unknown_slot_is_refused(db_session: Session, character_set):
    with pytest.raises(character_sets.CharacterSetError) as exc:
        character_sets.create_version(db_session, character_set, slots=["moodboard"])
    assert exc.value.code == "invalid_slot"


def test_a_version_needs_at_least_one_slot(db_session: Session, character_set):
    with pytest.raises(character_sets.CharacterSetError) as exc:
        character_sets.create_version(db_session, character_set, slots=[])
    assert exc.value.code == "no_slots"


def test_approval_requires_every_view_to_have_an_image(
    db_session: Session, character_set
):
    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side"],
    )
    with pytest.raises(character_sets.CharacterSetError) as exc:
        character_sets.approve_version(db_session, version)
    assert exc.value.code == "views_incomplete"


def test_approving_a_version_makes_its_images_canonical(
    db_session: Session, character_set, png_bytes
):
    version = character_sets.create_version(
        db_session, character_set, slots=["front", "side"],
    )
    for index, view in enumerate(character_sets.list_views(db_session, version)):
        character_sets.attach_view_image(
            db_session, view, data=png_bytes(64 + index, 64),
            content_type="image/png", original_filename=view.slot + ".png",
            provenance={"provider_id": "mock", "model": "deterministic"},
        )

    approved = character_sets.approve_version(db_session, version)
    assert approved.status == character_sets.STATUS_APPROVED
    assert approved.approved_at is not None

    db_session.refresh(character_set)
    assert character_set.approved_version_id == version.id

    images = character_sets.resolve_canonical_images(
        db_session, character_set.project_id, [character_set.id]
    )
    assert [image.sha256 for image in images] == [
        view.image.sha256
        for view in character_sets.list_views(db_session, version)
    ]


def test_approving_a_second_version_supersedes_the_first_without_deleting_it(
    db_session: Session, character_set, png_bytes
):
    """Version history is preserved; only the canonical pointer moves."""
    first = _approved_version(db_session, character_set, png_bytes, ["front"], seed=1)
    second = _approved_version(db_session, character_set, png_bytes, ["front"], seed=2)

    db_session.refresh(first)
    db_session.refresh(character_set)
    assert first.status == character_sets.STATUS_SUPERSEDED
    assert second.status == character_sets.STATUS_APPROVED
    assert character_set.approved_version_id == second.id

    history = character_sets.list_versions(db_session, character_set)
    assert [v.version for v in history] == [1, 2]
    # The superseded version keeps its images: it is history, not a draft.
    assert all(
        view.image is not None
        for view in character_sets.list_views(db_session, first)
    )


def test_canonical_digest_changes_when_the_approved_version_changes(
    db_session: Session, character_set, png_bytes
):
    """One digest answers "would a generation from this set differ now?"."""
    _approved_version(db_session, character_set, png_bytes, ["front"], seed=1)
    db_session.refresh(character_set)
    before = character_sets.canonical_digest(db_session, character_set)

    _approved_version(db_session, character_set, png_bytes, ["front"], seed=2)
    db_session.refresh(character_set)
    after = character_sets.canonical_digest(db_session, character_set)

    assert before and after and before != after


def test_resolve_canonical_images_ignores_sets_from_another_project(
    db_session: Session, character_set, png_bytes
):
    _approved_version(db_session, character_set, png_bytes, ["front"], seed=1)
    other = Project(id=str(uuid.uuid4()), title="Other")
    db_session.add(other)
    db_session.commit()

    assert character_sets.resolve_canonical_images(
        db_session, other.id, [character_set.id]
    ) == []


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _approved_version(db_session, character_set, png_bytes, slots, *, seed: int):
    version = character_sets.create_version(db_session, character_set, slots=slots)
    for index, view in enumerate(character_sets.list_views(db_session, version)):
        character_sets.attach_view_image(
            db_session, view,
            # Distinct bytes per seed so the canonical digest really moves.
            data=png_bytes(64 + seed, 64 + index),
            content_type="image/png",
            original_filename=view.slot + ".png",
            provenance={"provider_id": "mock", "seed": seed},
        )
    return character_sets.approve_version(db_session, version)
