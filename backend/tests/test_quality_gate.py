"""Whether an episode is good enough to publish, written down.

Review until now answered one question per take: is this shot usable. That is
the wrong unit for the decision that actually matters, which is about the whole
episode and is made once: does this go out.

The blueprint names nine measures and a target for each, and one extra question
worth more than the nine: *would I know this was AI within two seconds?* If the
answer is yes, the reason has to be named - plastic faces, excessive cinematic
lighting, impossible architecture, unnatural motion - because "it looks like AI"
regenerates nothing and "the faces are plastic in shots 6 and 7" regenerates two
shots.

Three things this is careful about:

* **The score is a record, not an opinion that evaporates.** It is kept per
  episode so nine pilots can be compared against each other rather than
  remembered.
* **A failed gate does not delete anything.** It refuses the publish step and
  names what fell short. Everything already made stays made.
* **The targets live in one place.** A gate whose thresholds are written into
  two files is a gate that will eventually disagree with itself.
"""

import pytest

from app.services import quality_gate


PASSING = {
    "hook_strength": 8, "story_clarity": 9, "visual_realism": 8,
    "world_consistency": 9, "character_consistency": 8, "ai_artifact": 8,
    "pacing": 8, "ending": 9, "audio": 7,
}


# ---------------------------------------------------------------------------
# The rubric
# ---------------------------------------------------------------------------

def test_every_metric_has_a_target_and_a_question_behind_it():
    """A number with no question behind it gets scored 8 every time."""
    for metric in quality_gate.METRICS:
        assert 1 <= metric.target <= 10, metric.key
        assert len(metric.question) > 20, metric.key
        assert metric.label.strip()


def test_the_rubric_covers_what_the_blueprint_asks_for():
    keys = {metric.key for metric in quality_gate.METRICS}
    assert keys == {
        "hook_strength", "story_clarity", "visual_realism", "world_consistency",
        "character_consistency", "ai_artifact", "pacing", "ending", "audio",
    }


# ---------------------------------------------------------------------------
# Evaluating
# ---------------------------------------------------------------------------

def test_a_passing_scorecard_passes():
    result = quality_gate.evaluate(PASSING, ai_tell=False, ai_tell_causes="")
    assert result.passed is True
    assert result.shortfalls == []


def test_a_single_metric_below_target_fails_and_is_named():
    """Naming it is the point: "not good enough" changes nothing."""
    scores = {**PASSING, "character_consistency": 5}

    result = quality_gate.evaluate(scores, ai_tell=False, ai_tell_causes="")

    assert result.passed is False
    assert [s["key"] for s in result.shortfalls] == ["character_consistency"]
    assert result.shortfalls[0]["scored"] == 5
    assert result.shortfalls[0]["target"] == 8


def test_a_metric_exactly_on_target_passes():
    """Targets in the blueprint are written as "at least", and a gate that
    reads them as "more than" fails work that met the standard."""
    scores = {**PASSING, "audio": quality_gate.target_for("audio")}
    assert quality_gate.evaluate(scores, ai_tell=False, ai_tell_causes="").passed


def test_an_unscored_metric_is_not_treated_as_a_pass():
    """Silence is the easiest way to pass a gate by accident."""
    scores = {k: v for k, v in PASSING.items() if k != "pacing"}

    result = quality_gate.evaluate(scores, ai_tell=False, ai_tell_causes="")

    assert result.passed is False
    assert result.shortfalls[0]["key"] == "pacing"
    assert result.shortfalls[0]["scored"] is None


def test_an_obvious_ai_tell_fails_the_gate_whatever_the_numbers_say():
    """The one question that outranks the nine. A film that reads as AI in two
    seconds is not saved by nines everywhere else."""
    result = quality_gate.evaluate(
        PASSING, ai_tell=True, ai_tell_causes="plastic faces in shots 6 and 7",
    )

    assert result.passed is False
    assert any("two seconds" in reason for reason in result.reasons)


def test_an_ai_tell_with_no_cause_is_refused_rather_than_recorded():
    """"It looks like AI" regenerates nothing; "the faces are plastic in shots
    6 and 7" regenerates two shots."""
    with pytest.raises(quality_gate.QualityGateError):
        quality_gate.evaluate(PASSING, ai_tell=True, ai_tell_causes="   ")


def test_a_score_outside_the_scale_is_refused():
    with pytest.raises(quality_gate.QualityGateError):
        quality_gate.evaluate(
            {**PASSING, "pacing": 11}, ai_tell=False, ai_tell_causes="",
        )


def test_an_unknown_metric_is_refused_rather_than_ignored():
    """A misspelt key scored 9 would otherwise leave the real metric unscored
    and the card looking complete."""
    with pytest.raises(quality_gate.QualityGateError) as exc:
        quality_gate.evaluate(
            {**PASSING, "pacing_": 9}, ai_tell=False, ai_tell_causes="",
        )
    assert "pacing_" in str(exc.value)


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------

def test_a_review_is_recorded_against_the_episode(client, sample_project):
    response = client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": PASSING, "ai_tell": False, "notes": "Holds up.",
    })

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["passed"] is True
    assert body["scores"]["hook_strength"] == 8


def test_the_latest_review_is_what_the_episode_reports(client, sample_project):
    """A second look supersedes the first; both are kept, because the change
    between them is the useful part."""
    client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": {**PASSING, "pacing": 4}, "ai_tell": False,
    })
    client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": PASSING, "ai_tell": False,
    })

    latest = client.get(f"/api/projects/{sample_project.id}/quality-review").json()

    assert latest["passed"] is True
    assert latest["scores"]["pacing"] == 8


def test_an_episode_never_reviewed_says_so_rather_than_404(client, sample_project):
    """Not reviewed yet is a normal state on the way to publishing, not an
    error to show somebody."""
    response = client.get(f"/api/projects/{sample_project.id}/quality-review")

    assert response.status_code == 200
    body = response.json()
    assert body["reviewed"] is False
    assert body["passed"] is False


def test_the_history_keeps_what_changed(client, sample_project):
    client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": {**PASSING, "pacing": 4}, "ai_tell": False,
    })
    client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": PASSING, "ai_tell": False,
    })

    history = client.get(
        f"/api/projects/{sample_project.id}/quality-review/history"
    ).json()

    assert len(history) == 2
    assert [entry["passed"] for entry in history] == [True, False]


def test_a_failing_review_names_the_shortfall_in_the_response(
    client, sample_project,
):
    response = client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": {**PASSING, "visual_realism": 3},
        "ai_tell": True,
        "ai_tell_causes": "excessive cinematic lighting throughout",
    })

    body = response.json()
    assert body["passed"] is False
    assert [s["key"] for s in body["shortfalls"]] == ["visual_realism"]
    assert body["ai_tell_causes"].startswith("excessive")


def test_a_bad_scorecard_is_refused_and_nothing_is_recorded(
    client, sample_project,
):
    response = client.post(f"/api/projects/{sample_project.id}/quality-review", json={
        "scores": {**PASSING, "pacing": 99}, "ai_tell": False,
    })

    assert response.status_code == 422, response.text
    assert client.get(
        f"/api/projects/{sample_project.id}/quality-review"
    ).json()["reviewed"] is False
