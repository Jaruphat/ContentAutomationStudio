"""Everything needed to upload, in one place, with the gate in front of it.

The pipeline ended at a rendered MP4 and a pile of manifests. Uploading meant
finding the file, writing a title somewhere else, remembering the series label,
copying the hashtags from a document, and grabbing a thumbnail by scrubbing.
Every one of those is a place to publish the wrong thing.

The package is that list assembled once, with the publish gate in front of it.
Two rules make it worth having rather than a folder of conventions:

* **Not ready is the default, and it says why.** No render, a render older than
  the cut, or a quality review that has not passed - each is named. A package
  that reports ready when it is not is worse than no package, because it is
  believed.
* **Nothing is invented.** A missing title is a missing title, not the
  project's working name quietly promoted into the world.
"""

import os
from pathlib import Path
from functools import lru_cache

import pytest

from app import paths
from app.services import media_probe


PASSING = {
    "hook_strength": 8, "story_clarity": 9, "visual_realism": 8,
    "world_consistency": 9, "character_consistency": 8, "ai_artifact": 8,
    "pacing": 8, "ending": 9, "audio": 7,
}


@lru_cache(maxsize=1)
def _video_bytes() -> bytes:
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        target = str(Path(folder) / "fixture.mp4")
        ffmpeg = media_probe.ffmpeg_path()
        if not ffmpeg:
            pytest.skip("ffmpeg is required for publish validation")
        code, _, error = media_probe.run_captured([
            ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=s=64x64:d=0.2",
            "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", target,
        ], timeout=30)
        assert code == 0, error
        return Path(target).read_bytes()


def _write_render(project_id: str) -> str:
    directory = paths.exports_dir(project_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "review.mp4")
    with open(path, "wb") as handle:
        handle.write(_video_bytes())
    return path


def _pass_the_gate(client, project_id):
    client.post(f"/api/projects/{project_id}/quality-review", json={
        "scores": PASSING, "ai_tell": False,
    })


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_a_project_with_nothing_done_is_not_ready_and_says_why(
    client, sample_project,
):
    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["ready"] is False
    joined = " ".join(body["blockers"]).lower()
    assert "render" in joined
    assert "quality" in joined or "review" in joined


def test_a_rendered_but_unreviewed_episode_is_not_ready(client, sample_project):
    """The gate exists to be in the way here. A film that renders is not a
    film somebody has watched."""
    _write_render(sample_project.id)

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["ready"] is False
    assert any("review" in b.lower() for b in body["blockers"])


def test_a_failed_review_blocks_and_carries_its_reasons_forward(
    client, sample_project,
):
    """The blockers must say what fell short, not that something did."""
    _write_render(sample_project.id)
    client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": {**PASSING, "character_consistency": 4}, "ai_tell": False,
    })

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["ready"] is False
    assert any("character consistency" in b.lower() for b in body["blockers"])


def test_a_rendered_and_passed_episode_is_ready(client, sample_project):
    _write_render(sample_project.id)
    _pass_the_gate(client, sample_project.id)

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["ready"] is True, body["blockers"]
    assert body["blockers"] == []


def test_replacing_video_invalidates_review_even_if_timestamp_is_restored(client, sample_project):
    filename = _write_render(sample_project.id)
    _pass_the_gate(client, sample_project.id)
    timestamp = os.path.getmtime(filename)
    with open(filename, "ab") as stream:
        stream.write(b"different render")
    os.utime(filename, (timestamp, timestamp))
    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()
    assert not body["ready"] and not body["quality_passed"]
    assert any("identify this video" in reason for reason in body["blockers"])


def test_review_before_render_cannot_approve_future_video(client, sample_project):
    _pass_the_gate(client, sample_project.id)
    _write_render(sample_project.id)
    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()
    assert not body["ready"]


def test_corrupt_video_cannot_pass_even_with_a_quality_score(client, sample_project):
    filename = _write_render(sample_project.id)
    Path(filename).write_bytes(b"broken media")
    _pass_the_gate(client, sample_project.id)
    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()
    assert not body["ready"]
    assert any("readable video" in reason for reason in body["blockers"])


# ---------------------------------------------------------------------------
# The contents
# ---------------------------------------------------------------------------

def test_the_package_carries_what_an_upload_form_asks_for(
    client, db_session, sample_project,
):
    _write_render(sample_project.id)
    _pass_the_gate(client, sample_project.id)
    client.put(f"/api/projects/{sample_project.id}/publish", json={
        "publish_title": "A Train Arrives Here Every Night at 3:17 AM",
        "series_label": "STRANGE FILE #001 | ODDVERSE",
        "publish_description": "A train. An abandoned station.",
        "publish_hashtags": "#shorts #mystery #scifi",
    })

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["publish_title"].startswith("A Train Arrives")
    assert body["series_label"] == "STRANGE FILE #001 | ODDVERSE"
    assert body["publish_hashtags"] == "#shorts #mystery #scifi"
    assert body["video_url"].endswith("/render/file")


def test_a_missing_title_is_missing_rather_than_the_working_name(
    client, sample_project,
):
    """The project title is a working name. Promoting it into the world
    silently is how an episode goes out called "Untitled 3"."""
    _write_render(sample_project.id)
    _pass_the_gate(client, sample_project.id)

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["publish_title"] == ""
    assert any("title" in warning.lower() for warning in body["warnings"])


def test_the_package_reports_the_episode_vocabulary_it_will_be_measured_by(
    client,
):
    """Published without the pillar and hook recorded, the episode cannot be
    read against anything afterwards - and afterwards is too late."""
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "pillars": [{"key": "strange_files", "name": "STRANGE FILES"}],
        "hooks": [{"key": "H01", "name": "Impossible Event"}],
    }).json()
    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train", "pillar": "strange_files", "hook_type": "H01",
    }).json()
    _write_render(episode["id"])
    _pass_the_gate(client, episode["id"])

    body = client.get(f"/api/projects/{episode['id']}/publish-package").json()

    assert body["pillar"] == "strange_files"
    assert body["hook_type"] == "H01"


def test_an_episode_with_no_pillar_is_warned_but_not_blocked(
    client, sample_project,
):
    """Publishing an unclassified episode is a real choice; losing the ability
    to compare it is the cost, and the cost is stated rather than enforced."""
    _write_render(sample_project.id)
    _pass_the_gate(client, sample_project.id)

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()

    assert body["ready"] is True
    assert any("pillar" in warning.lower() for warning in body["warnings"])


def test_publishing_fields_are_kept_on_the_project(client, sample_project):
    client.put(f"/api/projects/{sample_project.id}/publish", json={
        "publish_title": "A Train Arrives Here Every Night at 3:17 AM",
    })

    body = client.get(f"/api/projects/{sample_project.id}/publish-package").json()
    assert body["publish_title"].startswith("A Train Arrives")


@pytest.mark.parametrize("change", [{"audio_gain_db": -6}, {"audio_mode": "mute"}])
def test_clip_audio_change_requires_a_new_render_but_same_value_does_not(
    client, db_session, sample_project, sample_shot, change,
):
    from app.models import GenerationJob, TimelineItem

    item = TimelineItem(project_id=sample_project.id, shot_id=sample_shot.id)
    db_session.add(item)
    db_session.commit()
    _write_render(sample_project.id)
    _pass_the_gate(client, sample_project.id)
    package_url = f"/api/projects/{sample_project.id}/publish-package"
    shot_url = f"/api/projects/{sample_project.id}/scenes/{sample_shot.scene_id}/shots/{sample_shot.id}"
    assert client.get(package_url).json()["ready"]
    assert client.put(shot_url, json={"audio_mode": "native", "audio_gain_db": 0}).status_code == 200
    assert client.get(package_url).json()["ready"]

    assert client.put(shot_url, json=change).status_code == 200
    package = client.get(package_url).json()
    assert not package["ready"]
    assert any("timeline changed" in reason for reason in package["blockers"])
    assert db_session.query(GenerationJob).count() == 0


def test_an_unknown_project_is_a_404(client):
    assert client.get("/api/projects/nope/publish-package").status_code == 404
