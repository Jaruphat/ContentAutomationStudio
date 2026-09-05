"""Watching the finished film in the application that made it.

Everything up to here is reviewable in the browser except the one thing the
whole pipeline exists to produce. Render Review wrote an MP4 and returned an
absolute Windows path, so the only way to see the result was to leave the app,
find the file and open it in something else - and the path was gone from the
screen on the next reload.

Two pieces fix that, and the second is the one that matters:

* The render is at a known place per project, so "is there a finished film?"
  is a question the page can ask on load rather than something only the
  response to a render knew.
* The bytes are served with HTTP range support. Without it a browser can only
  play a video from the start: the seek bar moves and nothing happens. Nobody
  reviews a three-minute film without scrubbing it.
"""

import os

from app import paths


def _write_render(project_id: str, data: bytes) -> str:
    directory = paths.exports_dir(project_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "review.mp4")
    with open(path, "wb") as f:
        f.write(data)
    return path


# ---------------------------------------------------------------------------
# Finding it
# ---------------------------------------------------------------------------

def test_a_project_with_no_render_says_so_rather_than_404(client, sample_project):
    """A project that has not been rendered yet is a normal state, not an
    error. Answering with 404 would make the page show a failure to somebody
    who has simply not pressed the button."""
    body = client.get(f"/api/projects/{sample_project.id}/render/latest").json()

    assert body["rendered"] is False
    assert body["url"] == ""
    assert body["reason"]


def test_a_rendered_film_is_reported_with_what_it_takes_to_play_it(
    client, sample_project,
):
    _write_render(sample_project.id, b"\x00" * 2048)

    body = client.get(f"/api/projects/{sample_project.id}/render/latest").json()

    assert body["rendered"] is True
    assert body["size_bytes"] == 2048
    assert body["url"].endswith(f"/api/projects/{sample_project.id}/render/file")
    assert body["rendered_at"], "the page has to be able to say how old it is"


def test_an_unknown_project_is_still_a_404(client):
    assert client.get("/api/projects/nope/render/latest").status_code == 404


# ---------------------------------------------------------------------------
# Playing it
# ---------------------------------------------------------------------------

def test_the_whole_file_is_served_and_advertises_range_support(
    client, sample_project,
):
    """A player decides whether it can seek from this header alone."""
    _write_render(sample_project.id, b"abcdefghij")

    response = client.get(f"/api/projects/{sample_project.id}/render/file")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == b"abcdefghij"
    assert response.headers["content-type"] == "video/mp4"


def test_a_range_request_returns_exactly_that_slice(client, sample_project):
    """This is what a seek is. Returning the whole file with 200 makes the
    seek bar move while the picture stays where it was."""
    _write_render(sample_project.id, b"abcdefghij")

    response = client.get(
        f"/api/projects/{sample_project.id}/render/file",
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 206
    assert response.content == b"cdef"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"


def test_an_open_ended_range_runs_to_the_end_of_the_file(client, sample_project):
    """The form browsers actually send first: "bytes=0-" to start playback."""
    _write_render(sample_project.id, b"abcdefghij")

    response = client.get(
        f"/api/projects/{sample_project.id}/render/file",
        headers={"Range": "bytes=6-"},
    )

    assert response.status_code == 206
    assert response.content == b"ghij"
    assert response.headers["content-range"] == "bytes 6-9/10"


def test_a_range_past_the_end_is_refused_with_the_real_length(
    client, sample_project,
):
    """416 carrying the true size is how a player recovers; a truncated 206
    would leave it decoding bytes that are not there."""
    _write_render(sample_project.id, b"abcdefghij")

    response = client.get(
        f"/api/projects/{sample_project.id}/render/file",
        headers={"Range": "bytes=50-60"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


def test_an_unsatisfiable_unit_falls_back_to_the_whole_file(
    client, sample_project,
):
    """A header this endpoint does not understand must not fail the request -
    the file still plays, it just cannot be seeked."""
    _write_render(sample_project.id, b"abcdefghij")

    response = client.get(
        f"/api/projects/{sample_project.id}/render/file",
        headers={"Range": "items=0-1"},
    )

    assert response.status_code == 200
    assert response.content == b"abcdefghij"


def test_playing_a_film_that_was_never_rendered_is_a_404(client, sample_project):
    response = client.get(f"/api/projects/{sample_project.id}/render/file")
    assert response.status_code == 404
    assert "render" in response.text.lower()


# ---------------------------------------------------------------------------
# The same seeking for a single take
# ---------------------------------------------------------------------------

def test_take_media_is_seekable_too(client, db_session, sample_shot, tmp_path):
    """Reviewing one eight-second clip needs scrubbing as much as the film
    does, and it was served the same way."""
    from app.models import Take
    import uuid

    directory = paths.exports_dir("takes-probe")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "clip.mp4")
    with open(path, "wb") as f:
        f.write(b"0123456789")
    take = Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=path,
        review_status="Pending", width=64, height=64,
    )
    db_session.add(take)
    db_session.commit()

    response = client.get(
        f"/api/media/takes/{take.id}/file", headers={"Range": "bytes=1-3"},
    )

    assert response.status_code == 206
    assert response.content == b"123"
