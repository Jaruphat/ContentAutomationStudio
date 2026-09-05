"""Reviewing a film without clicking twenty-three times.

A three-minute short is twenty-three takes, and approving them one at a time is
the slowest part of using this application by a wide margin. The queue can make
a film overnight; the review of it should not take longer than watching it.

The batch is not a loop with a nicer name. It reports what happened to each
take, applies nothing when any of them cannot be acted on, and refuses a take
from another project outright - because a mistake made twenty-three at a time
is twenty-three times harder to notice.
"""

import uuid

from app.models import Take


def _take(db, shot_id, status="Pending", path="frame.png"):
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot_id, file_path=path,
        review_status=status, width=64, height=64,
    )
    db.add(take)
    db.commit()
    return take


def test_approving_a_batch_approves_every_take_in_it(
    client, db_session, sample_project, sample_shot,
):
    takes = [_take(db_session, sample_shot.id) for _ in range(3)]

    response = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={"take_ids": [t.id for t in takes], "action": "approve"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["approved"] == 3
    assert body["failed"] == 0
    for take in takes:
        db_session.refresh(take)
        assert take.review_status == "Approved"


def test_the_result_names_each_take_and_what_happened_to_it(
    client, db_session, sample_project, sample_shot,
):
    """A count alone cannot be checked against what a user expected."""
    takes = [_take(db_session, sample_shot.id) for _ in range(2)]

    body = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={"take_ids": [t.id for t in takes], "action": "approve"},
    ).json()

    assert {r["take_id"] for r in body["results"]} == {t.id for t in takes}
    assert all(r["status"] == "Approved" for r in body["results"])


def test_rejecting_a_batch_carries_one_reason_to_all_of_them(
    client, db_session, sample_project, sample_shot,
):
    takes = [_take(db_session, sample_shot.id) for _ in range(2)]

    response = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={
            "take_ids": [t.id for t in takes],
            "action": "reject",
            "reason": "wrong character",
        },
    )

    assert response.status_code == 200, response.text
    for take in takes:
        db_session.refresh(take)
        assert take.review_status == "Rejected"
        assert "wrong character" in (take.notes or "")


def test_a_take_from_another_project_is_refused_and_nothing_is_applied(
    client, db_session, sample_project, sample_shot,
):
    """Half-applied is the worst outcome: it leaves the user unsure which
    half, across a batch too large to check by eye."""
    mine = _take(db_session, sample_shot.id)
    other_project = client.post("/api/projects", json={"title": "Elsewhere"}).json()
    other_scene = client.post(
        f"/api/projects/{other_project['id']}/scenes", json={"order": 1},
    ).json()
    other_shot = client.post(
        f"/api/projects/{other_project['id']}/scenes/{other_scene['id']}/shots",
        json={"order": 1},
    ).json()
    theirs = _take(db_session, other_shot["id"])

    response = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={"take_ids": [mine.id, theirs.id], "action": "approve"},
    )

    assert response.status_code == 409, response.text
    db_session.refresh(mine)
    assert mine.review_status == "Pending", "nothing may be applied"


def test_an_unknown_take_id_is_refused_rather_than_skipped(
    client, db_session, sample_project, sample_shot,
):
    mine = _take(db_session, sample_shot.id)

    response = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={"take_ids": [mine.id, "no-such-take"], "action": "approve"},
    )

    assert response.status_code == 409
    db_session.refresh(mine)
    assert mine.review_status == "Pending"


def test_an_empty_batch_is_a_bad_request_not_a_silent_success(
    client, sample_project,
):
    response = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={"take_ids": [], "action": "approve"},
    )
    assert response.status_code in (400, 422)


def test_a_batch_matches_the_single_take_contract_for_a_reviewed_shot(
    client, db_session, sample_project, sample_shot,
):
    """The batch is the existing endpoint applied many times, not a new rule.

    Approving two takes of one shot is allowed here exactly as it is one at a
    time; the timeline settles the ambiguity by taking the most recent. A batch
    that quietly enforced something stricter would make the two paths disagree.
    """
    first = _take(db_session, sample_shot.id, path="a.png")
    second = _take(db_session, sample_shot.id, path="b.png")

    body = client.post(
        f"/api/projects/{sample_project.id}/takes/batch-review",
        json={"take_ids": [first.id, second.id], "action": "approve"},
    ).json()

    assert body["approved"] == 2
    db_session.refresh(sample_shot)
    assert sample_shot.status == "Approved"
