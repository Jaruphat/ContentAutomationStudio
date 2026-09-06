"""Rejecting the last take gives the shot back.

Found while producing an episode through the pages. Two takes were made before
a workflow was pinned to the size it was tuned for - a still that took
forty-five minutes at the delivery canvas, and a clip that started from the
wrong frame - so both were rejected, which is what rejection is for.

The shot was then stuck. Rejecting every take left it in ``NeedsReview``, and
preflight refuses a shot in that state ("expected Draft, Failed, Ready"), so
the queue would never pick it up again. There was nothing left to review: the
only take had just been thrown away. The producer had to reach into the
database to move it on, which is exactly the shape of thing this application
exists to avoid.

A shot whose takes are all rejected is a shot that has not been made yet. It
has its prompt, its references and its workflow; what it does not have is a
picture. That is ``Ready``.

The same argument as a cancelled render giving the shot back, and the same
rule: a state a person cannot leave without a terminal is a bug, whatever it
is called.
"""

import uuid

from app.models import Shot, Take


def _shot(db, scene, status="Generating") -> Shot:
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=1,
        generation_mode="image", image_prompt="A newspaper kiosk before dawn.",
        status=status,
    )
    db.add(shot)
    db.commit()
    return shot


def _take(db, shot, status="Pending") -> Take:
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id,
        file_path=f"/tmp/{uuid.uuid4()}.png", review_status=status,
    )
    db.add(take)
    db.commit()
    return take


def test_rejecting_the_only_take_makes_the_shot_generatable_again(
    client, db_session, sample_scene,
):
    shot = _shot(db_session, sample_scene, status="NeedsReview")
    take = _take(db_session, shot)

    response = client.post(f"/api/takes/{take.id}/reject")

    assert response.status_code == 200, response.text
    db_session.refresh(shot)
    assert shot.status == "Ready"


def test_a_shot_with_another_take_still_waiting_stays_in_review(
    client, db_session, sample_scene,
):
    """Two takes, one rejected: there is still something to look at."""
    shot = _shot(db_session, sample_scene, status="NeedsReview")
    rejected = _take(db_session, shot)
    _take(db_session, shot)

    client.post(f"/api/takes/{rejected.id}/reject")

    db_session.refresh(shot)
    assert shot.status == "NeedsReview"


def test_rejecting_a_take_does_not_disown_an_approved_one(
    client, db_session, sample_scene,
):
    """A second attempt rejected must not unpick the first one's approval."""
    shot = _shot(db_session, sample_scene, status="Approved")
    _take(db_session, shot, status="Approved")
    second = _take(db_session, shot)

    client.post(f"/api/takes/{second.id}/reject")

    db_session.refresh(shot)
    assert shot.status == "Approved"


def test_the_released_shot_passes_preflight(
    client, db_session, sample_project, sample_scene,
):
    """The point of the fix, stated as the thing that was blocked: after a
    rejection the queue can take the shot again."""
    shot = _shot(db_session, sample_scene, status="NeedsReview")
    take = _take(db_session, shot)
    client.post(f"/api/takes/{take.id}/reject")

    preflight = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    blocked = [
        issue for entry in preflight["issues"] if entry["shot_id"] == shot.id
        for issue in entry["issues"] if "status" in issue
    ]
    assert blocked == []


def test_a_shot_whose_takes_were_all_rejected_is_not_stale(
    client, db_session, sample_scene,
):
    """The second half of the same stuck state.

    Staleness means "what this shot produced is not what it now is". A shot
    whose only take has been rejected has not produced anything: it was thrown
    away. Leaving the digest of the discarded take behind marked the shot
    stale, and preflight refuses a stale shot - so the shot was blocked twice
    over, once for its status and once for a take that no longer counted.
    """
    shot = _shot(db_session, sample_scene, status="NeedsReview")
    shot.generated_revision = 1
    shot.prompt_revision = 3
    shot.generated_content_sha256 = "an old digest"
    shot.is_stale = True
    take = _take(db_session, shot)
    db_session.commit()

    client.post(f"/api/takes/{take.id}/reject")

    db_session.refresh(shot)
    assert shot.is_stale is False
    assert not shot.generated_revision


def test_an_approved_take_keeps_its_shot_marked_as_generated(
    client, db_session, sample_scene,
):
    """A rejected second attempt must not erase what the first one produced."""
    shot = _shot(db_session, sample_scene, status="Approved")
    shot.generated_revision = 2
    db_session.commit()
    _take(db_session, shot, status="Approved")
    second = _take(db_session, shot)

    client.post(f"/api/takes/{second.id}/reject")

    db_session.refresh(shot)
    assert shot.generated_revision == 2
