"""Regenerating for a reason, instead of rolling the dice again.

Regeneration was one button that made a new seed. When a take is nearly right,
that is the wrong move: a new seed re-rolls the composition, so the framing
that worked is thrown away along with the thing that did not. The user's only
alternative was to edit the prompt by hand, which changes the shot's content
revision and marks every take of it stale.

What the user actually wants to say is small and finite: *same shot, different
framing*, or *same framing, later in the day*. Those two ask for opposite
things from the sampler and the difference is not in the words:

* A different framing needs a **new seed**. The seed is most of what fixes
  composition, so keeping it and asking for a wider shot mostly returns the
  same shot.
* A different light at the same framing needs the **seed kept**. Holding it
  while the prompt changes is what makes the structure persist and the light
  move, which is the whole request.

So an intent carries both a directive and a seed policy, and neither is left
to the user to work out. The shot itself is never edited - the directive rides
on the job - because an intent is a request for one take, not a change to what
the shot is.
"""

import uuid

import pytest

from app.models import GenerationJob, Take
from app.services import job_payload, regeneration_intent


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

def test_reframing_re_rolls_the_seed_and_relighting_holds_it():
    """The one distinction the whole feature exists to encode."""
    assert regeneration_intent.get("reframe").keep_seed is False
    assert regeneration_intent.get("relight").keep_seed is True


def test_every_intent_carries_a_directive_and_an_explanation():
    """A dropdown of bare verbs is a worse prompt box. Each entry has to say
    what it will do to the image and why it does it that way."""
    for intent in regeneration_intent.all_intents():
        assert intent.directive.strip(), intent.key
        assert len(intent.explanation) > 30, intent.key
        assert intent.label.strip(), intent.key


def test_an_unknown_intent_is_refused_rather_than_ignored():
    """Silently dropping it would return an ordinary re-roll while the user
    believes they asked for something specific."""
    with pytest.raises(regeneration_intent.UnknownIntent):
        regeneration_intent.get("make-it-pop")


def test_no_intent_is_the_plain_re_roll_that_already_existed():
    assert regeneration_intent.get("") is None


# ---------------------------------------------------------------------------
# Through the endpoint
# ---------------------------------------------------------------------------

def _completed_take(db, shot_id, seed):
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=shot_id, seed=seed, status="Completed",
        parameter_map={job_payload.SEED: seed},
    )
    db.add(job)
    db.flush()
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot_id, job_id=job.id,
        file_path="frame.png", review_status="Rejected", width=64, height=64,
    )
    db.add(take)
    db.commit()
    return take


def test_relighting_reuses_the_seed_of_the_take_being_improved(
    client, db_session, sample_shot,
):
    _completed_take(db_session, sample_shot.id, seed=4242)

    response = client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "relight", "intent_note": "late afternoon"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["seed"] == 4242, "holding the seed is what keeps the framing"


def test_reframing_does_not_reuse_the_seed(client, db_session, sample_shot):
    _completed_take(db_session, sample_shot.id, seed=4242)

    body = client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "reframe"},
    ).json()

    assert body["seed"] != 4242


def test_the_directive_and_the_note_reach_the_prompt_that_is_submitted(
    client, db_session, sample_shot,
):
    body = client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "relight", "intent_note": "late afternoon, low sun"},
    ).json()

    prompt = body["parameter_map"][job_payload.POSITIVE_PROMPT]
    assert "late afternoon, low sun" in prompt
    assert regeneration_intent.get("relight").directive in prompt


def test_the_intent_is_recorded_on_the_job_that_ran(
    client, db_session, sample_shot,
):
    """Six takes of one shot are unreadable without knowing what each was
    asking for."""
    body = client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "reframe", "intent_note": "wider"},
    ).json()

    assert body["request_params"]["regeneration_intent"] == "reframe"
    assert body["request_params"]["regeneration_note"] == "wider"


def test_the_shot_itself_is_never_edited_by_an_intent(
    client, db_session, sample_shot,
):
    """An intent asks for one take. Writing it into the shot would change what
    the shot *is*, and mark every earlier take of it stale."""
    # Regeneration refreshes revisions on its way through, and on a shot that
    # has never been generated that first pass establishes the digest
    # baseline. Do a plain re-roll first so the comparison below is about the
    # intent rather than about that one-off migration.
    client.post(f"/api/shots/{sample_shot.id}/regenerate")
    primed = (
        db_session.query(GenerationJob)
        .filter(GenerationJob.shot_id == sample_shot.id)
        .first()
    )
    primed.status = "Completed"
    db_session.commit()
    db_session.refresh(sample_shot)

    before = (
        sample_shot.image_prompt, sample_shot.video_prompt,
        sample_shot.content_sha256, sample_shot.prompt_revision,
    )

    client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "relight", "intent_note": "dusk"},
    )

    db_session.refresh(sample_shot)
    assert (
        sample_shot.image_prompt, sample_shot.video_prompt,
        sample_shot.content_sha256, sample_shot.prompt_revision,
    ) == before


def test_an_unknown_intent_is_a_bad_request(client, sample_shot):
    response = client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "make-it-pop"},
    )
    assert response.status_code == 422, response.text
    assert "make-it-pop" in response.text


def test_relighting_with_no_previous_take_still_runs(client, sample_shot):
    """There is nothing to hold the framing of, so it degrades to a fresh
    seed rather than refusing a request that is merely premature."""
    response = client.post(
        f"/api/shots/{sample_shot.id}/regenerate",
        json={"intent": "relight"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["seed"]
