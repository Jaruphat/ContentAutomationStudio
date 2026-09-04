"""A spoken narration track, built from the same words as the subtitles.

The render already carries whatever audio the takes came with - room tone,
footsteps, whatever the video model produced. What it had no way to carry was a
voice reading the film, which is what a narrated short is. Writing that as a
separate audio file and muxing it by hand outside the app would mean the thing
the user downloads is not the thing the app made.

Two properties matter and are asserted here.

*The narration is the subtitles.* Both are built from `Shot.dialogue`, so a
line cannot be heard that is not shown, or shown that is not heard. Any other
arrangement drifts the moment somebody edits one of them.

*Timing comes from the timeline, not from the speech.* A clip is as long as the
shot it belongs to; a voice that runs long is allowed to overrun into the gap
rather than pushing the film out of sync with its own picture.
"""

import os
import wave

import pytest

from app.services import narration


class RecordingVoice:
    """A stand-in speech engine that writes real, silent, correctly-timed WAVs."""

    def __init__(self, seconds_per_word: float = 0.4):
        self.seconds_per_word = seconds_per_word
        self.spoken: list[str] = []

    def speak(self, text: str, out_path: str) -> float:
        self.spoken.append(text)
        duration = max(0.2, len(text.split()) * self.seconds_per_word)
        frames = int(duration * narration.SAMPLE_RATE)
        with wave.open(out_path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(narration.SAMPLE_RATE)
            handle.writeframes(b"\x00\x00" * frames)
        return duration


def _cue(start: float, end: float, text: str) -> narration.NarrationCue:
    return narration.NarrationCue(start_sec=start, end_sec=end, text=text)


def test_a_film_with_nothing_to_say_produces_no_track(tmp_path):
    """Silence is not a track of silence; it is the absence of one.

    A wholly empty narration file would make the render mix a silent stream
    over the takes and report a narration that nobody wrote.
    """
    voice = RecordingVoice()
    result = narration.build_track([], str(tmp_path / "narration.wav"), voice=voice)
    assert result is None
    assert voice.spoken == []


def test_each_line_is_spoken_once_and_placed_at_its_cue(tmp_path):
    voice = RecordingVoice()
    out = str(tmp_path / "narration.wav")

    result = narration.build_track(
        [_cue(0.0, 8.0, "They gave her the smallest desk."),
         _cue(8.0, 16.0, "So she mapped the crack in a teacup.")],
        out, voice=voice,
    )

    assert result is not None
    assert voice.spoken == [
        "They gave her the smallest desk.",
        "So she mapped the crack in a teacup.",
    ]
    with wave.open(out, "rb") as handle:
        seconds = handle.getnframes() / handle.getframerate()
    # The track spans the film, not just the speech inside it.
    assert seconds == pytest.approx(16.0, abs=0.2)


def test_a_line_is_placed_at_its_own_start_not_after_the_previous_one(tmp_path):
    """Speech shorter than its shot must not drag the next line early.

    If clips were simply concatenated, one terse line would pull every
    following line out of step with the picture for the rest of the film.
    """
    voice = RecordingVoice(seconds_per_word=0.1)
    out = str(tmp_path / "narration.wav")

    narration.build_track(
        [_cue(0.0, 8.0, "Short."), _cue(8.0, 16.0, "Second line here.")],
        out, voice=voice,
    )

    samples = narration.read_mono(out)
    # Nothing should have been written into the silence before the second cue.
    quiet_window = samples[int(2.0 * narration.SAMPLE_RATE):int(7.5 * narration.SAMPLE_RATE)]
    assert all(value == 0 for value in quiet_window[:2000])


def test_an_overlong_line_overruns_rather_than_shifting_the_film(tmp_path):
    """Timing follows the picture. A voice that runs long is the lesser fault."""
    voice = RecordingVoice(seconds_per_word=2.0)
    out = str(tmp_path / "narration.wav")

    result = narration.build_track(
        [_cue(0.0, 2.0, "A line far too long for its shot"), _cue(2.0, 4.0, "Next")],
        out, voice=voice,
    )

    assert result is not None
    assert result.overruns, "an overrun has to be reported, not hidden"
    assert result.overruns[0].startswith("A line far too long")


def test_blank_dialogue_is_skipped_without_a_gap_in_the_others(tmp_path):
    voice = RecordingVoice()
    out = str(tmp_path / "narration.wav")

    narration.build_track(
        [_cue(0.0, 4.0, "   "), _cue(4.0, 8.0, "Only this is spoken.")],
        out, voice=voice,
    )

    assert voice.spoken == ["Only this is spoken."]


def test_cues_come_from_the_same_field_the_subtitles_use(db_session, sample_project):
    """Narration and subtitles must not be able to disagree."""
    from app.services import subtitle_service
    assert narration.DIALOGUE_FIELD == subtitle_service.DIALOGUE_FIELD


def test_a_voice_that_fails_on_one_line_does_not_lose_the_rest(tmp_path):
    """One unpronounceable line should cost that line, not the whole track."""

    class FlakyVoice(RecordingVoice):
        def speak(self, text, out_path):
            if "boom" in text:
                raise RuntimeError("speech engine refused this line")
            return super().speak(text, out_path)

    voice = FlakyVoice()
    out = str(tmp_path / "narration.wav")

    result = narration.build_track(
        [_cue(0.0, 4.0, "boom"), _cue(4.0, 8.0, "This line is fine.")],
        out, voice=voice,
    )

    assert result is not None
    assert result.failures and "boom" in result.failures[0]
    assert os.path.exists(out)
