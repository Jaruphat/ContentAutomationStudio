"""What the audience did, joined to what we chose.

Producing nine pilots is only an experiment if the results can be read against
the decisions. That means two things the application did not have: somewhere to
put the numbers a platform reports, and a comparison that groups episodes by
the choices that varied - pillar, hook, ending, length - rather than by title.

The hard part is not the arithmetic. It is refusing to answer.

Three episodes per pillar cannot tell you which pillar wins. Neither can nine
episodes when eight of them are unpublished. A comparison that ranks anyway
produces a winner, the winner gets scaled, and a month of work follows a number
that was noise. So the comparison reports what it has, states the sample it had
it from, and declines to name a winner it cannot support - which is the only
part of this that changes what somebody does on Monday.
"""

import pytest

from app.services import analytics


def _channel(client, **over):
    body = {
        "name": "ODDVERSE",
        "pillars": [
            {"key": "strange_files", "name": "STRANGE FILES"},
            {"key": "what_if", "name": "WHAT IF"},
        ],
        "hooks": [
            {"key": "H01", "name": "Impossible Event"},
            {"key": "H02", "name": "What If"},
        ],
        **over,
    }
    return client.post("/api/channels", json=body).json()


def _episode(client, channel, title, pillar="strange_files", hook="H01"):
    return client.post(f"/api/channels/{channel['id']}/episodes", json={
        "title": title, "pillar": pillar, "hook_type": hook,
        "ending_type": "twist",
    }).json()


def _record(client, episode, **metrics):
    payload = {"source": "manual", **metrics}
    return client.post(f"/api/projects/{episode['id']}/analytics", json=payload)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def test_numbers_are_recorded_against_the_episode(client):
    channel = _channel(client)
    episode = _episode(client, channel, "The 3:17 Train")

    response = _record(
        client, episode, views_24h=1200, avg_percent_viewed=64.2,
        engaged_views=430, likes=88,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["views_24h"] == 1200
    assert body["avg_percent_viewed"] == pytest.approx(64.2)


def test_every_capture_is_kept_so_a_number_can_be_watched_move(client):
    """A single snapshot cannot distinguish a video that died at 200 views
    from one on its way to 20,000."""
    channel = _channel(client)
    episode = _episode(client, channel, "The 3:17 Train")

    _record(client, episode, views_24h=1200)
    _record(client, episode, views_7d=9400)

    history = client.get(f"/api/projects/{episode['id']}/analytics").json()
    assert len(history) == 2


def test_the_latest_capture_is_what_a_comparison_uses(client):
    """Two snapshots of one episode must not count as two episodes."""
    channel = _channel(client)
    episode = _episode(client, channel, "The 3:17 Train")
    _record(client, episode, avg_percent_viewed=40.0)
    _record(client, episode, avg_percent_viewed=61.0)

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["episodes"][0]["avg_percent_viewed"] == pytest.approx(61.0)
    assert report["episode_count"] == 1


def test_a_percentage_outside_the_scale_is_refused(client):
    """A field the platform reports as a percentage, pasted as a fraction, is
    the difference between 6% and 60% retention."""
    channel = _channel(client)
    episode = _episode(client, channel, "The 3:17 Train")

    response = _record(client, episode, avg_percent_viewed=640.0)

    assert response.status_code == 422, response.text


def test_a_negative_count_is_refused(client):
    channel = _channel(client)
    episode = _episode(client, channel, "x")
    assert _record(client, episode, views_24h=-5).status_code == 422


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------

def test_episodes_are_grouped_by_the_choices_that_varied(client):
    channel = _channel(client)
    a = _episode(client, channel, "A", pillar="strange_files", hook="H01")
    b = _episode(client, channel, "B", pillar="what_if", hook="H02")
    _record(client, a, avg_percent_viewed=70.0, views_24h=1000)
    _record(client, b, avg_percent_viewed=40.0, views_24h=1000)

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    by_pillar = {g["value"]: g for g in report["groups"]["pillar"]}
    assert by_pillar["strange_files"]["avg_percent_viewed"] == pytest.approx(70.0)
    assert by_pillar["what_if"]["avg_percent_viewed"] == pytest.approx(40.0)


def test_a_group_of_one_is_not_called_a_winner(client):
    """One episode per pillar is an anecdote. Ranking it produces a winner,
    the winner gets scaled, and a month follows a number that was noise."""
    channel = _channel(client)
    a = _episode(client, channel, "A", pillar="strange_files")
    b = _episode(client, channel, "B", pillar="what_if", hook="H02")
    _record(client, a, avg_percent_viewed=70.0)
    _record(client, b, avg_percent_viewed=40.0)

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["winner"]["pillar"] is None
    assert "enough" in report["winner"]["reason"].lower()


def test_a_winner_is_named_once_there_is_enough_to_name_one(client):
    channel = _channel(client)
    for index in range(analytics.MIN_GROUP_SIZE):
        episode = _episode(client, channel, f"SF{index}", pillar="strange_files")
        _record(client, episode, avg_percent_viewed=72.0)
    for index in range(analytics.MIN_GROUP_SIZE):
        episode = _episode(client, channel, f"WI{index}", pillar="what_if",
                           hook="H02")
        _record(client, episode, avg_percent_viewed=38.0)

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["winner"]["pillar"] == "strange_files"
    assert report["winner"]["sample_size"] == analytics.MIN_GROUP_SIZE


def test_a_tie_is_reported_as_a_tie_rather_than_broken_arbitrarily(client):
    """Ordering by id is still an answer, and it is the wrong one to act on."""
    channel = _channel(client)
    for index in range(analytics.MIN_GROUP_SIZE):
        a = _episode(client, channel, f"SF{index}", pillar="strange_files")
        b = _episode(client, channel, f"WI{index}", pillar="what_if", hook="H02")
        _record(client, a, avg_percent_viewed=55.0)
        _record(client, b, avg_percent_viewed=55.0)

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["winner"]["pillar"] is None
    assert "tie" in report["winner"]["reason"].lower()


def test_an_episode_with_no_numbers_is_counted_as_unmeasured_not_as_zero(
    client,
):
    """Counting an unpublished episode as zero retention drags its whole
    group down and buries the format that was actually working."""
    channel = _channel(client)
    measured = _episode(client, channel, "Published")
    _episode(client, channel, "Not published yet")
    _record(client, measured, avg_percent_viewed=70.0)

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["episode_count"] == 1
    assert report["unmeasured_count"] == 1
    by_pillar = {g["value"]: g for g in report["groups"]["pillar"]}
    assert by_pillar["strange_files"]["avg_percent_viewed"] == pytest.approx(70.0)


def test_a_channel_with_nothing_measured_says_so(client):
    channel = _channel(client)
    _episode(client, channel, "Not published yet")

    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["episode_count"] == 0
    assert report["winner"]["pillar"] is None
    assert report["groups"]["pillar"] == []


def test_the_report_names_the_metric_it_ranked_on(client):
    """Views and retention disagree constantly, and a ranking that does not
    say which it used cannot be argued with."""
    channel = _channel(client)
    report = client.get(f"/api/channels/{channel['id']}/analytics").json()

    assert report["ranked_on"] == analytics.RANKING_METRIC


# ---------------------------------------------------------------------------
# The service, directly
# ---------------------------------------------------------------------------

def test_grouping_ignores_a_dimension_nobody_filled_in():
    """A blank ending type across every episode is not a group of nine, it is
    a dimension nobody recorded."""
    rows = [
        {"pillar": "strange_files", "hook_type": "H01", "ending_type": "",
         "avg_percent_viewed": 70.0},
        {"pillar": "strange_files", "hook_type": "H01", "ending_type": "",
         "avg_percent_viewed": 60.0},
    ]

    groups = analytics.group_by(rows, "ending_type")

    assert groups == []
