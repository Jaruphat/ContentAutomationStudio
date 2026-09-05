"""A narrator that can be directed.

The local Windows voice is free, which is why it is the default, and it cannot
be directed at all. The Voice Bible asks for a calm male documentary narrator
at around 150 words per minute who pauses before three named phrases. None of
that is expressible to a platform voice: it has a name, a rate slider, and no
opinion about how a sentence should land.

A hosted voice takes an instruction, which is the whole reason to pay for one.
So the direction the channel already carries is passed through, per line, and
recorded on the track - a narration that sounds wrong needs to say what it was
told, or the next attempt is a guess.

Three things this is careful about, all of them about money and honesty:

* **Nothing is spoken without an authorised, configured key.** An overnight
  render must not quietly spend.
* **What was spent is reported.** Characters, per line, totalled - the number
  a bill can be checked against.
* **A failure is a failure.** Silence written to a WAV would render a film with
  no narration and no warning, which is worse than a refused render.
"""

import os
import wave

import httpx
import pytest

from app.services import narration
from app.services.openai_voice import OpenAIVoice


def _wav_bytes(seconds: float = 1.0, rate: int = 24000) -> bytes:
    import array
    import io
    import math

    samples = array.array(
        "h",
        (
            int(12000 * math.sin(2 * math.pi * 220 * n / rate))
            for n in range(int(rate * seconds))
        ),
    )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return buffer.getvalue()


class _Recorder:
    """Stands in for the API and remembers exactly what was asked of it."""

    def __init__(self, status: int = 200, body: bytes | None = None):
        self.requests: list[dict] = []
        self._status = status
        self._body = body if body is not None else _wav_bytes()

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            import json

            self.requests.append({
                "url": str(request.url),
                "json": json.loads(request.content.decode()),
                "auth": request.headers.get("authorization", ""),
            })
            if self._status != 200:
                return httpx.Response(self._status, json={
                    "error": {"message": "insufficient_quota"}
                })
            return httpx.Response(200, content=self._body)

        return httpx.MockTransport(handle)


def _voice(recorder: _Recorder, **over) -> OpenAIVoice:
    return OpenAIVoice(
        api_key="sk-test", transport=recorder.transport(), **over
    )


# ---------------------------------------------------------------------------
# Speaking
# ---------------------------------------------------------------------------

def test_it_writes_a_wav_and_reports_how_long_it_runs(tmp_path):
    recorder = _Recorder(body=_wav_bytes(seconds=2.0))
    voice = _voice(recorder)

    seconds = voice.speak("Until last night.", str(tmp_path / "a.wav"))

    assert os.path.isfile(tmp_path / "a.wav")
    assert seconds == pytest.approx(2.0, abs=0.2)


def test_the_direction_reaches_the_request(tmp_path):
    """The reason to pay for a hosted voice: it takes an instruction, and the
    channel already carries one."""
    recorder = _Recorder()
    voice = _voice(
        recorder,
        instructions=(
            "Calm male documentary narrator, quiet confidence, controlled "
            "curiosity, around 150 words per minute."
        ),
    )

    voice.speak("The station closed thirty years ago.", str(tmp_path / "a.wav"))

    body = recorder.requests[0]["json"]
    assert "documentary narrator" in body["instructions"]
    assert body["input"] == "The station closed thirty years ago."


def test_the_voice_and_model_are_chosen_not_assumed(tmp_path):
    recorder = _Recorder()
    voice = _voice(recorder, voice="onyx", model="gpt-4o-mini-tts")

    voice.speak("x", str(tmp_path / "a.wav"))

    body = recorder.requests[0]["json"]
    assert body["voice"] == "onyx"
    assert body["model"] == "gpt-4o-mini-tts"


def test_it_asks_for_wav_because_the_mixer_reads_wav(tmp_path):
    """Anything else would be re-encoded on the way in, for nothing."""
    recorder = _Recorder()

    _voice(recorder).speak("x", str(tmp_path / "a.wav"))

    assert recorder.requests[0]["json"]["response_format"] == "wav"


def test_the_key_is_sent_and_never_written_anywhere(tmp_path):
    recorder = _Recorder()
    voice = _voice(recorder)

    voice.speak("x", str(tmp_path / "a.wav"))

    assert recorder.requests[0]["auth"] == "Bearer sk-test"
    assert "sk-test" not in repr(voice)
    assert "sk-test" not in str(voice.usage)


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

def test_an_unconfigured_voice_refuses_before_it_calls_anything(tmp_path):
    voice = OpenAIVoice(api_key="")

    with pytest.raises(narration.NarrationError) as exc:
        voice.speak("x", str(tmp_path / "a.wav"))
    assert "OPENAI_API_KEY" in str(exc.value)


def test_what_was_spent_is_counted_as_it_goes(tmp_path):
    """A bill has to be checkable against something."""
    recorder = _Recorder()
    voice = _voice(recorder)

    voice.speak("Until last night.", str(tmp_path / "a.wav"))
    voice.speak("But that wasn't the strange part.", str(tmp_path / "b.wav"))

    assert voice.usage["lines"] == 2
    assert voice.usage["characters"] == len("Until last night.") + len(
        "But that wasn't the strange part."
    )
    assert voice.usage["model"] == voice.model


def test_a_refused_request_raises_rather_than_writing_silence(tmp_path):
    """Silence in the WAV renders a film with no narration and no warning,
    which is worse than a render that stops."""
    recorder = _Recorder(status=429)
    voice = _voice(recorder)

    with pytest.raises(narration.NarrationError) as exc:
        voice.speak("x", str(tmp_path / "a.wav"))

    assert "insufficient_quota" in str(exc.value)
    assert not os.path.exists(tmp_path / "a.wav")


def test_an_empty_line_is_never_sent(tmp_path):
    """Paying to synthesise nothing, and getting a clip of nothing back."""
    recorder = _Recorder()
    voice = _voice(recorder)

    with pytest.raises(narration.NarrationError):
        voice.speak("   ", str(tmp_path / "a.wav"))
    assert recorder.requests == []


# ---------------------------------------------------------------------------
# Through the track builder
# ---------------------------------------------------------------------------

def test_the_track_builder_takes_this_voice_like_any_other(tmp_path):
    """The point of the Voice protocol: nothing above here changes."""
    recorder = _Recorder(body=_wav_bytes(seconds=0.5))
    voice = _voice(recorder)

    track = narration.build_track(
        [
            narration.NarrationCue(
                start_sec=0.0, end_sec=4.0,
                text="Every night at exactly 3:17."),
            narration.NarrationCue(
                start_sec=4.0, end_sec=8.0, text="That's impossible."),
        ],
        str(tmp_path / "narration.wav"),
        voice=voice,
    )

    assert os.path.isfile(track.path)
    assert track.overruns == []
    assert len(recorder.requests) == 2


# ---------------------------------------------------------------------------
# The header the endpoint actually sends
# ---------------------------------------------------------------------------

def _streamed_wav(seconds: float = 6.2, rate: int = 24000) -> bytes:
    """A WAV whose header claims an unknown length, as OpenAI's does.

    Found on the first real call: the endpoint streams, so it writes the
    sentinel frame count 0x7FFFFFFF rather than the real one. Trusting the
    header made a six-second line report as twenty-four hours - which then
    reports as an overrun on every shot, and would size the narration canvas
    from a number nothing on the timeline can match.
    """
    import struct

    frames = int(rate * seconds)
    data = bytes([0, 1]) * frames
    header = (
        b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data" + struct.pack("<I", 0x7FFFFFFF * 2)
    )
    return header + data


def test_a_streamed_wav_is_measured_by_its_bytes_not_its_header(tmp_path):
    """The real defect, from the first live call. A header-derived duration
    made a six-second line claim twenty-four hours."""
    recorder = _Recorder(body=_streamed_wav(seconds=6.2))

    seconds = _voice(recorder).speak("x", str(tmp_path / "a.wav"))

    assert seconds == pytest.approx(6.2, abs=0.1)


def test_a_streamed_wav_mixes_at_its_real_length(tmp_path):
    """The same trap one layer up: the track builder reads frames by the
    header's count too, and a sentinel there would pad the film with silence
    to a length nothing on the timeline matches."""
    recorder = _Recorder(body=_streamed_wav(seconds=1.0))

    track = narration.build_track(
        [narration.NarrationCue(start_sec=0.0, end_sec=4.0, text="A line.")],
        str(tmp_path / "narration.wav"),
        voice=_voice(recorder),
    )

    assert track is not None
    assert track.overruns == [], "a one-second line does not overrun four seconds"
    with wave.open(track.path, "rb") as handle:
        assert handle.getnframes() / handle.getframerate() == pytest.approx(
            4.0, abs=0.2
        )
