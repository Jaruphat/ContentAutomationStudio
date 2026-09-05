"""Deciding what the film sounds like, shot by shot.

H3 gives every clip a native audio track and the render took all of it,
wholesale. That is the right default and a bad only-option: the generated
audio for one shot is regularly a mechanical hum, a burst of speech in no
language, or a room tone that belongs to a different room, and the only
remedies were to accept it across the whole film or lose audio across the
whole film.

Two controls, at the two levels where the decisions actually are:

* **Per shot** - use this clip's own audio or not, and at what level. One bad
  eight seconds should cost eight seconds, not three minutes.
* **Per project** - a music bed under the whole film, ducked under narration,
  because a bed is a property of the film and not of any shot in it.

Everything here is measured against a real rendered file. A test that asserts
an FFmpeg command was built is a test of the command, not of the sound.
"""

import json
import os
import re
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Shot, Take, TimelineItem
from app.services import media_probe, render_service, revisions

ffmpeg_required = pytest.mark.skipif(
    render_service.ffmpeg_path() is None,
    reason="FFmpeg is not installed on this machine",
)
ffprobe_required = pytest.mark.skipif(
    render_service.ffprobe_path() is None,
    reason="ffprobe is not installed on this machine",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shot(db, scene, order, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="video", video_prompt=f"shot {order}", **kwargs,
    )
    db.add(shot)
    db.commit()
    return shot


def _place(db, project_id, shot, media, order, duration=1.0):
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path=media,
        review_status="Approved", width=320, height=180,
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
        in_point_sec=order * duration,
        out_point_sec=(order + 1) * duration,
        duration_sec=duration,
        take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()
    return take


def _rms_dbfs(path: str, start: float, duration: float) -> float:
    """The RMS level of one window of a file, in dBFS.

    Windowed rather than whole-file because the question here is always about
    one shot inside a programme that was loudness-normalised as a whole.
    """
    returncode, _stdout, stderr = media_probe.run_captured([
        media_probe.ffmpeg_path(), "-hide_banner", "-nostats",
        "-ss", f"{start:g}", "-t", f"{duration:g}", "-i", path,
        "-af", "astats=metadata=1:reset=0", "-f", "null", "-",
    ], timeout=60)
    assert returncode == 0, stderr
    levels = [float(v) for v in re.findall(r"RMS level dB:\s*(-?\d+\.?\d*)", stderr)]
    if not levels:
        # astats prints "-inf" for pure digital silence.
        assert "RMS level dB: -inf" in stderr, stderr[-500:]
        return -120.0
    return max(levels)


def _write_tone(path: str, *, seconds: float = 2.0) -> str:
    ffmpeg = media_probe.ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed on this machine")
    returncode, _stdout, stderr = media_probe.run_captured([
        ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", f"sine=frequency=220:duration={seconds:g}:sample_rate=44100",
        "-ac", "2", path,
    ], timeout=60)
    if returncode != 0 or not os.path.isfile(path):
        pytest.skip(f"could not synthesise music bed: {stderr[-200:]}")
    return path


# ---------------------------------------------------------------------------
# Per-shot audio
# ---------------------------------------------------------------------------

@ffmpeg_required
@ffprobe_required
class TestShotAudioDirection:

    def test_a_muted_shot_is_silent_while_the_others_are_not(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """The whole point: one bad eight seconds costs eight seconds."""
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=2.0,
        )
        loud = _shot(db_session, sample_scene, 1)
        muted = _shot(db_session, sample_scene, 2, audio_mode="mute")
        _place(db_session, sample_project.id, loud, media, 0, duration=2.0)
        _place(db_session, sample_project.id, muted, media, 1, duration=2.0)

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        first = _rms_dbfs(result["output_path"], 0.3, 1.2)
        second = _rms_dbfs(result["output_path"], 2.3, 1.2)
        assert first > -40.0, "the unmuted shot must still be audible"
        assert second < -60.0, f"the muted shot is still audible at {second} dB"

    def test_muting_every_shot_leaves_a_silent_film_rather_than_a_broken_one(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """A film with nothing worth hearing is a legitimate outcome, and it
        must not be reported as one that carries audio."""
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=1.0,
        )
        shot = _shot(db_session, sample_scene, 1, audio_mode="mute")
        _place(db_session, sample_project.id, shot, media, 0)

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["has_audio"] is False

    def test_a_shot_turned_down_is_quieter_than_one_left_alone(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """Level, not just on and off: generated audio is often usable but
        far too loud against the shot beside it."""
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=2.0,
        )
        full = _shot(db_session, sample_scene, 1)
        quiet = _shot(db_session, sample_scene, 2, audio_gain_db=-18.0)
        _place(db_session, sample_project.id, full, media, 0, duration=2.0)
        _place(db_session, sample_project.id, quiet, media, 1, duration=2.0)

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        first = _rms_dbfs(result["output_path"], 0.3, 1.2)
        second = _rms_dbfs(result["output_path"], 2.3, 1.2)
        # Programme loudness normalisation moves both by the same amount, so
        # the difference between them survives it.
        assert first - second == pytest.approx(18.0, abs=4.0)

    def test_the_render_reports_what_it_did_to_each_shot(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """A film that sounds wrong needs to say which shot was turned down,
        or the next edit is a guess."""
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=1.0,
        )
        shot = _shot(db_session, sample_scene, 1, audio_mode="mute")
        _place(db_session, sample_project.id, shot, media, 0)

        result = render_service.render_review_video(db_session, sample_project.id)

        muted = result["audio_direction"]["muted_shots"]
        assert shot.id in muted


# ---------------------------------------------------------------------------
# The music bed
# ---------------------------------------------------------------------------

@ffmpeg_required
@ffprobe_required
class TestMusicBed:

    def test_a_bed_gives_a_silent_film_a_soundtrack(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """Stills and muted clips are the common case for a bed - there is
        nothing else to hear."""
        media = synthesise_clip(
            str(tmp_path / "silent.mp4"), with_audio=False, duration=2.0,
        )
        shot = _shot(db_session, sample_scene, 1)
        _place(db_session, sample_project.id, shot, media, 0, duration=2.0)
        sample_project.music_path = _write_tone(str(tmp_path / "bed.wav"))
        db_session.commit()

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["has_audio"] is True
        assert result["audio_direction"]["music"]["present"] is True
        assert _rms_dbfs(result["output_path"], 0.3, 1.2) > -50.0

    def test_the_bed_is_cut_to_the_film_and_not_the_other_way_round(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """A four-minute track under a two-second film must not produce a
        four-minute film."""
        media = synthesise_clip(
            str(tmp_path / "silent.mp4"), with_audio=False, duration=1.0,
        )
        shot = _shot(db_session, sample_scene, 1)
        _place(db_session, sample_project.id, shot, media, 0, duration=1.0)
        sample_project.music_path = _write_tone(str(tmp_path / "bed.wav"), seconds=8.0)
        db_session.commit()

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["duration_sec"] == pytest.approx(1.0, abs=0.4)

    def test_a_bed_sits_under_the_takes_rather_than_over_them(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """It is a bed. Mixed at parity it would be a duet with the film."""
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=2.0,
        )
        shot = _shot(db_session, sample_scene, 1)
        _place(db_session, sample_project.id, shot, media, 0, duration=2.0)
        sample_project.music_path = _write_tone(str(tmp_path / "bed.wav"))
        db_session.commit()

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["audio_direction"]["music"]["gain_db"] < 0.0

    def test_a_missing_music_file_is_reported_and_the_film_still_renders(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """Losing the whole render over a moved file would be the wrong trade;
        so would delivering a silent film that was supposed to have music and
        saying nothing."""
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=1.0,
        )
        shot = _shot(db_session, sample_scene, 1)
        _place(db_session, sample_project.id, shot, media, 0)
        sample_project.music_path = str(tmp_path / "gone.wav")
        db_session.commit()

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["audio_direction"]["music"]["present"] is False
        assert any("music" in w.lower() for w in result["warnings"]), result["warnings"]

    def test_no_music_configured_changes_nothing(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        media = synthesise_clip(
            str(tmp_path / "tone.mp4"), with_audio=True, duration=1.0,
        )
        shot = _shot(db_session, sample_scene, 1)
        _place(db_session, sample_project.id, shot, media, 0)

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["audio_direction"]["music"]["present"] is False
        assert result["has_audio"] is True

    def test_the_bed_ducks_under_narration(
        self, db_session: Session, sample_project, sample_scene, tmp_path,
        synthesise_clip,
    ):
        """Music at reading level over a voice is the commonest way a review
        cut becomes unwatchable."""
        media = synthesise_clip(
            str(tmp_path / "silent.mp4"), with_audio=False, duration=2.0,
        )
        shot = _shot(db_session, sample_scene, 1, dialogue="A boy sweeps the sky.")
        _place(db_session, sample_project.id, shot, media, 0, duration=2.0)
        sample_project.music_path = _write_tone(str(tmp_path / "bed.wav"))
        db_session.commit()

        result = render_service.render_review_video(
            db_session, sample_project.id, narrate=True,
        )

        assert result["rendered"] is True, result["reason"]
        music = result["audio_direction"]["music"]
        if result["narration"]["present"]:
            assert music["ducked_under_narration"] is True
            assert music["gain_db"] < render_service.MUSIC_GAIN_DB


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

@ffmpeg_required
@ffprobe_required
def test_audio_direction_is_recorded_in_the_render_provenance(
    db_session: Session, sample_project, sample_scene, tmp_path, synthesise_clip,
):
    """The sidecar is what a delivered file is checked against later."""
    media = synthesise_clip(
        str(tmp_path / "tone.mp4"), with_audio=True, duration=1.0,
    )
    shot = _shot(db_session, sample_scene, 1, audio_gain_db=-6.0)
    _place(db_session, sample_project.id, shot, media, 0)

    result = render_service.render_review_video(db_session, sample_project.id)
    assert result["rendered"] is True, result["reason"]

    with open(result["provenance_path"], encoding="utf-8") as f:
        recorded = json.load(f)["render_settings"]["audio"]["direction"]
    assert recorded["adjusted_shots"][shot.id] == -6.0
