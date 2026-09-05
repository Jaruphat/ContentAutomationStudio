"""Choosing what to make, before spending an hour of GPU on it.

The blueprint's first step was a scoring exercise: nine niches rated on viral
potential, repeatability, fit with the tools to hand, story potential,
automation difficulty and policy risk, weighted, ranked, and the top three
taken forward. It was done once, in a document, and every premise since has
been chosen the way premises are usually chosen - whichever one was in mind
that morning.

The same rubric applied to premises, kept beside the channel it belongs to, is
worth more than the arithmetic suggests: it makes the choice comparable across
weeks, and it makes rejecting an idea cheap. An hour of GPU time follows every
premise that survives this screen.

One gate outranks the scores, exactly as the two-second question does at the
other end of the pipeline. The blueprint's story rule is that every episode
must answer, in one sentence, *what is the one strange thing?* A premise that
cannot is rejected before it is scored - because a premise that cannot answer
it does not become a better film with better production.
"""

import pytest

from app.services import premises


CANDIDATE = {
    "title": "The 3:17 Train",
    "logline": "A train arrives at an abandoned station every night at 3:17.",
    "one_strange_thing": "A train that should not exist keeps a timetable.",
    "pillar": "strange_files",
    "hook_type": "H01",
    "scores": {
        "viral_potential": 9, "repeatability": 8, "tool_fit": 9,
        "story_potential": 9, "automation_ease": 7, "policy_safety": 9,
    },
}


# ---------------------------------------------------------------------------
# The rubric
# ---------------------------------------------------------------------------

def test_every_criterion_is_weighted_and_the_weights_sum_to_one():
    """An unweighted rubric ranks a premise that is easy to automate above one
    anybody would watch."""
    assert sum(c.weight for c in premises.CRITERIA) == pytest.approx(1.0)


def test_every_criterion_says_what_it_is_asking():
    for criterion in premises.CRITERIA:
        assert len(criterion.question) > 25, criterion.key
        assert criterion.label.strip()


def test_the_criteria_are_the_blueprint_s_own():
    assert {c.key for c in premises.CRITERIA} == {
        "viral_potential", "repeatability", "tool_fit", "story_potential",
        "automation_ease", "policy_safety",
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_a_premise_scores_out_of_one_hundred():
    result = premises.score(CANDIDATE["scores"])
    assert 0 <= result.total <= 100
    assert result.total == pytest.approx(86.0, abs=2.0)


def test_a_premise_that_is_strong_everywhere_beats_one_that_is_not():
    weak = {key: 4 for key in CANDIDATE["scores"]}
    assert premises.score(CANDIDATE["scores"]).total > premises.score(weak).total


def test_an_unscored_criterion_is_refused_rather_than_counted_as_zero():
    """Counted as zero it drags a good premise below a mediocre one that was
    filled in completely; ignored, it flatters whoever skipped it."""
    partial = {k: v for k, v in CANDIDATE["scores"].items() if k != "tool_fit"}

    with pytest.raises(premises.PremiseError) as exc:
        premises.score(partial)
    assert "tool_fit" in str(exc.value)


def test_a_score_off_the_scale_is_refused():
    with pytest.raises(premises.PremiseError):
        premises.score({**CANDIDATE["scores"], "repeatability": 40})


def test_an_unknown_criterion_is_refused():
    with pytest.raises(premises.PremiseError) as exc:
        premises.score({**CANDIDATE["scores"], "vibes": 10})
    assert "vibes" in str(exc.value)


def test_the_result_names_the_weakest_criterion():
    """Ranking without saying where a premise is weak leaves nothing to fix."""
    scores = {**CANDIDATE["scores"], "repeatability": 2}

    result = premises.score(scores)

    assert result.weakest["key"] == "repeatability"


# ---------------------------------------------------------------------------
# The gate that outranks the scores
# ---------------------------------------------------------------------------

def test_a_premise_with_no_one_strange_thing_is_rejected_before_scoring(
    client,
):
    channel = client.post("/api/channels", json={
        "name": "ODDVERSE",
        "pillars": [{"key": "strange_files", "name": "STRANGE FILES"}],
        "hooks": [{"key": "H01", "name": "Impossible Event"}],
    }).json()

    response = client.post(f"/api/channels/{channel['id']}/premises", json={
        **CANDIDATE, "one_strange_thing": "   ",
    })

    assert response.status_code == 422, response.text
    assert "one strange thing" in response.text.lower()


def test_a_premise_whose_strange_thing_is_a_paragraph_is_rejected(client):
    """The rule is that it fits in one sentence. Two paragraphs mean the idea
    has not been found yet, and no amount of production rescues that."""
    channel = client.post("/api/channels", json={"name": "ODDVERSE"}).json()

    response = client.post(f"/api/channels/{channel['id']}/premises", json={
        **CANDIDATE, "pillar": "", "hook_type": "",
        "one_strange_thing": " ".join(["a very long explanation"] * 30),
    })

    assert response.status_code == 422
    assert "one sentence" in response.text.lower()


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------

def _channel(client):
    return client.post("/api/channels", json={
        "name": "ODDVERSE",
        "pillars": [{"key": "strange_files", "name": "STRANGE FILES"}],
        "hooks": [{"key": "H01", "name": "Impossible Event"}],
    }).json()


def test_a_scored_premise_is_kept_against_the_channel(client):
    channel = _channel(client)

    response = client.post(f"/api/channels/{channel['id']}/premises", json=CANDIDATE)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "The 3:17 Train"
    assert body["total"] == pytest.approx(86.0, abs=2.0)
    assert body["status"] == "candidate"


def test_candidates_come_back_ranked(client):
    channel = _channel(client)
    client.post(f"/api/channels/{channel['id']}/premises", json=CANDIDATE)
    client.post(f"/api/channels/{channel['id']}/premises", json={
        **CANDIDATE, "title": "A weaker idea",
        "scores": {key: 4 for key in CANDIDATE["scores"]},
    })

    listed = client.get(f"/api/channels/{channel['id']}/premises").json()

    assert [entry["title"] for entry in listed] == [
        "The 3:17 Train", "A weaker idea",
    ]


def test_a_pillar_the_channel_does_not_have_is_refused(client):
    channel = _channel(client)

    response = client.post(f"/api/channels/{channel['id']}/premises", json={
        **CANDIDATE, "pillar": "strange_flies",
    })

    assert response.status_code == 422


def test_a_chosen_premise_can_become_an_episode(client):
    """The point of scoring is what happens next. Retyping the premise into a
    new project is where the pillar and hook quietly stop matching."""
    channel = _channel(client)
    premise = client.post(
        f"/api/channels/{channel['id']}/premises", json=CANDIDATE
    ).json()

    response = client.post(
        f"/api/channels/{channel['id']}/premises/{premise['id']}/start"
    )

    assert response.status_code == 201, response.text
    episode = response.json()
    assert episode["title"] == "The 3:17 Train"
    assert episode["pillar"] == "strange_files"
    assert episode["hook_type"] == "H01"
    assert episode["premise"].startswith("A train arrives")

    after = client.get(f"/api/channels/{channel['id']}/premises").json()
    assert after[0]["status"] == "in_production"
    assert after[0]["project_id"] == episode["id"]


def test_starting_the_same_premise_twice_is_refused(client):
    """Two episodes of one idea is how a channel accidentally publishes the
    same short with two titles."""
    channel = _channel(client)
    premise = client.post(
        f"/api/channels/{channel['id']}/premises", json=CANDIDATE
    ).json()
    client.post(f"/api/channels/{channel['id']}/premises/{premise['id']}/start")

    again = client.post(
        f"/api/channels/{channel['id']}/premises/{premise['id']}/start"
    )

    assert again.status_code == 409


def test_a_rejected_premise_is_kept_rather_than_deleted(client):
    """The rejections are the record of what was considered, which is the only
    thing that stops the same idea being re-proposed every month."""
    channel = _channel(client)
    premise = client.post(
        f"/api/channels/{channel['id']}/premises", json=CANDIDATE
    ).json()

    client.post(
        f"/api/channels/{channel['id']}/premises/{premise['id']}/reject",
        json={"reason": "too close to SF02"},
    )

    listed = client.get(f"/api/channels/{channel['id']}/premises").json()
    assert listed[0]["status"] == "rejected"
    assert "SF02" in listed[0]["rejection_reason"]
