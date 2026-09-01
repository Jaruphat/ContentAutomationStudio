"""
Tests for take review endpoints addressed by global take/shot id.

These routes are what the cockpit's review and inspector panels call, so a
mismatch between the path here and the path the client builds is invisible to
both test suites until someone clicks the button.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Take


@pytest.fixture()
def sample_take(db_session: Session, sample_shot) -> Take:
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=sample_shot.id,
        file_path="C:/tmp/take.png",
        review_status="Pending",
        width=1920,
        height=1080,
    )
    db_session.add(take)
    db_session.commit()
    db_session.refresh(take)
    return take


class TestGetTake:
    def test_returns_the_take(self, client, sample_take):
        resp = client.get(f"/api/takes/{sample_take.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_take.id

    def test_unknown_take_is_404(self, client):
        assert client.get("/api/takes/nope").status_code == 404


class TestListShotTakes:
    def test_lists_takes_for_a_shot(self, client, sample_shot, sample_take):
        resp = client.get(f"/api/shots/{sample_shot.id}/takes")
        assert resp.status_code == 200
        assert [t["id"] for t in resp.json()] == [sample_take.id]

    def test_unknown_shot_is_404(self, client):
        assert client.get("/api/shots/nope/takes").status_code == 404


class TestApproveReject:
    def test_approve_sets_status_and_timestamp(self, client, sample_take):
        resp = client.post(
            f"/api/takes/{sample_take.id}/approve",
            json={"rating": 5, "notes": "good framing"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["review_status"] == "Approved"
        assert body["rating"] == 5
        assert body["approved_at"] is not None

    def test_approving_twice_is_rejected(self, client, sample_take):
        client.post(f"/api/takes/{sample_take.id}/approve", json={})
        resp = client.post(f"/api/takes/{sample_take.id}/approve", json={})
        assert resp.status_code == 400

    def test_reject_sets_status(self, client, sample_take):
        resp = client.post(
            f"/api/takes/{sample_take.id}/reject", json={"notes": "wrong wardrobe"}
        )
        assert resp.status_code == 200
        assert resp.json()["review_status"] == "Rejected"
        assert resp.json()["notes"] == "wrong wardrobe"

    def test_approve_promotes_the_shot(self, client, sample_shot, sample_take):
        client.post(f"/api/takes/{sample_take.id}/approve", json={})
        resp = client.get(
            f"/api/projects/{sample_shot.scene.project_id}"
            f"/scenes/{sample_shot.scene_id}/shots/{sample_shot.id}"
        )
        assert resp.json()["status"] == "Approved"


class TestRegenerate:
    def test_creates_a_new_queued_job(self, client, sample_shot):
        resp = client.post(f"/api/shots/{sample_shot.id}/regenerate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "Queued"
        assert body["shot_id"] == sample_shot.id

    def test_regenerate_uses_a_fresh_seed(self, client, sample_shot):
        first = client.post(f"/api/shots/{sample_shot.id}/regenerate").json()
        second = client.post(f"/api/shots/{sample_shot.id}/regenerate").json()
        assert first["seed"] != second["seed"]

    def test_unknown_shot_is_404(self, client):
        assert client.post("/api/shots/nope/regenerate").status_code == 404
