"""
Timeline API: what the cut shows, and what it truthfully says is missing.

A timeline row identified only by a truncated take id is not reviewable, and a
build that silently drops five of eighteen shots is not truthful. Both are
asserted here against the API responses the Timeline page actually renders.
"""

import os
import uuid
from datetime import datetime, timezone

from app.models import Scene, Shot, Take
from app.services import revisions, timeline_service
from app.services.mock_provider import _create_placeholder_png


def _current_take(
    shot: Shot,
    *,
    review_status: str = "Approved",
    file_path: str = "",
    lineage: dict | None = None,
    matching: bool = True,
    width: int = 0,
    height: int = 0,
) -> Take:
    return Take(
        id=str(uuid.uuid4()),
        shot_id=shot.id,
        file_path=file_path or f"C:/tmp/{uuid.uuid4()}.png",
        review_status=review_status,
        duration_sec=0.0,
        width=width,
        height=height,
        lineage=lineage or {},
        prompt_revision=shot.prompt_revision if matching else shot.prompt_revision - 1,
        prompt_sha256=shot.prompt_sha256 if matching else "stale-prompt",
        content_sha256=shot.content_sha256 if matching else "stale-content",
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
        created_at=datetime.now(timezone.utc),
    )


def _build(db, project_id: str) -> None:
    built = timeline_service.build_timeline_from_approved_takes(db, project_id)
    timeline_service.save_timeline_items(db, project_id, built)


def _add_shot(db, scene: Scene, order: int, subject: str) -> Shot:
    shot = Shot(
        id=str(uuid.uuid4()),
        scene_id=scene.id,
        order=order,
        subject=subject,
        image_prompt=f"prompt for {subject}",
        planned_duration_sec=2.0,
    )
    db.add(shot)
    db.commit()
    return shot


# ---------------------------------------------------------------------------
# Rows a person can read
# ---------------------------------------------------------------------------

def test_timeline_rows_name_their_scene_and_shot_instead_of_truncated_ids(
    client, db_session, sample_project, sample_scene, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _current_take(sample_shot)
    db_session.add(take)
    db_session.commit()
    _build(db_session, sample_project.id)

    response = client.get(f"/api/projects/{sample_project.id}/timeline")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["scene_id"] == sample_scene.id
    assert item["scene_title"] == sample_scene.title
    assert item["shot_name"].startswith(f"Shot {sample_shot.order}")
    assert sample_shot.subject in item["shot_name"]


def test_timeline_row_publishes_a_thumbnail_only_for_servable_media(
    client, db_session, sample_project, sample_shot, tmp_path
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _current_take(sample_shot, file_path=str(tmp_path / "gone.png"))
    db_session.add(take)
    db_session.commit()
    _build(db_session, sample_project.id)

    missing_media = client.get(f"/api/projects/{sample_project.id}/timeline")

    from app import paths

    real_media = os.path.join(paths.generated_dir(), f"{uuid.uuid4()}.png")
    _create_placeholder_png(real_media, 64, 36)
    take.file_path = real_media
    db_session.commit()

    servable = client.get(f"/api/projects/{sample_project.id}/timeline")

    assert missing_media.json()["items"][0]["thumbnail_url"] is None
    assert servable.json()["items"][0]["thumbnail_url"] == (
        f"/api/media/takes/{take.id}/file"
    )
    os.remove(real_media)


def test_timeline_row_flags_only_the_take_that_carries_a_waiver(
    client, db_session, sample_project, sample_scene, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    second_shot = _add_shot(db_session, sample_scene, 2, "Unwaived subject")
    revisions.refresh_project(db_session, sample_project.id)
    # The take a real waiver replaced: it has to exist and belong to the
    # same shot, or the waiver on the replacement is not provenance at all.
    original = _current_take(sample_shot, review_status="Rejected")
    db_session.add(original)
    db_session.commit()
    waived = _current_take(
        sample_shot,
        # sample_project targets 1920x1080 (16:9); this take is portrait, so
        # the mismatch the waiver excuses is real.
        width=1080,
        height=1920,
        lineage={
            "waived_from_take_id": original.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
    )
    plain = _current_take(second_shot)
    db_session.add_all([waived, plain])
    db_session.commit()
    _build(db_session, sample_project.id)

    items = client.get(f"/api/projects/{sample_project.id}/timeline").json()["items"]

    by_take = {item["take_id"]: item for item in items}
    assert by_take[waived.id]["waived"] is True
    assert by_take[plain.id]["waived"] is False


# ---------------------------------------------------------------------------
# Coverage: what is not on the cut, and why
# ---------------------------------------------------------------------------

def test_coverage_reports_every_shot_the_build_left_out_with_a_reason(
    client, db_session, sample_project, sample_scene, sample_shot
):
    ungenerated = _add_shot(db_session, sample_scene, 2, "Never generated")
    pending = _add_shot(db_session, sample_scene, 3, "Waiting on review")
    stale = _add_shot(db_session, sample_scene, 4, "Stale approval")
    rejected = _add_shot(db_session, sample_scene, 5, "All rejected")
    revisions.refresh_project(db_session, sample_project.id)

    db_session.add_all([
        _current_take(sample_shot),
        _current_take(pending, review_status="Pending"),
        # Approved, but against content the shot has since moved past.
        _current_take(stale, matching=False),
        _current_take(rejected, review_status="Rejected"),
    ])
    db_session.commit()
    _build(db_session, sample_project.id)

    body = client.get(f"/api/projects/{sample_project.id}/timeline").json()

    coverage = body["coverage"]
    assert coverage["total_shots"] == 5
    assert coverage["covered_shots"] == 1
    reasons = {entry["shot_id"]: entry["reason"] for entry in coverage["missing"]}
    assert set(reasons) == {ungenerated.id, pending.id, stale.id, rejected.id}
    assert "No take has been generated" in reasons[ungenerated.id]
    assert "Review" in reasons[pending.id]
    assert "out of date" in reasons[stale.id]
    assert "rejected" in reasons[rejected.id]
    missing_entry = next(
        entry for entry in coverage["missing"] if entry["shot_id"] == pending.id
    )
    assert missing_entry["scene_title"] == sample_scene.title
    assert "Waiting on review" in missing_entry["shot_name"]


def test_coverage_tells_the_user_to_rebuild_when_an_approved_take_is_ready(
    client, db_session, sample_project, sample_scene, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    db_session.add(_current_take(sample_shot))
    db_session.commit()
    _build(db_session, sample_project.id)

    later = _add_shot(db_session, sample_scene, 2, "Approved after the build")
    revisions.refresh_project(db_session, sample_project.id)
    db_session.add(_current_take(later))
    db_session.commit()

    coverage = client.get(
        f"/api/projects/{sample_project.id}/timeline"
    ).json()["coverage"]

    assert coverage["covered_shots"] == 1
    assert coverage["total_shots"] == 2
    assert "Rebuild" in coverage["missing"][0]["reason"]


def test_a_complete_cut_reports_no_missing_shots(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    db_session.add(_current_take(sample_shot))
    db_session.commit()
    _build(db_session, sample_project.id)

    coverage = client.get(
        f"/api/projects/{sample_project.id}/timeline"
    ).json()["coverage"]

    assert coverage == {"total_shots": 1, "covered_shots": 1, "missing": []}


# ---------------------------------------------------------------------------
# PUT must reject an incomplete item before touching the existing cut
# ---------------------------------------------------------------------------

def test_put_rejects_an_item_missing_both_ids_and_keeps_the_existing_cut(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _current_take(sample_shot)
    db_session.add(take)
    db_session.commit()
    _build(db_session, sample_project.id)
    existing = client.get(f"/api/projects/{sample_project.id}/timeline").json()
    assert existing["items"][0]["take_id"] == take.id

    response = client.put(
        f"/api/projects/{sample_project.id}/timeline",
        json={"items": [{"order": 0, "duration_sec": 1.0}]},
    )

    # FastAPI/pydantic rejects the malformed payload before the handler -
    # and therefore the service's delete-then-replace - ever runs.
    assert response.status_code == 422

    survived = client.get(f"/api/projects/{sample_project.id}/timeline").json()
    assert survived["items"][0]["id"] == existing["items"][0]["id"]
    assert survived["items"][0]["take_id"] == take.id


def test_put_rejects_a_lineage_mismatched_item_and_keeps_the_existing_cut(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _current_take(sample_shot)
    db_session.add(take)
    db_session.commit()
    _build(db_session, sample_project.id)
    existing = client.get(f"/api/projects/{sample_project.id}/timeline").json()

    response = client.put(
        f"/api/projects/{sample_project.id}/timeline",
        json={
            "items": [{
                "shot_id": sample_shot.id,
                "take_id": "ghost-take-id",
                "order": 0,
                "duration_sec": 1.0,
            }]
        },
    )

    # A well-formed but bogus lineage is a 409, and it must not have
    # replaced the previously valid cut with the rejected one.
    assert response.status_code == 409

    survived = client.get(f"/api/projects/{sample_project.id}/timeline").json()
    assert survived["items"][0]["id"] == existing["items"][0]["id"]
    assert survived["items"][0]["take_id"] == take.id


def test_build_response_carries_the_same_coverage_as_the_timeline_read(
    client, db_session, sample_project, sample_scene, sample_shot
):
    _add_shot(db_session, sample_scene, 2, "No take at all")
    revisions.refresh_project(db_session, sample_project.id)
    db_session.add(_current_take(sample_shot))
    db_session.commit()

    build = client.post(f"/api/projects/{sample_project.id}/timeline/build")
    read = client.get(f"/api/projects/{sample_project.id}/timeline")

    assert build.status_code == 200
    assert build.json()["coverage"] == read.json()["coverage"]
    assert build.json()["coverage"]["covered_shots"] == 1
    assert build.json()["items"][0]["shot_name"].startswith("Shot")
