"""An overrun has to say by how much.

"2 narration line(s) run past the shot they belong to" is a fact with no
decision attached to it. A line 0.3 seconds long is a bleed nobody hears
across a hard cut; a line 5 seconds long has swallowed the shot after it. The
same sentence produces both, because a hosted narrator does not read at a
fixed rate - measured on one episode, the same voice under the same direction
ran between 52 and 179 words per minute, and re-reading an unchanged line
moved it far enough to cross the tolerance and back.

Word count cannot size these lines and neither can one measurement. What the
writer can act on is the number of seconds this render was over by, so it is
reported beside the line.
"""

import uuid

from app.services import narration


class _PacedVoice:
    """A voice that takes exactly as long as it is told to."""

    def __init__(self, seconds: dict[str, float]):
        self.seconds = seconds

    def speak(self, text: str, out_path: str) -> float:
        import array
        import wave

        length = self.seconds.get(text, 1.0)
        frames = int(length * narration.SAMPLE_RATE)
        with wave.open(out_path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(narration.SAMPLE_RATE)
            handle.writeframes(array.array("h", bytes(2 * frames)).tobytes())
        return length


def _cues():
    return [
        narration.NarrationCue(start_sec=0.0, end_sec=3.0, text="A short line."),
        narration.NarrationCue(start_sec=3.0, end_sec=6.0, text="A long line."),
    ]


def test_the_amount_is_reported_beside_the_line(tmp_path):
    voice = _PacedVoice({"A short line.": 2.0, "A long line.": 4.4})

    track = narration.build_track(
        _cues(), str(tmp_path / f"{uuid.uuid4()}.wav"), voice=voice
    )

    assert track.overruns == ["A long line."]
    assert track.overrun_sec == [1.4]


def test_a_line_inside_its_shot_reports_nothing(tmp_path):
    voice = _PacedVoice({"A short line.": 2.0, "A long line.": 2.9})

    track = narration.build_track(
        _cues(), str(tmp_path / f"{uuid.uuid4()}.wav"), voice=voice
    )

    assert track.overruns == []
    assert track.overrun_sec == []


def test_the_render_warning_carries_the_worst_amount(tmp_path):
    """The warning is what a person actually reads. "run past the shot" tells
    them to act; "by up to 0.3s" tells them whether to."""
    from app.services import render_service

    cues = _cues()
    voice = _PacedVoice(
        {cue.text: (cue.end_sec - cue.start_sec) + 1.75 for cue in cues}
    )
    track = narration.build_track(
        cues, str(tmp_path / f"{uuid.uuid4()}.wav"), voice=voice
    )

    assert track.overrun_sec == [1.75, 1.75]
    assert render_service._overrun_warning(track) == (
        "2 narration line(s) run past the shot they belong to, by up to "
        "1.8s; the picture was left in step."
    )
