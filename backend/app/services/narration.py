"""A spoken narration track, built from the same words as the subtitles.

The render already carries whatever audio the takes came with. What it had no
way to carry was a voice reading the film, which for a narrated short is most
of the film. Producing that outside the app would mean the file a user
downloads is not the file the app made, and its provenance would stop being
true at the last step.

Two decisions shape everything here.

*The narration is the subtitles.* Both read ``Shot.dialogue``, so a line
cannot be heard that is not shown, or shown that is not heard.

*Timing follows the picture.* Each line is placed at the start of the timeline
item it belongs to, never appended to the previous one. A voice shorter than
its shot leaves a pause; a voice longer than its shot overruns and is reported.
Concatenating instead would let one terse line drag every later line out of
step for the rest of the film.

The default voice is the operating system's own, so a run costs nothing. A
hosted voice would sound better, and that is a decision with a price on it.
"""

from __future__ import annotations

import array
import logging
import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.services.subtitle_service import DIALOGUE_FIELD

logger = logging.getLogger("cas.narration")

__all__ = [
    "DIALOGUE_FIELD", "SAMPLE_RATE", "NarrationCue", "NarrationTrack",
    "WindowsSapiVoice", "build_track", "cues_for_project", "read_mono",
]

#: 22.05 kHz mono is what the platform voices produce natively; resampling a
#: spoken track buys nothing the render's own encode does not already do.
SAMPLE_RATE = 22050
#: How long to let one line take before giving up on the speech engine.
SPEECH_TIMEOUT_SEC = 120


@dataclass(frozen=True)
class NarrationCue:
    """One line, and the stretch of film it belongs to."""

    start_sec: float
    end_sec: float
    text: str


@dataclass
class NarrationTrack:
    """The assembled track, and everything that did not go perfectly."""

    path: str
    duration_sec: float
    #: Lines whose speech ran past the shot they belong to. Reported rather
    #: than trimmed: a clipped word is worse than a slight overrun, and the
    #: fix is to rewrite the line or lengthen the shot.
    overruns: list[str] = field(default_factory=list)
    #: By how many seconds, in the same order. A hosted narrator does not read
    #: at a fixed rate - one episode measured the same voice between 52 and
    #: 179 words per minute - so "over" on its own says nothing about whether
    #: it matters. Three tenths of a second is a bleed across a hard cut; five
    #: seconds has swallowed the shot after it.
    overrun_sec: list[float] = field(default_factory=list)
    #: Lines the speech engine refused. One bad line costs that line only.
    failures: list[str] = field(default_factory=list)


class NarrationError(RuntimeError):
    """A line that could not be spoken, with the reason.

    Named here rather than in a provider so the track builder catches one
    thing whichever voice is in use, and so a caller can tell a voice that
    refused from a voice that was never configured.
    """


class Voice(Protocol):
    """Anything that can write ``text`` to a mono WAV and say how long it is."""

    def speak(self, text: str, out_path: str) -> float: ...


class WindowsSapiVoice:
    """The speech voices already installed on Windows.

    Chosen as the default because it is local and free: an overnight render
    should not quietly spend money. Quality is dated, and a hosted voice is the
    obvious upgrade when someone decides to authorise one.
    """

    def __init__(self, voice_name: str = "", rate: int = 0):
        self._voice_name = voice_name
        self._rate = rate  # SAPI's -10..10 scale; 0 is normal.

    def speak(self, text: str, out_path: str) -> float:
        escaped = text.replace("'", "''")
        select = (
            f"$s.SelectVoice('{self._voice_name}');" if self._voice_name else ""
        )
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"{select}"
            f"$s.Rate = {int(self._rate)};"
            f"$s.SetOutputToWaveFile('{out_path}');"
            f"$s.Speak('{escaped}');"
            "$s.Dispose();"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=SPEECH_TIMEOUT_SEC,
        )
        if result.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(
                f"speech synthesis failed: {(result.stderr or '').strip()[:300]}"
            )
        return _wav_duration(out_path)


def _wav_duration(path: str) -> float:
    # Measured from the frames rather than the header count: a streaming
    # producer writes a sentinel there, and a wrong length here is silently
    # wrong rather than loudly wrong.
    return wav_seconds(path)


def read_all_frames(handle: "wave.Wave_read") -> bytes:
    """Every frame in a WAV, however wrong its header is about the count.

    A streaming producer writes a sentinel frame count - OpenAI's speech
    endpoint sends 0x7FFFFFFF - because it does not know the length when the
    header goes out. Trusting that number made a six-second line measure as
    twenty-four hours, which then reports as an overrun on every shot and
    sizes the mix canvas from something nothing on the timeline can match.
    Reading in chunks to EOF is correct for an honest header too.
    """
    chunks: list[bytes] = []
    while True:
        chunk = handle.readframes(4096)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def wav_seconds(path: str) -> float:
    """How long a WAV really runs, measured from its frames."""
    with wave.open(path, "rb") as handle:
        rate = handle.getframerate() or SAMPLE_RATE
        width = handle.getsampwidth() or 2
        channels = handle.getnchannels() or 1
        raw = read_all_frames(handle)
    return len(raw) / float(rate * width * channels)


def read_mono(path: str) -> array.array:
    """The samples in a WAV, for asserting on what was actually written."""
    with wave.open(path, "rb") as handle:
        raw = read_all_frames(handle)
    samples = array.array("h")
    samples.frombytes(raw)
    return samples


def _load_resampled(path: str) -> array.array:
    """One line's samples as mono 16-bit at ``SAMPLE_RATE``.

    Platform voices do not all agree on rate or channel count, and a mismatch
    would place the line at the wrong speed rather than fail loudly.
    """
    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = read_all_frames(handle)
    if width != 2:
        raise RuntimeError(f"expected 16-bit speech, got {width * 8}-bit")
    samples = array.array("h")
    samples.frombytes(raw)
    if channels > 1:
        samples = array.array("h", samples[::channels])
    if rate != SAMPLE_RATE and rate > 0:
        ratio = SAMPLE_RATE / rate
        resampled = array.array("h", bytes(2 * int(len(samples) * ratio)))
        for index in range(len(resampled)):
            source = int(index / ratio)
            resampled[index] = samples[source] if source < len(samples) else 0
        samples = resampled
    return samples


def build_track(
    cues: list[NarrationCue],
    out_path: str,
    *,
    voice: Voice | None = None,
) -> NarrationTrack | None:
    """Write one WAV spanning the film, with each line at its own start.

    Returns None when there is nothing to say: an entirely silent track would
    make the render mix a stream nobody wrote and report a narration that does
    not exist.
    """
    speakable = [cue for cue in cues if (cue.text or "").strip()]
    if not speakable:
        return None

    voice = voice or WindowsSapiVoice()
    program_sec = max(cue.end_sec for cue in cues)
    total_samples = int(program_sec * SAMPLE_RATE)
    canvas = array.array("h", bytes(2 * total_samples))

    overruns: list[str] = []
    overrun_sec: list[float] = []
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="cas-narration-") as work_dir:
        for index, cue in enumerate(speakable):
            text = cue.text.strip()
            clip_path = os.path.join(work_dir, f"line-{index:03d}.wav")
            try:
                spoken_sec = voice.speak(text, clip_path)
                samples = _load_resampled(clip_path)
            except Exception as exc:
                logger.warning("Narration line %d failed: %s", index + 1, exc)
                failures.append(f"{text[:60]} ({exc})")
                continue

            available = max(0.0, cue.end_sec - cue.start_sec)
            if spoken_sec > available + 0.25:
                overruns.append(text)
                overrun_sec.append(round(spoken_sec - available, 2))

            offset = int(cue.start_sec * SAMPLE_RATE)
            for position, value in enumerate(samples):
                target = offset + position
                if target >= total_samples:
                    # The last line may run past the final shot; the track is
                    # grown rather than the word cut off mid-syllable.
                    canvas.extend(array.array("h", bytes(2 * (target - total_samples + 1))))
                    total_samples = len(canvas)
                mixed = canvas[target] + value
                canvas[target] = max(-32768, min(32767, mixed))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with wave.open(out_path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(canvas.tobytes())

    return NarrationTrack(
        path=out_path,
        duration_sec=len(canvas) / float(SAMPLE_RATE),
        overruns=overruns,
        overrun_sec=overrun_sec,
        failures=failures,
    )


def cues_for_project(db: Session, project_id: str) -> list[NarrationCue]:
    """The film's lines, in program order, from the timeline it will render.

    Read from the timeline rather than from shot order so the narration
    matches the cut that is actually being assembled, including any shot the
    timeline leaves out.
    """
    from app.models import Shot, TimelineItem

    items = (
        db.query(TimelineItem)
        .filter(TimelineItem.project_id == project_id)
        .order_by(TimelineItem.order)
        .all()
    )
    cues: list[NarrationCue] = []
    elapsed = 0.0
    for item in items:
        duration = float(item.duration_sec or 0.0)
        shot = db.query(Shot).filter(Shot.id == item.shot_id).first()
        text = str(getattr(shot, DIALOGUE_FIELD, "") or "") if shot else ""
        cues.append(NarrationCue(start_sec=elapsed, end_sec=elapsed + duration, text=text))
        elapsed += duration
    return cues


def describe(track: NarrationTrack | None) -> dict[str, Any]:
    """What the render should record about the narration it carries."""
    if track is None:
        return {"present": False}
    return {
        "present": True,
        "duration_sec": round(track.duration_sec, 3),
        "overruns": track.overruns,
        "failures": track.failures,
    }
