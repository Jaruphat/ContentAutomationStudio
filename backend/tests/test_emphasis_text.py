"""Two caption tracks, because they are doing two different jobs.

A subtitle is an accessibility track: everything that is said, timed to when it
is said, readable by someone who cannot hear it. Emphasis text is a design
element: three to six words, punched on screen for a beat, doing the work a
title card does. Rendering them with one style makes the subtitle shout and the
emphasis look like a caption.

The distinction has consequences beyond styling:

* Emphasis is **burned in only**. A soft subtitle file is a transcript, and a
  transcript that contains "EVERY NIGHT / AT 3:17 AM" alongside the sentence it
  was drawn from is a transcript with the same line twice.
* Emphasis is **short by construction**. A pasted paragraph in this field is
  not a long emphasis, it is a mistake, and it covers the frame.
* The break is written by hand. "/" is where the line turns, because where a
  two-line card breaks is a design decision, not a wrapping outcome.
"""

import uuid

import pytest

from app.models import Shot, Take, TimelineItem
from app.services import revisions, subtitle_service


def _shot(db, scene, order, dialogue="", emphasis="", duration=4.0):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="image-to-video", video_prompt="x",
        planned_duration_sec=duration, dialogue=dialogue,
        emphasis_text=emphasis,
    )
    db.add(shot)
    db.commit()
    return shot


def _place(db, project_id, shot, order, clip=8.0):
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="clip.mp4",
        review_status="Approved", width=576, height=1024, duration_sec=clip,
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
    )
    db.add(take)
    db.flush()
    duration = min(shot.planned_duration_sec, clip)
    db.add(TimelineItem(
        id=str(uuid.uuid4()), project_id=project_id, shot_id=shot.id,
        take_id=take.id, order=order,
        in_point_sec=order * duration, out_point_sec=(order + 1) * duration,
        duration_sec=duration,
        take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()
    return take


# ---------------------------------------------------------------------------
# The cues
# ---------------------------------------------------------------------------

def test_emphasis_cues_come_from_the_emphasis_field_not_the_dialogue(
    db_session, sample_project, sample_scene,
):
    shot = _shot(
        db_session, sample_scene, 1,
        dialogue="Every night at exactly 3:17, a train arrives.",
        emphasis="EVERY NIGHT / AT 3:17 AM",
    )
    _place(db_session, sample_project.id, shot, 0)

    cues = subtitle_service.build_emphasis_cues(db_session, sample_project.id)

    assert len(cues) == 1
    assert "3:17 AM" in cues[0]["text"]
    assert "a train arrives" not in cues[0]["text"]


def test_a_shot_with_no_emphasis_contributes_nothing(
    db_session, sample_project, sample_scene,
):
    """Most shots have none. An empty card held on screen is worse than no
    card, because the viewer waits for it to say something."""
    shot = _shot(db_session, sample_scene, 1, dialogue="Spoken but not punched.")
    _place(db_session, sample_project.id, shot, 0)

    assert subtitle_service.build_emphasis_cues(db_session, sample_project.id) == []


def test_the_slash_is_where_the_line_turns(
    db_session, sample_project, sample_scene,
):
    """Where a two-line card breaks is a design decision, not a wrapping
    outcome, so it is written by hand and honoured."""
    shot = _shot(db_session, sample_scene, 1, emphasis="EVERY NIGHT / AT 3:17 AM")
    _place(db_session, sample_project.id, shot, 0)

    cues = subtitle_service.build_emphasis_cues(db_session, sample_project.id)

    assert cues[0]["text"] == "EVERY NIGHT\nAT 3:17 AM"


def test_an_emphasis_card_is_held_for_a_beat_not_the_whole_shot(
    db_session, sample_project, sample_scene,
):
    """It is a punch, not a lower third. Held for four seconds it stops being
    emphasis and becomes furniture."""
    shot = _shot(db_session, sample_scene, 1, emphasis="THE TRAIN RETURNS.",
                 duration=4.0)
    _place(db_session, sample_project.id, shot, 0)

    cue = subtitle_service.build_emphasis_cues(db_session, sample_project.id)[0]

    assert cue["start_sec"] == 0.0
    assert cue["end_sec"] == pytest.approx(subtitle_service.EMPHASIS_SECONDS)


def test_a_card_never_outlives_the_shot_it_belongs_to(
    db_session, sample_project, sample_scene,
):
    """A two-second shot cannot hold a card for longer than two seconds
    without it bleeding onto the next one."""
    shot = _shot(db_session, sample_scene, 1, emphasis="3:17 AM", duration=1.0)
    _place(db_session, sample_project.id, shot, 0)

    cue = subtitle_service.build_emphasis_cues(db_session, sample_project.id)[0]

    assert cue["end_sec"] == pytest.approx(1.0)


def test_cards_follow_the_cut_not_the_source_clips(
    db_session, sample_project, sample_scene,
):
    """The same trap the dialogue track has: timing from clip lengths while
    the cut uses planned lengths puts every later card in the wrong place."""
    first = _shot(db_session, sample_scene, 1, emphasis="ONE", duration=4.0)
    second = _shot(db_session, sample_scene, 2, emphasis="TWO", duration=4.0)
    _place(db_session, sample_project.id, first, 0)
    _place(db_session, sample_project.id, second, 1)

    cues = subtitle_service.build_emphasis_cues(db_session, sample_project.id)

    assert cues[0]["start_sec"] == 0.0
    assert cues[1]["start_sec"] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def test_a_paragraph_in_the_emphasis_field_is_refused(
    db_session, sample_project, sample_scene,
):
    """Not a long emphasis - a mistake, and one that covers the frame."""
    shot = _shot(
        db_session, sample_scene, 1,
        emphasis=(
            "Every night at exactly 3:17 a train arrives at this abandoned "
            "station and nobody has ever stepped off it until last night"
        ),
    )
    _place(db_session, sample_project.id, shot, 0)

    with pytest.raises(ValueError) as exc:
        subtitle_service.build_emphasis_cues(db_session, sample_project.id)
    assert "words" in str(exc.value).lower()


def test_more_than_two_lines_is_refused(db_session, sample_project, sample_scene):
    shot = _shot(db_session, sample_scene, 1, emphasis="ONE / TWO / THREE")
    _place(db_session, sample_project.id, shot, 0)

    with pytest.raises(ValueError) as exc:
        subtitle_service.build_emphasis_cues(db_session, sample_project.id)
    assert "lines" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_both_tracks_are_burned_in_one_pass_with_two_styles(db_session):
    """One file, two styles. Two burn-in passes would re-encode the picture
    twice for no reason, and two files cannot be layered by the same filter."""
    settings = subtitle_service.SubtitleSettings(mode="burn_in")
    ass = subtitle_service.render_ass(
        [{"index": 1, "start_sec": 0.0, "end_sec": 4.0, "text": "Spoken line."}],
        settings, 576, 1024,
        emphasis_cues=[
            {"index": 1, "start_sec": 0.0, "end_sec": 1.8,
             "text": "EVERY NIGHT\nAT 3:17 AM"},
        ],
    )

    assert "Style: Default," in ass
    assert "Style: Emphasis," in ass
    assert ",Emphasis,," in ass
    assert "EVERY NIGHT\\NAT 3:17 AM" in ass


def test_the_emphasis_style_is_not_the_subtitle_style(db_session):
    """If it renders identically there was no point separating them."""
    settings = subtitle_service.SubtitleSettings(mode="burn_in")
    ass = subtitle_service.render_ass(
        [], settings, 576, 1024,
        emphasis_cues=[{"index": 1, "start_sec": 0.0, "end_sec": 1.8,
                        "text": "IT WAS HIM."}],
    )

    default = next(line for line in ass.splitlines() if line.startswith("Style: Default,"))
    emphasis = next(line for line in ass.splitlines() if line.startswith("Style: Emphasis,"))
    assert default.split(",")[2:] != emphasis.split(",")[2:]


def test_emphasis_stays_out_of_the_soft_subtitle_file(db_session):
    """A transcript containing both the sentence and the three words punched
    out of it is a transcript with the same line twice."""
    srt = subtitle_service.render_srt([
        {"index": 1, "start_sec": 0.0, "end_sec": 4.0,
         "text": "Every night at exactly 3:17, a train arrives."},
    ])

    assert "3:17" in srt
    assert "EVERY NIGHT" not in srt


def test_rendering_without_emphasis_is_unchanged(db_session):
    """Every project written before this must burn in exactly as it did."""
    settings = subtitle_service.SubtitleSettings(mode="burn_in")
    cues = [{"index": 1, "start_sec": 0.0, "end_sec": 4.0, "text": "A line."}]

    assert subtitle_service.render_ass(cues, settings, 576, 1024) == (
        subtitle_service.render_ass(cues, settings, 576, 1024, emphasis_cues=[])
    )
