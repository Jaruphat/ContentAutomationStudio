"""Hearing a narrator before a film commits to it.

Choosing a voice from a list of names is choosing blind. NORI EP001 was
re-read, re-cut and re-rendered twice to find out that the voice picked from
the list was barely different from the one before it - about twenty minutes and
a metered synthesis of the whole script, to answer a question one sentence
would have answered.

So: one line, the voice being considered, and the direction the film would
actually give it - because the direction is what carries age and energy, and a
preview that skipped it would be auditioning the wrong thing.
"""

import array
import io
import json
import math
import wave

import httpx
import pytest

from app.models import Channel, Project, Scene, Shot


def _wav_bytes(seconds: float = 0.5, rate: int = 24000) -> bytes:
    samples = array.array(
        "h",
        (
            int(9000 * math.sin(2 * math.pi * 220 * n / rate))
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
    """Stands in for the speech endpoint and remembers what it was asked."""

    def __init__(self):
        self.requests: list[dict] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(request.content.decode()))
            return httpx.Response(200, content=_wav_bytes())

        return httpx.MockTransport(handle)


@pytest.fixture()
def recorder(monkeypatch):
    """Every voice the router builds speaks to the recorder, not to OpenAI."""
    from app.services import openai_voice

    rec = _Recorder()
    real = openai_voice.OpenAIVoice

    def build(**kwargs):
        kwargs.setdefault("api_key", "sk-test")
        kwargs.setdefault("transport", rec.transport())
        return real(**kwargs)

    monkeypatch.setattr(openai_voice, "OpenAIVoice", build)
    return rec


def _project(db_session, **over) -> Project:
    project = Project(title="NORI", **over)
    db_session.add(project)
    db_session.commit()
    return project


def _with_line(db_session, project: Project, line: str) -> None:
    scene = Scene(project_id=project.id, title="One", order=1)
    db_session.add(scene)
    db_session.flush()
    shot = Shot(scene_id=scene.id, order=1, dialogue=line)
    db_session.add(shot)
    db_session.commit()


def test_it_speaks_the_chosen_voice(client, db_session, recorder):
    project = _project(db_session)

    response = client.post(
        f"/api/projects/{project.id}/narration/preview",
        json={"voice": "nova", "confirm_paid_generation": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
    assert response.headers["x-narration-voice"] == "nova"
    assert recorder.requests[0]["voice"] == "nova"


def test_it_auditions_on_the_film_s_own_opening_line(client, db_session, recorder):
    project = _project(db_session)
    _with_line(db_session, project, "I am a rice ball.")

    client.post(
        f"/api/projects/{project.id}/narration/preview",
        json={"voice": "ash", "confirm_paid_generation": True},
    )

    assert recorder.requests[0]["input"] == "I am a rice ball."


def test_it_carries_the_channel_s_direction(client, db_session, recorder):
    channel = Channel(name="Nori", voice_direction="Small cheerful character.")
    db_session.add(channel)
    db_session.commit()
    project = _project(db_session, channel_id=channel.id)

    client.post(
        f"/api/projects/{project.id}/narration/preview",
        json={"voice": "ash", "confirm_paid_generation": True},
    )

    # The direction is what carries age and energy. A preview without it would
    # audition a voice the film is never going to use.
    assert recorder.requests[0]["instructions"] == "Small cheerful character."


def test_a_given_direction_beats_the_channel_s(client, db_session, recorder):
    channel = Channel(name="Nori", voice_direction="Documentary narrator.")
    db_session.add(channel)
    db_session.commit()
    project = _project(db_session, channel_id=channel.id)

    client.post(
        f"/api/projects/{project.id}/narration/preview",
        json={
            "voice": "ash",
            "instructions": "Sound about eight years old.",
            "confirm_paid_generation": True,
        },
    )

    assert recorder.requests[0]["instructions"] == "Sound about eight years old."


def test_it_will_not_read_a_script_for_free(client, db_session, recorder):
    project = _project(db_session)
    long_line = "Rice and salt. " * 100

    client.post(
        f"/api/projects/{project.id}/narration/preview",
        json={
            "text": long_line,
            "confirm_paid_generation": True,
        },
    )

    # A preview is for hearing a voice, not for getting a whole script read a
    # sentence at a time through the audition button.
    assert len(recorder.requests[0]["input"]) <= 240


def test_it_refuses_until_the_spend_is_authorised(client, db_session, recorder):
    project = _project(db_session)

    response = client.post(
        f"/api/projects/{project.id}/narration/preview",
        json={"voice": "nova"},
    )

    assert response.status_code == 409
    assert "metered" in response.json()["detail"]
    assert recorder.requests == []


def test_it_is_404_for_a_project_that_does_not_exist(client, db_session, recorder):
    response = client.post(
        "/api/projects/nope/narration/preview",
        json={"confirm_paid_generation": True},
    )

    assert response.status_code == 404
