"""A render that lost its narration must say so.

NORI EP001 was re-rendered to change its narrator. Every one of the seventy-
nine lines was refused by the provider - the account had run out of credit -
and the render wrote a silent film, returned success, and left a provenance
sidecar reporting no warnings at all. The failures were in the log and nowhere
else, so the film looked finished until somebody played it.

Two things were wrong and both are fixed here.

The sidecar only ever carried the aspect-override warnings; everything the
render itself had to say - a missing narration, a duration that did not match
the manifest - went into the API response and never into the record. A record
that cannot report a bad render is not a record.

And a narration that was asked for and did not arrive was treated as a note
rather than a defect, so the delivery still passed its own validation.
"""

import json

from app.services import narration, render_service

from tests.test_render_service import (
    _create_placeholder_png,
    add_approved_take_on_timeline,
)


class _RefusingVoice:
    """A provider that has run out of credit, which is what happened."""

    def speak(self, text: str, out_path: str) -> float:
        raise narration.NarrationError(
            "The speech request was refused (429): You have no credits remaining."
        )


class _SilentVoice:
    """A voice that says nothing and claims success."""

    def speak(self, text: str, out_path: str) -> float:
        import wave

        with wave.open(out_path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(narration.SAMPLE_RATE)
            handle.writeframes(b"\x00\x00" * narration.SAMPLE_RATE)
        return 1.0


def _one_shot_film(db_session, project, shot, tmp_path, line: str = "I am a rice ball."):
    media = str(tmp_path / "frame.png")
    _create_placeholder_png(media, 320, 180)
    shot.dialogue = line
    db_session.add(shot)
    db_session.commit()
    add_approved_take_on_timeline(
        db_session, project.id, shot.id, media, duration=4.0
    )


def test_a_refused_narration_is_reported_not_swallowed(
    db_session, sample_project, sample_shot, tmp_path
):
    _one_shot_film(db_session, sample_project, sample_shot, tmp_path)

    result = render_service.render_review_video(
        db_session, sample_project.id, narrate=True, voice=_RefusingVoice()
    )

    assert result["rendered"] is True
    assert any("could not be spoken" in w for w in result["warnings"]), result["warnings"]


def test_the_sidecar_carries_what_the_render_said(
    db_session, sample_project, sample_shot, tmp_path
):
    _one_shot_film(db_session, sample_project, sample_shot, tmp_path)

    result = render_service.render_review_video(
        db_session, sample_project.id, narrate=True, voice=_RefusingVoice()
    )

    with open(result["provenance_path"], encoding="utf-8") as handle:
        record = json.load(handle)

    # The record is the thing that outlives the response. A silent film whose
    # sidecar says nothing went wrong is how one got delivered.
    assert any("could not be spoken" in w for w in record["warnings"]), record["warnings"]
    assert record["delivery_validation"]["pipeline_pass"] is False


def test_the_sidecar_records_what_was_spoken(
    db_session, sample_project, sample_shot, tmp_path
):
    _one_shot_film(db_session, sample_project, sample_shot, tmp_path)

    result = render_service.render_review_video(
        db_session, sample_project.id, narrate=True, voice=_SilentVoice()
    )

    with open(result["provenance_path"], encoding="utf-8") as handle:
        record = json.load(handle)

    # Whether a film was read at all, and whether any line was refused, is not
    # recoverable from the video afterwards.
    spoken = record["render_settings"]["narration"]
    assert spoken["present"] is True
    assert spoken["failures"] == []
    assert record["delivery_validation"]["pipeline_pass"] is True


def test_a_clean_render_still_passes(
    db_session, sample_project, sample_shot, tmp_path
):
    _one_shot_film(db_session, sample_project, sample_shot, tmp_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    with open(result["provenance_path"], encoding="utf-8") as handle:
        record = json.load(handle)

    assert result["rendered"] is True
    assert record["warnings"] == []
    assert record["delivery_validation"]["pipeline_pass"] is True


class _PacedVoice:
    """Reads at a fixed rate, so a line's length is known in advance."""

    def __init__(self, seconds: float):
        self.seconds = seconds

    def speak(self, text: str, out_path: str) -> float:
        import wave

        frames = int(narration.SAMPLE_RATE * self.seconds)
        with wave.open(out_path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(narration.SAMPLE_RATE)
            handle.writeframes(b"\x01\x00" * frames)
        return self.seconds


def test_the_record_says_how_long_each_line_took(
    db_session, sample_project, sample_shot, tmp_path
):
    # The shot is held four seconds; the narrator takes six. Planning a cut
    # from an estimate and never measuring it is how thirty-eight lines of one
    # episode came to overlap the line after them.
    _one_shot_film(db_session, sample_project, sample_shot, tmp_path)

    result = render_service.render_review_video(
        db_session, sample_project.id, narrate=True, voice=_PacedVoice(6.0)
    )

    with open(result["provenance_path"], encoding="utf-8") as handle:
        record = json.load(handle)

    spoken = record["render_settings"]["narration"]
    assert spoken["lines"] == [
        {"order": 1, "spoken_sec": 6.0, "available_sec": 4.0}
    ]
    assert spoken["overrun_sec"] == [2.0]
    # An overrun is a real defect: the next line starts on time regardless, so
    # the two are mixed on top of each other.
    assert any("run past the shot" in w for w in record["warnings"])
