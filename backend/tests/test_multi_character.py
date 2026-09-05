"""Two characters in one shot.

A scene with a hare and a tortoise in it needs both of them conditioned, and
the app has always let a shot bind more than one character set. What it did
with them was the problem: the resolver emitted every canonical view of every
set in set order, so a two-slot workflow given a hare and a tortoise received
the hare's full-body and the hare's front view, and drew two hares.

The order has to be by rank across the sets rather than by set: everybody's
primary view first, then everybody's second. Truncating that to the workflow's
capacity then does the obvious right thing - two slots and two characters is
one view each.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Character, Project, Scene, Shot
from app.services import character_sets, shot_conditioning


def _shot(db, scene, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=kwargs.pop("order", 1),
        image_prompt="a hare and a tortoise", status="Draft", **kwargs,
    )
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


def _approved_set(db, project_id, character_id, png_bytes, *, name, slots, seed=1):
    character_set = character_sets.create_set(
        db, project_id=project_id, name=name, character_id=character_id,
        appearance=f"{name} appearance",
    )
    version = character_sets.create_version(db, character_set, slots=slots)
    for index, view in enumerate(character_sets.list_views(db, version)):
        character_sets.attach_view_image(
            db, view, data=png_bytes(64 + seed * 8 + index, 64),
            content_type="image/png", original_filename=f"{name}-{view.slot}.png",
            provenance={"provider_id": "mock", "seed": seed + index},
        )
    character_sets.approve_version(db, version)
    return character_set


@pytest.fixture()
def hare_and_tortoise(db_session, sample_project, sample_character, png_bytes):
    hare = _approved_set(
        db_session, sample_project.id, sample_character.id, png_bytes,
        name="Hare", slots=["front", "full_body"], seed=1,
    )
    tortoise = _approved_set(
        db_session, sample_project.id, None, png_bytes,
        name="Tortoise", slots=["front", "full_body"], seed=9,
    )
    return hare, tortoise


def _sets_of(entries):
    return [entry.detail.get("character_set_name") for entry in entries]


def test_every_character_gets_its_primary_view_before_anyone_gets_a_second(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    hare_and_tortoise,
):
    """Rank across the sets, not set after set.

    Ordering by set means the first character fills every slot a workflow has
    and the second is never sent at all.
    """
    hare, tortoise = hare_and_tortoise
    shot = _shot(db_session, sample_scene, character_set_ids=[hare.id, tortoise.id])

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert resolved.problems == []
    assert _sets_of(resolved.images[:2]) == ["Hare", "Tortoise"]
    # And the second view of each follows, still paired.
    assert _sets_of(resolved.images[2:4]) == ["Hare", "Tortoise"]


def test_the_primary_view_is_the_one_that_shows_the_whole_character(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    hare_and_tortoise,
):
    """A full body says more about a tortoise than a portrait crop does."""
    hare, tortoise = hare_and_tortoise
    shot = _shot(db_session, sample_scene, character_set_ids=[hare.id, tortoise.id])

    resolved = shot_conditioning.resolve(db_session, sample_project.id, shot)

    assert [entry.detail.get("view_slot") for entry in resolved.images[:2]] == [
        "full_body", "full_body",
    ]


def test_two_characters_on_a_two_input_workflow_send_one_view_each(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    hare_and_tortoise,
):
    """The whole point: a hare and a tortoise, not two hares."""
    hare, tortoise = hare_and_tortoise
    shot = _shot(db_session, sample_scene, character_set_ids=[hare.id, tortoise.id])

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=2,
    )

    assert selected.problems == []
    assert _sets_of(selected.submitted_images) == ["Hare", "Tortoise"]


def test_binding_order_decides_which_character_leads(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    hare_and_tortoise,
):
    """Slot one is not arbitrary - some routes weight the first reference more,
    so the order the user bound the sets in is the order they are sent."""
    hare, tortoise = hare_and_tortoise
    shot = _shot(db_session, sample_scene, character_set_ids=[tortoise.id, hare.id])

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=2,
    )

    assert _sets_of(selected.submitted_images) == ["Tortoise", "Hare"]


def test_two_characters_still_cannot_fit_a_one_input_workflow(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    hare_and_tortoise,
):
    """One image cannot carry two identities, and guessing which to drop would
    silently write one of the characters out of the shot."""
    hare, tortoise = hare_and_tortoise
    shot = _shot(db_session, sample_scene, character_set_ids=[hare.id, tortoise.id])

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=1,
    )

    assert selected.problems
    assert selected.submitted_images == []


def test_three_characters_need_three_slots(
    db_session: Session, sample_project: Project, sample_scene: Scene,
    sample_character: Character, hare_and_tortoise, png_bytes,
):
    hare, tortoise = hare_and_tortoise
    fox = _approved_set(
        db_session, sample_project.id, None, png_bytes,
        name="Fox", slots=["full_body"], seed=17,
    )
    shot = _shot(
        db_session, sample_scene,
        character_set_ids=[hare.id, tortoise.id, fox.id],
    )

    selected = shot_conditioning.select_for_submission(
        shot_conditioning.resolve(db_session, sample_project.id, shot), max_images=3,
    )

    assert selected.problems == []
    assert _sets_of(selected.submitted_images) == ["Hare", "Tortoise", "Fox"]
