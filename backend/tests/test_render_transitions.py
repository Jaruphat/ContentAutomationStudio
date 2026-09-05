"""Dissolves, and the tail before the loop.

`transition_in` and `transition_out` have been on the timeline row since the
first build and the renderer has never read either of them. Every film this
application has made is hard cuts, whatever the row said - a field that exists,
is editable, is exported in the manifest, and does nothing.

Honouring them is not free. The concat demuxer stream-copies the segments,
which is why assembly is fast; a dissolve is a filter across the boundary and
cannot be stream-copied. So the fast path stays exactly as it was whenever
every transition is a cut, and the whole programme is re-encoded through an
xfade chain only when a dissolve is actually asked for. That cost is stated in
the result rather than paid silently.

Two things the tests hold the implementation to:

* **A dissolve shortens the film.** Two four-second shots with a half-second
  dissolve run 7.5 seconds, not 8. Getting this wrong is invisible in a
  thumbnail and puts every later subtitle out of step.
* **A dissolve longer than the shots it joins is refused.** Overlapping past
  a neighbour's start does not blend two shots, it eats a third.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Shot, Take, TimelineItem
from app.services import render_service, revisions

ffmpeg_required = pytest.mark.skipif(
    render_service.ffmpeg_path() is None,
    reason="FFmpeg is not installed on this machine",
)
ffprobe_required = pytest.mark.skipif(
    render_service.ffprobe_path() is None,
    reason="ffprobe is not installed on this machine",
)


def _shot(db, scene, order, duration):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="image-to-video", video_prompt="x",
        planned_duration_sec=duration,
    )
    db.add(shot)
    db.commit()
    return shot


def _place(db, project_id, shot, media, order, duration, transition_in="cut"):
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path=media,
        review_status="Approved", width=320, height=180, duration_sec=duration,
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
        duration_sec=duration, transition_in=transition_in,
        take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()
    return take


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

def test_a_cut_is_the_default_and_costs_nothing_extra():
    assert render_service.TRANSITION_CUT == "cut"
    assert render_service.DEFAULT_DISSOLVE_SEC > 0


def test_an_unknown_transition_is_refused_rather_than_treated_as_a_cut(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """Silently downgrading an unrecognised name to a cut would deliver a film
    that ignores an edit somebody made and looks exactly like one that
    honoured it."""
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    first = _shot(db_session, sample_scene, 1, 2.0)
    second = _shot(db_session, sample_scene, 2, 2.0)
    _place(db_session, sample_project.id, first, media, 0, 2.0)
    _place(db_session, sample_project.id, second, media, 1, 2.0,
           transition_in="star-wipe")

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is False
    assert "star-wipe" in result["reason"]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@ffmpeg_required
@ffprobe_required
def test_a_film_of_cuts_still_takes_the_fast_path(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """The common case must not pay for a feature it does not use."""
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    for order in range(2):
        shot = _shot(db_session, sample_scene, order + 1, 2.0)
        _place(db_session, sample_project.id, shot, media, order, 2.0)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True, result["reason"]
    assert result["transitions"]["dissolves"] == 0
    assert result["transitions"]["re_encoded"] is False
    assert result["duration_sec"] == pytest.approx(4.0, abs=0.3)


@ffmpeg_required
@ffprobe_required
def test_a_dissolve_overlaps_the_two_shots_and_shortens_the_film(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """Two two-second shots with a half-second dissolve run 3.5 seconds. Left
    at 4, every later subtitle and narration cue is out of step."""
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    first = _shot(db_session, sample_scene, 1, 2.0)
    second = _shot(db_session, sample_scene, 2, 2.0)
    _place(db_session, sample_project.id, first, media, 0, 2.0)
    _place(db_session, sample_project.id, second, media, 1, 2.0,
           transition_in="dissolve")

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True, result["reason"]
    assert result["transitions"]["dissolves"] == 1
    assert result["transitions"]["re_encoded"] is True
    assert result["duration_sec"] == pytest.approx(
        4.0 - render_service.DEFAULT_DISSOLVE_SEC, abs=0.3
    )


@ffmpeg_required
@ffprobe_required
def test_a_dissolve_longer_than_the_shots_it_joins_is_refused(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """Overlapping past a neighbour's start does not blend two shots, it eats
    a third."""
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    first = _shot(db_session, sample_scene, 1, 0.2)
    second = _shot(db_session, sample_scene, 2, 0.2)
    _place(db_session, sample_project.id, first, media, 0, 0.2)
    _place(db_session, sample_project.id, second, media, 1, 0.2,
           transition_in="dissolve")

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is False
    assert "dissolve" in result["reason"].lower()


@ffmpeg_required
@ffprobe_required
def test_a_dissolve_on_the_first_shot_is_ignored_rather_than_refused(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """There is nothing before it to dissolve from. Refusing would block a
    render over a setting with no effect."""
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    shot = _shot(db_session, sample_scene, 1, 2.0)
    _place(db_session, sample_project.id, shot, media, 0, 2.0,
           transition_in="dissolve")

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True, result["reason"]
    assert result["transitions"]["dissolves"] == 0


# ---------------------------------------------------------------------------
# The tail
# ---------------------------------------------------------------------------

@ffmpeg_required
@ffprobe_required
def test_a_black_tail_is_appended_when_the_project_asks_for_one(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """A few frames of black before the loop stop the last frame and the first
    from touching, which is what makes a loop read as a loop rather than a
    glitch."""
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    shot = _shot(db_session, sample_scene, 1, 2.0)
    _place(db_session, sample_project.id, shot, media, 0, 2.0)
    sample_project.tail_black_frames = 12
    db_session.commit()

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True, result["reason"]
    expected = 2.0 + 12 / (sample_project.frame_rate or 24.0)
    assert result["duration_sec"] == pytest.approx(expected, abs=0.3)
    assert result["transitions"]["tail_black_frames"] == 12


@ffmpeg_required
@ffprobe_required
def test_no_tail_by_default(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    media = synthesise_clip(str(tmp_path / "a.mp4"), with_audio=False, duration=4.0)
    shot = _shot(db_session, sample_scene, 1, 2.0)
    _place(db_session, sample_project.id, shot, media, 0, 2.0)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["duration_sec"] == pytest.approx(2.0, abs=0.3)
    assert result["transitions"]["tail_black_frames"] == 0
