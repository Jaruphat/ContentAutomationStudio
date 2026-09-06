"""What a shot should sound like, told to the model that renders it.

The H3 video models generate sound along with the picture, and they take the
direction for it from the same prompt - a line beginning "Audio:" naming what
is heard. Nothing in this application said that, so every clip came back with
whatever ambience the model invented, and the blueprint's Sound Bible - wind, a
clock tick, rail vibration, a pneumatic door, footsteps, paper rustle - lived
in a document that never reached a render.

It is a third field rather than a sentence appended to the motion direction,
for the same reason the motion direction is two fields and not one: these are
different briefs and the model weighs them differently. What happens in the
frame leads because that is what is being invented; the camera qualifies it;
the sound comes last, because it describes the same events from another sense
and a model given it first will narrate rather than animate.

The tests that matter here are the boring ones. A field that reaches the
preview and not the submitted job is worse than no field, because nine clips
render silently wrong and nothing reports it - which is exactly what happened
to the motion fields once already.
"""

import uuid

import pytest
from sqlalchemy import text

from app.models import Shot
from app.services import motion_direction, prompt_context


# ---------------------------------------------------------------------------
# Composing: sound comes last
# ---------------------------------------------------------------------------

def test_the_sound_is_named_and_comes_after_what_happens():
    composed = motion_direction.compose(
        subject_motion="The carriage door slides open.",
        camera_motion="Locked-off camera.",
        audio_direction="a pneumatic hiss, low engine idle, light wind",
    )

    assert composed.index("carriage door") < composed.index("Audio:")
    assert composed.index("Locked-off") < composed.index("Audio:")
    assert composed.endswith("Audio: a pneumatic hiss, low engine idle, light wind.")


def test_a_direction_that_already_ends_in_a_full_stop_does_not_gain_a_second():
    composed = motion_direction.compose(
        subject_motion="Rain falls.", camera_motion="",
        audio_direction="Rain on a tin roof.",
    )

    assert composed == "Rain falls. Audio: Rain on a tin roof."


def test_sound_alone_is_still_a_direction():
    """A shot can be held still on purpose and still be told what it sounds
    like. The motion warning covers the stillness; this must not swallow it."""
    assert motion_direction.compose(
        subject_motion="", camera_motion="", audio_direction="Distant traffic.",
    ) == "Audio: Distant traffic."


def test_no_sound_composes_exactly_as_it_did_before():
    """Every shot written before this field existed has to compile to the same
    prompt it compiled to yesterday, or an old project regenerates into a
    different film."""
    assert motion_direction.compose(
        subject_motion="The train rolls in.",
        camera_motion="Long lens, subtle vibration.",
    ) == "The train rolls in. Long lens, subtle vibration."
    assert motion_direction.compose(
        subject_motion="The train rolls in.",
        camera_motion="Long lens, subtle vibration.",
        audio_direction="",
    ) == "The train rolls in. Long lens, subtle vibration."


# ---------------------------------------------------------------------------
# Reaching the prompt a generation actually submits
# ---------------------------------------------------------------------------

def test_the_shot_hands_its_sound_direction_to_the_compiler(
    db_session, sample_scene,
):
    """`shot_input` is the one description of a shot the compiler is given.
    A field the shot stores and this function drops is a field that exists
    everywhere except in the render."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video",
        subject_motion="The door swings open.",
        audio_direction="a pneumatic hiss and light wind",
    )
    db_session.add(shot)
    db_session.commit()

    assert prompt_context.shot_input(shot)["audio_direction"] == (
        "a pneumatic hiss and light wind"
    )


def test_the_compiled_video_prompt_carries_the_sound(db_session, sample_scene):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video",
        subject_motion="The door swings open.",
        camera_motion="Locked-off camera.",
        audio_direction="a pneumatic hiss and light wind",
    )
    db_session.add(shot)
    db_session.commit()

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "Audio: a pneumatic hiss and light wind." in compiled.positive_prompt


def test_an_image_shot_is_not_told_what_it_sounds_like(db_session, sample_scene):
    """A still has no sound, and a sound sentence in an image prompt is one
    more thing for the model to draw."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image", image_prompt="An empty platform at night.",
        audio_direction="wind across an empty station",
    )
    db_session.add(shot)
    db_session.commit()

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "Audio:" not in compiled.positive_prompt


# ---------------------------------------------------------------------------
# The API boundary
# ---------------------------------------------------------------------------

def _video_shot(client):
    project = client.post("/api/projects", json={"title": "Sound"}).json()
    pid = project["id"]
    scene = client.post(f"/api/projects/{pid}/scenes", json={"title": "S"}).json()
    path = f"/api/projects/{pid}/scenes/{scene['id']}/shots"
    shot = client.post(path, json={
        "generation_mode": "image-to-video",
        "subject_motion": "The door swings open.",
        "audio_direction": "a pneumatic hiss and light wind",
    })
    assert shot.status_code == 201, shot.text
    return pid, path, shot.json()


def test_a_sound_direction_round_trips_through_the_api(client):
    pid, path, shot = _video_shot(client)
    assert shot["audio_direction"] == "a pneumatic hiss and light wind"

    changed = client.put(f"{path}/{shot['id']}", json={
        "audio_direction": "footsteps on wet concrete, distant traffic",
    })

    assert changed.status_code == 200, changed.text
    assert changed.json()["audio_direction"] == (
        "footsteps on wet concrete, distant traffic"
    )


def test_changing_the_sound_direction_changes_what_would_be_generated(client):
    """Unlike a caption, this reaches the model, so a clip generated before the
    change is not a clip of the shot as it now stands."""
    pid, path, shot = _video_shot(client)

    changed = client.put(f"{path}/{shot['id']}", json={
        "audio_direction": "a clock ticking in an empty room",
    }).json()

    assert changed["content_sha256"] != shot["content_sha256"]
    assert changed["prompt_revision"] > shot["prompt_revision"]


def test_a_misspelled_sound_field_is_refused_rather_than_dropped(client):
    pid, path, shot = _video_shot(client)

    response = client.put(f"{path}/{shot['id']}", json={
        "audio_directon": "a pneumatic hiss",
    })

    assert response.status_code == 422
    assert "audio_directon" in response.text


def test_a_shot_older_than_the_column_still_reads_and_edits(
    client, db_session, sample_project, sample_scene,
):
    """ADD COLUMN can only be NULL in SQLite, so every shot made before this
    field carries None. A response model declaring `str = ""` does not coerce
    that - it fails validation and a plain GET becomes a 500."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video", video_prompt="x",
    )
    db_session.add(shot)
    db_session.commit()
    db_session.execute(
        text("UPDATE shots SET audio_direction = NULL WHERE id = :id"),
        {"id": shot.id},
    )
    db_session.commit()

    listed = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots"
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["audio_direction"] == ""


def test_a_null_sound_direction_compiles_without_a_sound_sentence(
    db_session, sample_scene,
):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video", subject_motion="The door opens.",
    )
    db_session.add(shot)
    db_session.commit()
    db_session.execute(
        text("UPDATE shots SET audio_direction = NULL WHERE id = :id"),
        {"id": shot.id},
    )
    db_session.commit()
    db_session.expire_all()
    shot = db_session.query(Shot).filter(Shot.id == shot.id).one()

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "Audio:" not in compiled.positive_prompt


@pytest.mark.parametrize("value", ["Audio: wind", "audio: wind", "AUDIO: wind"])
def test_a_direction_that_already_says_audio_is_not_labelled_twice(value):
    """The label is this application's, and a writer who types it themselves
    should not get "Audio: Audio: wind" in a paid render."""
    composed = motion_direction.compose(
        subject_motion="The door opens.", camera_motion="",
        audio_direction=value,
    )

    assert composed.lower().count("audio:") == 1
