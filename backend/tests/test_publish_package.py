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

import pytest

from app import paths


PASSING = {
    "hook_strength": 8, "story_clarity": 9, "visual_realism": 8,
    "world_consistency": 9, "character_consistency": 8, "ai_artifact": 8,
    "pacing": 8, "ending": 9, "audio": 7,
}


def _write_render(project_id: str) -> str:
    directory = paths.exports_dir(project_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "review.mp4")
    with open(path, "wb") as handle:
        handle.write(b"\x00" * 4096)
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


def test_an_unknown_project_is_a_404(client):
    assert client.get("/api/projects/nope/publish-package").status_code == 404
