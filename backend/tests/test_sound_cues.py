"""A sound at a moment, which is what an audio timeline is.

The blueprint's sound design is a list of times: cold night ambience from 0:00,
a clock ticking at 0:04, rail vibration rising at 0:06, a pneumatic door at
0:14, footsteps at 0:17. None of that is expressible as a property of a shot,
because half of it starts inside one shot and runs through the next, and the
rest is a specific instant rather than a duration.

So a cue is a sound, a place, and a level. Its place is given relative to a
shot rather than to the film, because a shot moves whenever the cut before it
changes length - and a cue pinned to an absolute second silently detaches from
the thing it was made for the first time somebody trims a shot.

The refusals are about the same thing from the other side: a cue that lands
after the film ends plays to nobody and says nothing about it, so it is
refused; and a cue on a shot that is not in the cut is refused too, since its
anchor is not on the timeline at all.
"""

import os
import uuid

import pytest

from app.models import Shot, Take, TimelineItem
from app.services import media_probe, render_service, revisions, sound_cues


def _shot(db, scene, order, duration=4.0):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="image-to-video", video_prompt="x",
        planned_duration_sec=duration,
    )
    db.add(shot)
    db.commit()
    return shot


def _place(db, project_id, shot, media, order, duration=4.0):
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
        duration_sec=duration,
        take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()
    return take


def _tone(path: str, seconds: float = 0.5, hz: int = 880) -> str:
    ffmpeg = media_probe.ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed on this machine")
    code, _out, err = media_probe.run_captured([
        ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", f"sine=frequency={hz}:duration={seconds:g}:sample_rate=44100",
        "-ac", "2", path,
    ], timeout=60)
    if code != 0 or not os.path.isfile(path):
        pytest.skip(f"could not synthesise a cue: {err[-200:]}")
    return path


# ---------------------------------------------------------------------------
# Placing a cue
# ---------------------------------------------------------------------------

def test_a_cue_is_placed_relative_to_its_shot(db_session, sample_project, sample_scene, tmp_path):
    """Absolute seconds detach from the thing they were made for the first
    time somebody trims an earlier shot."""
    first = _shot(db_session, sample_scene, 1)
    second = _shot(db_session, sample_scene, 2)
    _place(db_session, sample_project.id, first, str(tmp_path / "a.mp4"), 0)
    _place(db_session, sample_project.id, second, str(tmp_path / "b.mp4"), 1)

    cue = sound_cues.create_cue(
        db_session, sample_project.id,
        shot_id=second.id, file_path=_tone(str(tmp_path / "door.wav")),
        offset_sec=1.0, gain_db=-6.0, label="pneumatic door",
    )

    resolved = sound_cues.resolve_cues(db_session, sample_project.id)
    assert [entry["start_sec"] for entry in resolved] == [5.0]
    assert resolved[0]["cue_id"] == cue.id


def test_the_same_cue_moves_when_the_cut_before_it_changes(
    db_session, sample_project, sample_scene, tmp_path,
):
    """This is the whole reason a cue is anchored to a shot."""
    first = _shot(db_session, sample_scene, 1)
    second = _shot(db_session, sample_scene, 2)
    _place(db_session, sample_project.id, first, str(tmp_path / "a.mp4"), 0)
    _place(db_session, sample_project.id, second, str(tmp_path / "b.mp4"), 1)
    sound_cues.create_cue(
        db_session, sample_project.id, shot_id=second.id,
        file_path=_tone(str(tmp_path / "door.wav")), offset_sec=1.0,
    )

    item = (
        db_session.query(TimelineItem)
        .filter(TimelineItem.project_id == sample_project.id,
                TimelineItem.order == 0)
        .one()
    )
    item.duration_sec = 2.0
    item.out_point_sec = 2.0
    second_item = (
        db_session.query(TimelineItem)
        .filter(TimelineItem.project_id == sample_project.id,
                TimelineItem.order == 1)
        .one()
    )
    second_item.in_point_sec = 2.0
    second_item.out_point_sec = 6.0
    db_session.commit()

    resolved = sound_cues.resolve_cues(db_session, sample_project.id)
    assert resolved[0]["start_sec"] == 3.0


def test_a_cue_on_a_shot_that_is_not_in_the_cut_is_refused(
    db_session, sample_project, sample_scene, tmp_path,
):
    """Its anchor is not on the timeline, so there is no moment to place it
    at - and a cue that silently plays at zero is worse than one refused."""
    orphan = _shot(db_session, sample_scene, 1)

    with pytest.raises(sound_cues.SoundCueError):
        sound_cues.create_cue(
            db_session, sample_project.id, shot_id=orphan.id,
            file_path=_tone(str(tmp_path / "x.wav")), offset_sec=0.0,
        )


def test_a_cue_past_the_end_of_its_shot_is_allowed_and_reported(
    db_session, sample_project, sample_scene, tmp_path,
):
    """Ambience is meant to run through a cut. Refusing that would make the
    feature useless for the half of sound design that is not a hit."""
    shot = _shot(db_session, sample_scene, 1)
    _place(db_session, sample_project.id, shot, str(tmp_path / "a.mp4"), 0)

    cue = sound_cues.create_cue(
        db_session, sample_project.id, shot_id=shot.id,
        file_path=_tone(str(tmp_path / "amb.wav"), seconds=8.0),
        offset_sec=0.0, label="night ambience",
    )

    assert cue.id
    resolved = sound_cues.resolve_cues(db_session, sample_project.id)
    assert resolved[0]["runs_past_the_end"] is True


def test_a_cue_starting_after_the_film_ends_is_refused(
    db_session, sample_project, sample_scene, tmp_path,
):
    shot = _shot(db_session, sample_scene, 1)
    _place(db_session, sample_project.id, shot, str(tmp_path / "a.mp4"), 0)

    with pytest.raises(sound_cues.SoundCueError) as exc:
        sound_cues.create_cue(
            db_session, sample_project.id, shot_id=shot.id,
            file_path=_tone(str(tmp_path / "x.wav")), offset_sec=99.0,
        )
    assert "after" in str(exc.value).lower()


def test_a_missing_sound_file_is_refused(
    db_session, sample_project, sample_scene, tmp_path,
):
    shot = _shot(db_session, sample_scene, 1)
    _place(db_session, sample_project.id, shot, str(tmp_path / "a.mp4"), 0)

    with pytest.raises(sound_cues.SoundCueError):
        sound_cues.create_cue(
            db_session, sample_project.id, shot_id=shot.id,
            file_path=str(tmp_path / "nothing.wav"), offset_sec=0.0,
        )


# ---------------------------------------------------------------------------
# Reaching the render
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    render_service.ffmpeg_path() is None or render_service.ffprobe_path() is None,
    reason="FFmpeg is not installed on this machine",
)
def test_a_cue_is_audible_at_its_moment_and_not_before(
    db_session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """Measured on the rendered file. A test that asserts an FFmpeg command
    was built tests the command, not the sound."""
    media = synthesise_clip(
        str(tmp_path / "silent.mp4"), with_audio=False, duration=4.0,
    )
    shot = _shot(db_session, sample_scene, 1, duration=4.0)
    _place(db_session, sample_project.id, shot, media, 0, duration=4.0)
    sound_cues.create_cue(
        db_session, sample_project.id, shot_id=shot.id,
        file_path=_tone(str(tmp_path / "hit.wav"), seconds=1.0),
        offset_sec=2.0, label="door",
    )

    result = render_service.render_review_video(db_session, sample_project.id)
    assert result["rendered"] is True, result["reason"]
    assert result["has_audio"] is True
    assert result["audio_direction"]["sound_cues"]["placed"] == 1

    from tests.test_render_audio_direction import _rms_dbfs

    before = _rms_dbfs(result["output_path"], 0.2, 1.0)
    during = _rms_dbfs(result["output_path"], 2.2, 0.6)
    assert during > before + 20, f"cue not audible: {before} then {during}"


@pytest.mark.skipif(
    render_service.ffmpeg_path() is None or render_service.ffprobe_path() is None,
    reason="FFmpeg is not installed on this machine",
)
def test_a_cue_whose_file_vanished_warns_and_the_film_still_renders(
    db_session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """Losing a whole render to a moved sound file is the wrong trade; so is
    delivering a film missing a sound and saying nothing."""
    media = synthesise_clip(
        str(tmp_path / "silent.mp4"), with_audio=False, duration=2.0,
    )
    shot = _shot(db_session, sample_scene, 1, duration=2.0)
    _place(db_session, sample_project.id, shot, media, 0, duration=2.0)
    cue = sound_cues.create_cue(
        db_session, sample_project.id, shot_id=shot.id,
        file_path=_tone(str(tmp_path / "hit.wav")), offset_sec=0.5,
        label="door",
    )
    os.remove(cue.file_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True, result["reason"]
    assert any("door" in warning for warning in result["warnings"]), result["warnings"]
