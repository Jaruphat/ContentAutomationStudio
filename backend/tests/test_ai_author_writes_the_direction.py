"""What two produced episodes learned has to reach the shots the AI writes.

The storyboard task wrote `video_prompt` and nothing else about motion. Two
episodes established that this is not enough, and each lesson was paid for in
GPU time:

* **What happens leads; the camera qualifies.** A film whose shots asked for
  "slow gentle camera drift" came back as twenty-three held paintings, and the
  next cut - which named two things that move and then said "nothing else
  moves" - was 86% identical frames. The model takes a camera sentence as the
  whole brief. So the direction is two fields, and what moves is first.
* **The models render sound.** H3 reads a line beginning "Audio:" from the
  same prompt and produces ambience from it. Without one, every clip comes
  back with whatever the model invented, and a channel's sound bible never
  reaches a render.
* **Emphasis cards are a second caption track.** Three to six words, held over
  the shot; the accessibility track carries the full line separately.

A storyboard written by hand carries all three. A storyboard written by the
application did not, so an episode authored in the app would arrive undirected
and silent, and the person who authored it would have no way to know why.
"""


import pytest

from app.models import Shot
from app.services.ai import prompts, task_schemas
from app.services.ai.task_schemas import SHOT_PROPERTIES


DIRECTION_FIELDS = ("subject_motion", "camera_motion", "audio_direction")


# ---------------------------------------------------------------------------
# The contract the model is given
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", DIRECTION_FIELDS + ("emphasis_text",))
def test_the_shot_schema_asks_for_the_direction(field):
    assert field in SHOT_PROPERTIES, field
    assert SHOT_PROPERTIES[field]["description"].strip()


def test_the_schema_still_requires_every_property_it_declares():
    """The provider contract is strict-schema: a property that is not required
    is a property the model may silently omit."""
    schema = task_schemas.TASK_SCHEMAS["scene_decomposition"]
    shot = schema["properties"]["scenes"]["items"]["properties"]["shots"]["items"]
    assert set(shot["required"]) == set(shot["properties"])


def test_the_system_prompt_teaches_the_order_the_fields_are_sent_in():
    """A field the model fills in with a camera sentence is the failure this
    exists to prevent, so the rule is stated, not implied by a field name."""
    system = prompts.SCENE_DECOMPOSITION_SYSTEM.lower()

    assert "subject_motion" in system
    assert "camera_motion" in system
    assert "audio_direction" in system
    assert "emphasis_text" in system


# ---------------------------------------------------------------------------
# What reaches the database
# ---------------------------------------------------------------------------

def _scene(shot: dict) -> dict:
    return {
        "order": 0, "title": "The hall", "purpose": "Find the door",
        "summary": "A man walks down a hallway.", "time_of_day": "night",
        "emotional_beat": "unease", "planned_duration_sec": 4.0,
        "character_names": [], "location_name": "", "shots": [shot],
    }


def _shot(**overrides) -> dict:
    base = {
        "order": 0, "shot_type": "wide shot", "camera_angle": "eye level",
        "camera_movement": "static", "lens_framing": "35mm",
        "subject": "a man", "action": "walks down a hallway",
        "environment": "a narrow upstairs hallway at night",
        "dialogue": "There's a door at the end of the hall.",
        "planned_duration_sec": 4.0, "generation_mode": "image-to-video",
        "image_prompt": "A narrow upstairs hallway at night.",
        "video_prompt": "",
        "subject_motion": "The man walks three steps and stops.",
        "camera_motion": "Locked-off camera at the top of the stairs.",
        "audio_direction": "footsteps on worn carpet, a house settling",
        "emphasis_text": "A DOOR AT THE END.",
        "negative_prompt": "text, watermark",
    }
    base.update(overrides)
    return base


def _apply(db, project, scene: dict):
    from app.services.ai import tasks

    return tasks._apply_storyboard(db, project, [scene], True)


def test_the_direction_reaches_the_shot(db_session, sample_project):
    _apply(db_session, sample_project, _scene(_shot()))

    shot = db_session.query(Shot).order_by(Shot.created_at.desc()).first()
    assert shot.subject_motion.startswith("The man walks three steps")
    assert shot.camera_motion.startswith("Locked-off camera")
    assert shot.audio_direction == "footsteps on worn carpet, a house settling"
    assert shot.emphasis_text == "A DOOR AT THE END."


def test_a_still_is_not_given_motion_or_sound(db_session, sample_project):
    """The same rule `video_prompt` already follows. A still has no sound, and
    a sound sentence in an image prompt is one more thing to draw."""
    _apply(db_session, sample_project, _scene(_shot(
        generation_mode="image", video_prompt="", emphasis_text="",
    )))

    shot = db_session.query(Shot).order_by(Shot.created_at.desc()).first()
    assert shot.subject_motion == ""
    assert shot.camera_motion == ""
    assert shot.audio_direction == ""


def test_a_reply_without_the_direction_still_applies(
    db_session, sample_project,
):
    """A provider that predates these fields, or a reviewed draft saved before
    them, must not fail to apply - it just arrives undirected."""
    bare = _shot()
    for field in DIRECTION_FIELDS + ("emphasis_text",):
        bare.pop(field)

    summary, _warnings = _apply(db_session, sample_project, _scene(bare))

    assert summary["shots_created"] == 1
    shot = db_session.query(Shot).order_by(Shot.created_at.desc()).first()
    assert shot.subject_motion == ""
    assert shot.audio_direction == ""


# ---------------------------------------------------------------------------
# Warnings the author can act on
# ---------------------------------------------------------------------------

def test_a_shot_directed_only_by_its_camera_is_warned(
    db_session, sample_project,
):
    """The failure that produced two slideshows, caught while the storyboard is
    still free to change rather than after four hundred seconds a shot."""
    _summary, warnings = _apply(db_session, sample_project, _scene(_shot(
        subject_motion="", camera_motion="Slow gentle camera drift.",
    )))

    joined = " ".join(warnings).lower()
    assert "camera" in joined
    assert "shot 1" in joined


def test_an_emphasis_card_too_long_to_read_is_warned(
    db_session, sample_project,
):
    """Three to six words held over a vertical frame. A sentence there covers
    the picture and is gone before it is read."""
    _summary, warnings = _apply(db_session, sample_project, _scene(_shot(
        emphasis_text="He opened the door at the end of the upstairs hallway.",
    )))

    assert any("emphasis" in warning.lower() for warning in warnings)


def test_a_directed_shot_is_not_warned_about(db_session, sample_project):
    _summary, warnings = _apply(db_session, sample_project, _scene(_shot()))

    assert warnings == []


# ---------------------------------------------------------------------------
# The deterministic provider has to satisfy its own schema
# ---------------------------------------------------------------------------

def test_the_mock_provider_writes_the_direction_it_promises():
    """The mock is what every test without an API key runs against. A mock
    that omits a required property is a schema nobody is checking."""
    from app.services.ai.mock_provider import MockAIProvider  # noqa: F401

    required = set(SHOT_PROPERTIES)
    import inspect
    source = inspect.getsource(MockAIProvider)
    for field in required:
        assert f'"{field}"' in source, field
