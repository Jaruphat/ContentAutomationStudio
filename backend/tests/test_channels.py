"""A channel is the thing that outlives an episode.

The application's top object was a project, and a project is one film. That is
the right shape for making a film and the wrong shape for running a channel:
the house look, the negative prompt, the narrator, the audience and the content
pillars are the same for every episode, and re-entering them per episode is
both tedious and the way a channel stops looking like one channel. Nine pilot
episodes meant typing the same visual bible nine times and hoping it matched.

So a channel owns what recurs, an episode belongs to a channel, and starting an
episode copies the bibles into it.

**Copied, not referenced.** An episode that read its style live would change
retroactively when the channel's look was revised - and a delivered film whose
recorded style no longer matches the file cannot be checked against anything.
The copy is what makes an episode reproducible; the channel is what makes the
next one consistent.

The pillar, hook and ending are recorded on the episode as plain vocabulary
because they are what the analytics loop will later group by. Recording them
after the fact is not possible: nobody remembers which of nine hooks a video
used once it has been published for a month.
"""

import pytest

from app.services import channels


# ---------------------------------------------------------------------------
# The channel itself
# ---------------------------------------------------------------------------

def test_a_channel_holds_the_things_that_repeat(client):
    created = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "tagline": "Stories from worlds that shouldn't exist.",
        "audience": "English-first, global, 18-34",
        "visual_style": "Cinematic documentary realism, muted tones.",
        "negative_prompt": "cyberpunk, neon, glossy skin, AI art aesthetic",
        "voice_direction": "Calm male documentary narrator, ~150 WPM.",
    })

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "ODDVERSE"
    assert body["negative_prompt"].startswith("cyberpunk")


def test_a_channel_needs_a_name(client):
    """An unnamed channel cannot be picked from a list, which is the only way
    a second one is ever useful."""
    assert client.post("/api/channels", json={"name": "  "}).status_code == 422


def test_pillars_are_the_channel_s_own_vocabulary(client):
    """They differ per channel and drive what gets compared later, so they are
    data on the channel and not an enum in the code."""
    created = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "pillars": [
            {"key": "strange_files", "name": "STRANGE FILES", "share": 40,
             "purpose": "Mystery or anomaly in the present-day world"},
            {"key": "what_if", "name": "WHAT IF", "share": 30,
             "purpose": "Impossible scenario with a visual consequence"},
            {"key": "tomorrow", "name": "TOMORROW", "share": 30,
             "purpose": "Future micro-fiction"},
        ],
    }).json()

    assert [p["key"] for p in created["pillars"]] == [
        "strange_files", "what_if", "tomorrow",
    ]


def test_hooks_are_the_channel_s_own_vocabulary_too(client):
    created = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "hooks": [
            {"key": "H01", "name": "Impossible Event",
             "example": "At exactly 3:17 AM, a train arrives here."},
            {"key": "H02", "name": "What If",
             "example": "What if gravity disappeared for ten seconds?"},
        ],
    }).json()

    assert created["hooks"][0]["key"] == "H01"


def test_a_channel_can_be_edited_without_touching_its_episodes(
    client, db_session,
):
    """Revising the look is what a channel is for. It must not reach back into
    films that were already delivered under the old one."""
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE", "visual_style": "muted documentary realism",
    }).json()
    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train",
    }).json()

    client.put(f"/api/channels/{channel['id']}", json={
        "visual_style": "high-contrast neon",
    })

    styles = client.get(f"/api/projects/{episode['id']}/styles").json()
    assert "muted documentary realism" in styles[0]["visual_keywords"]
    assert "neon" not in styles[0]["visual_keywords"]


# ---------------------------------------------------------------------------
# Starting an episode
# ---------------------------------------------------------------------------

def test_starting_an_episode_copies_the_bibles_into_it(client):
    """This is the whole point. Nine episodes should not mean typing one
    visual bible nine times and hoping it matched."""
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "visual_style": "Cinematic documentary realism, muted neutral tones.",
        "negative_prompt": "cyberpunk, neon, glossy skin",
        "aspect_ratio": "9:16",
        "target_resolution": "1080x1920",
        "frame_rate": 30.0,
    }).json()

    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train",
    })

    assert episode.status_code == 201, episode.text
    body = episode.json()
    assert body["aspect_ratio"] == "9:16"
    assert body["target_resolution"] == "1080x1920"
    assert body["frame_rate"] == 30.0

    styles = client.get(f"/api/projects/{body['id']}/styles").json()
    assert len(styles) == 1
    assert "documentary realism" in styles[0]["visual_keywords"]
    assert "cyberpunk" in styles[0]["negative_constraints"]


def test_an_episode_records_which_channel_it_belongs_to(client):
    channel = client.post("/api/channels", json={"name": "ODDVERSE"}).json()

    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train",
    }).json()

    assert episode["channel_id"] == channel["id"]
    listed = client.get(f"/api/channels/{channel['id']}/episodes").json()
    assert [e["id"] for e in listed] == [episode["id"]]


def test_an_episode_records_the_vocabulary_the_analytics_loop_needs(client):
    """Recorded when the episode is made, because nobody remembers which of
    nine hooks a video used once it has been live for a month."""
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "pillars": [{"key": "strange_files", "name": "STRANGE FILES"}],
        "hooks": [{"key": "H01", "name": "Impossible Event"}],
    }).json()

    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train",
        "pillar": "strange_files",
        "hook_type": "H01",
        "ending_type": "twist",
        "premise": "A train that arrives at an abandoned station every night.",
    }).json()

    assert episode["pillar"] == "strange_files"
    assert episode["hook_type"] == "H01"
    assert episode["ending_type"] == "twist"
    assert episode["premise"].startswith("A train")


def test_a_pillar_the_channel_does_not_have_is_refused(client):
    """A typo here is invisible until the analytics grouping comes back with
    a category of one."""
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "pillars": [{"key": "strange_files", "name": "STRANGE FILES"}],
    }).json()

    response = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train", "pillar": "strange_flies",
    })

    assert response.status_code == 422
    assert "strange_flies" in response.text


def test_a_hook_the_channel_does_not_have_is_refused(client):
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "hooks": [{"key": "H01", "name": "Impossible Event"}],
    }).json()

    response = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train", "hook_type": "H99",
    })

    assert response.status_code == 422


def test_an_episode_of_a_channel_with_no_bibles_is_still_an_ordinary_project(
    client,
):
    """A channel started before its look is decided must not block work."""
    channel = client.post("/api/channels", json={"name": "New thing"}).json()

    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "Pilot",
    })

    assert episode.status_code == 201, episode.text
    assert client.get(f"/api/projects/{episode.json()['id']}/styles").json() == []


def test_episodes_of_an_unknown_channel_are_a_404(client):
    assert client.post("/api/channels/nope/episodes", json={
        "title": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def test_deleting_a_channel_does_not_delete_the_films_made_under_it(
    client, db_session,
):
    """A delivered episode is a thing that exists in the world. Losing nine of
    them because a channel was renamed by deletion would be unrecoverable."""
    channel = client.post("/api/channels", json={"name": "ODDVERSE"}).json()
    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "The 3:17 Train",
    }).json()

    deleted = client.delete(f"/api/channels/{channel['id']}")
    assert deleted.status_code in (204, 409), deleted.text

    if deleted.status_code == 204:
        still_there = client.get(f"/api/projects/{episode['id']}")
        assert still_there.status_code == 200
        assert still_there.json()["channel_id"] is None


# ---------------------------------------------------------------------------
# The service, directly
# ---------------------------------------------------------------------------

def test_the_seeded_style_is_named_after_the_channel(db_session, client):
    """A project's style list is flat and its rows have no name field, so the
    medium carries the attribution - otherwise nobody can tell where a style
    came from once a project has two."""
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE", "visual_style": "muted realism",
    }).json()
    episode = client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": "Pilot",
    }).json()

    styles = client.get(f"/api/projects/{episode['id']}/styles").json()
    assert "ODDVERSE" in styles[0]["medium"]


def test_validation_errors_name_what_was_offered(db_session):
    """The message has to carry the vocabulary, or the fix is a guess."""
    with pytest.raises(channels.ChannelError) as exc:
        channels.validate_vocabulary(
            pillars=[{"key": "strange_files", "name": "STRANGE FILES"}],
            hooks=[],
            pillar="what_if",
            hook_type="",
        )
    assert "strange_files" in str(exc.value)
