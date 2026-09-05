"""A line too long for its shot, said before the render rather than after.

Every cut of this episode has come back with the same warning: four or five
narration lines run past the shot they belong to. It arrives at the end, after
forty minutes of generation and a render, and it is not a fault in the voice -
it is a script and a shot plan that disagree. The blueprint writes seven
sentences for thirty-two seconds, which is about 150 words per minute and
entirely reasonable; distributed across shots of 4, 2 and 3 seconds, several of
them do not fit the shot they were assigned to.

That is knowable the moment the timeline is built. It needs no audio, no
provider and no money - only the words, the seconds, and a rate.

The estimate is deliberately a range rather than a number. Speaking rate is not
a constant, and a check that fires on a tenth of a second would be ignored
within a day; one that fires when a line cannot fit at any plausible rate is
worth reading.
"""

import uuid

import pytest

from app.models import Shot, Take, TimelineItem
from app.services import dialogue_fit, revisions


def _shot(db, scene, order, dialogue, duration):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="image-to-video", video_prompt="x",
        planned_duration_sec=duration, dialogue=dialogue,
    )
    db.add(shot)
    db.commit()
    return shot


def _place(db, project_id, shot, order, duration):
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="clip.mp4",
        review_status="Approved", width=64, height=64, duration_sec=duration,
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
    )
    db.add(take)
    db.flush()
    db.add(TimelineItem(
        id=str(uuid.uuid4()), project_id=project_id, shot_id=shot.id,
        take_id=take.id, order=order,
        in_point_sec=order * duration, out_point_sec=(order + 1) * duration,
        duration_sec=duration,
        take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------

def test_a_line_is_measured_in_words_at_a_speaking_rate():
    """Words, not characters. "antidisestablishmentarianism" is one word and
    a second and a half; twenty-eight characters of "I do not know" is four
    words and under a second."""
    seconds = dialogue_fit.speaking_seconds("Every night at exactly three seventeen")

    assert 1.5 < seconds < 4.0


def test_an_empty_line_takes_no_time():
    assert dialogue_fit.speaking_seconds("   ") == 0.0


def test_the_rate_is_the_one_the_voice_bible_asks_for():
    """Named so the check and the direction given to the narrator cannot
    drift apart."""
    assert 130 <= dialogue_fit.WORDS_PER_MINUTE <= 170


# ---------------------------------------------------------------------------
# Checking a cut
# ---------------------------------------------------------------------------

def test_a_line_that_cannot_fit_its_shot_is_reported(
    db_session, sample_project, sample_scene,
):
    shot = _shot(
        db_session, sample_scene, 1,
        "Every night at exactly 3:17, a train arrives at this abandoned station.",
        duration=2.0,
    )
    _place(db_session, sample_project.id, shot, 0, 2.0)

    problems = dialogue_fit.review(db_session, sample_project.id)

    assert len(problems) == 1
    assert problems[0]["shot_id"] == shot.id
    assert problems[0]["needs_sec"] > problems[0]["has_sec"]


def test_a_line_that_fits_comfortably_is_not_reported(
    db_session, sample_project, sample_scene,
):
    shot = _shot(db_session, sample_scene, 1, "Until last night.", duration=4.0)
    _place(db_session, sample_project.id, shot, 0, 4.0)

    assert dialogue_fit.review(db_session, sample_project.id) == []


def test_a_line_that_only_just_fits_is_left_alone(
    db_session, sample_project, sample_scene,
):
    """Speaking rate is not a constant. A check that fires on a tenth of a
    second is ignored within a day."""
    words = "one two three four five six seven eight"
    exact = dialogue_fit.speaking_seconds(words)
    shot = _shot(db_session, sample_scene, 1, words, duration=exact + 0.05)
    _place(db_session, sample_project.id, shot, 0, exact + 0.05)

    assert dialogue_fit.review(db_session, sample_project.id) == []


def test_the_report_says_how_much_longer_the_shot_needs_to_be(
    db_session, sample_project, sample_scene,
):
    """"Too long" leaves the fix to guesswork; "needs 6.2s, has 4.0s" is an
    edit somebody can make."""
    shot = _shot(
        db_session, sample_scene, 1,
        "Every night at exactly 3:17, a train arrives at this abandoned station.",
        duration=4.0,
    )
    _place(db_session, sample_project.id, shot, 0, 4.0)

    problem = dialogue_fit.review(db_session, sample_project.id)[0]

    assert problem["shortfall_sec"] == pytest.approx(
        problem["needs_sec"] - problem["has_sec"], abs=0.01
    )
    assert "seconds" in problem["message"]
    assert str(round(problem["needs_sec"], 1)) in problem["message"]


def test_a_shot_with_no_dialogue_is_never_reported(
    db_session, sample_project, sample_scene,
):
    shot = _shot(db_session, sample_scene, 1, "", duration=1.0)
    _place(db_session, sample_project.id, shot, 0, 1.0)

    assert dialogue_fit.review(db_session, sample_project.id) == []


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def test_preflight_warns_before_anything_is_generated(
    client, db_session, sample_project, sample_scene,
):
    """Forty minutes of generation and a render is too late to learn that the
    script and the shot plan disagree - and this needs no audio, no provider
    and no money to know."""
    shot = _shot(
        db_session, sample_scene, 1,
        "Every night at exactly 3:17, a train arrives at this abandoned station.",
        duration=2.0,
    )
    shot.status = "Ready"
    db_session.commit()
    _place(db_session, sample_project.id, shot, 0, 2.0)

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    assert any("narration" in w.lower() for w in body["warnings"]), body["warnings"]


def test_the_warning_never_blocks_a_run(
    client, db_session, sample_project, sample_scene,
):
    """A line that overruns is left in step by the renderer and reported; it
    is a thing to fix, not a reason to refuse a render somebody asked for."""
    shot = _shot(
        db_session, sample_scene, 1,
        "Every night at exactly 3:17, a train arrives at this abandoned station.",
        duration=2.0,
    )
    shot.status = "Ready"
    db_session.commit()
    _place(db_session, sample_project.id, shot, 0, 2.0)

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    for entry in body["issues"]:
        assert not any("narration" in issue.lower() for issue in entry["issues"])
