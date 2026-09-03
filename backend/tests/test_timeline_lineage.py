"""Revision-lineage gates for timeline selection and export."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Shot, Take, TimelineItem
from app.services import revisions, timeline_service


def _approved_take(
    shot,
    *,
    current: bool,
    created_at: datetime,
    lineage: dict | None = None,
    width: int = 0,
    height: int = 0,
) -> Take:
    return Take(
        id=str(uuid.uuid4()),
        shot_id=shot.id,
        file_path=f"C:/tmp/{uuid.uuid4()}.png",
        review_status="Approved",
        width=width,
        height=height,
        prompt_revision=shot.prompt_revision if current else max(0, shot.prompt_revision - 1),
        prompt_sha256=shot.prompt_sha256 if current else "stale-prompt",
        content_sha256=shot.content_sha256 if current else "stale-content",
        reference_image_ids=list(shot.reference_asset_ids or []) if current else ["stale-ref"],
        reference_sha256s=list(shot.reference_sha256s or []) if current else ["stale-hash"],
        lineage=lineage or {},
        created_at=created_at,
    )


#: sample_project targets 1920x1080 (16:9); portrait pixels are a real
#: mismatch a waiver can legitimately excuse.
MISMATCHED_DIMENSIONS = {"width": 1080, "height": 1920}


def _waiver_source_take(db_session, shot) -> Take:
    """A real prior take for the same shot - what a waiver claims to replace."""
    source = Take(
        id=str(uuid.uuid4()),
        shot_id=shot.id,
        file_path=f"C:/tmp/{uuid.uuid4()}.png",
        review_status="Rejected",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db_session.add(source)
    db_session.commit()
    return source


def test_build_uses_latest_exact_current_take_and_excludes_stale_only_shots(
    db_session, sample_project, sample_scene, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    now = datetime.now(timezone.utc)
    current = _approved_take(sample_shot, current=True, created_at=now)
    newer_stale = _approved_take(
        sample_shot, current=False, created_at=now + timedelta(seconds=1)
    )
    stale_only_shot = Shot(
        id=str(uuid.uuid4()),
        scene_id=sample_scene.id,
        order=2,
        subject="Stale only",
        image_prompt="stale only prompt",
    )
    db_session.add(stale_only_shot)
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    stale_only = _approved_take(
        stale_only_shot, current=False, created_at=now + timedelta(seconds=2)
    )
    db_session.add_all([current, newer_stale, stale_only])
    db_session.commit()

    items = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )

    assert [item["shot_id"] for item in items] == [sample_shot.id]
    assert items[0]["take_id"] == current.id
    assert items[0]["take_prompt_revision"] == sample_shot.prompt_revision
    assert items[0]["shot_prompt_revision"] == sample_shot.prompt_revision


def test_saved_timeline_and_manifest_emit_exact_take_lineage(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot, current=True, created_at=datetime.now(timezone.utc)
    )
    db_session.add(take)
    db_session.commit()

    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    saved = timeline_service.save_timeline_items(db_session, sample_project.id, built)
    manifest = timeline_service.get_timeline_manifest(db_session, sample_project.id)

    assert saved[0].take_prompt_revision == sample_shot.prompt_revision
    assert saved[0].shot_prompt_revision == sample_shot.prompt_revision
    item = manifest["items"][0]
    assert item["take_prompt_revision"] == sample_shot.prompt_revision
    assert item["shot_prompt_revision"] == sample_shot.prompt_revision
    assert item["source"]["prompt_revision"] == take.prompt_revision
    assert item["source"]["prompt_sha256"] == take.prompt_sha256
    assert item["source"]["content_sha256"] == take.content_sha256
    assert item["source"]["reference_image_ids"] == take.reference_image_ids
    assert item["source"]["reference_sha256s"] == take.reference_sha256s


def test_manifest_marks_only_waived_takes_that_are_on_the_current_timeline(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    now = datetime.now(timezone.utc)
    # A real prior take for this shot, superseded by the waived one below -
    # exactly what a waiver's "waived_from_take_id" is supposed to name.
    off_timeline_take = _approved_take(
        sample_shot, current=True, created_at=now - timedelta(seconds=1),
    )
    db_session.add(off_timeline_take)
    db_session.commit()
    timeline_take = _approved_take(
        sample_shot,
        current=True,
        created_at=now,
        lineage={
            "waived_from_take_id": off_timeline_take.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
            "waived_at": now.isoformat(),
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(timeline_take)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    manifest = timeline_service.get_timeline_manifest(
        db_session, sample_project.id, strict_lineage=True
    )

    assert manifest["warnings"] == [
        {
            "code": "e2e_aspect_override",
            "message": timeline_service.E2E_ASPECT_OVERRIDE_WARNING,
            "take_ids": [timeline_take.id],
            "waived_from_take_ids": [off_timeline_take.id],
            "waiver_reasons": [timeline_service.TRUSTED_WAIVER_REASON],
        }
    ]
    assert manifest["delivery_validation"] == {
        "pipeline_pass": True,
        "delivery_spec_pass": False,
    }
    assert manifest["items"][0]["source"]["lineage"] == timeline_take.lineage


def test_manifest_does_not_treat_a_partial_or_off_timeline_waiver_as_a_bypass(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    now = datetime.now(timezone.utc)
    timeline_take = _approved_take(
        sample_shot,
        current=True,
        created_at=now,
        lineage={"waiver_reason": "Missing source take id"},
    )
    off_timeline_take = _approved_take(
        sample_shot,
        current=True,
        created_at=now - timedelta(seconds=1),
        lineage={
            "waived_from_take_id": "off-timeline-source",
            "waiver_reason": "User-approved E2E dimension exception",
        },
    )
    db_session.add_all([timeline_take, off_timeline_take])
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    manifest = timeline_service.get_timeline_manifest(
        db_session, sample_project.id, strict_lineage=True
    )

    assert manifest["warnings"] == []
    assert manifest["delivery_validation"] == {
        "pipeline_pass": True,
        "delivery_spec_pass": True,
    }


# ---------------------------------------------------------------------------
# is_waived: every part of a fabricated waiver must fail closed
# ---------------------------------------------------------------------------

def test_waiver_is_rejected_when_the_source_take_id_does_not_resolve(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": "no-such-take",
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(take)
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is False


def test_waiver_is_rejected_when_it_references_itself(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        **MISMATCHED_DIMENSIONS,
    )
    take.lineage = {
        "waived_from_take_id": take.id,
        "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
    }
    db_session.add(take)
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is False


def test_waiver_is_rejected_when_claimed_source_was_created_later(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        **MISMATCHED_DIMENSIONS,
    )
    source = _approved_take(
        sample_shot,
        current=False,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    take.lineage = {
        "waived_from_take_id": source.id,
        "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
    }
    db_session.add_all([take, source])
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is False


def test_waiver_is_rejected_when_the_source_take_belongs_to_a_different_shot(
    db_session, sample_project, sample_scene, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    other_shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2, subject="Other",
    )
    db_session.add(other_shot)
    db_session.commit()
    source_on_other_shot = _waiver_source_take(db_session, other_shot)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": source_on_other_shot.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(take)
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is False


def test_waiver_is_rejected_when_the_reason_is_not_the_exact_trusted_text(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    source = _waiver_source_take(db_session, sample_shot)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": source.id,
            # Close, but not the exact trusted wording - and not a reason
            # the caller gets to invent.
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON + "!",
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(take)
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is False


def test_waiver_is_rejected_when_the_take_s_own_dimensions_already_match_target(
    db_session, sample_project, sample_shot
):
    """A waiver excuses a real mismatch. Nothing here is actually wrong, so
    there is nothing to excuse - a fabricated waiver must not create a
    delivery-spec failure out of nothing."""
    revisions.refresh_project(db_session, sample_project.id)
    source = _waiver_source_take(db_session, sample_shot)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": source.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
        width=1920, height=1080,  # matches sample_project's 16:9 target
    )
    db_session.add(take)
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is False


def test_waiver_is_accepted_when_every_part_is_genuine(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    source = _waiver_source_take(db_session, sample_shot)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": source.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(take)
    db_session.commit()

    assert timeline_service.is_waived(db_session, sample_project, take) is True


def test_timeline_api_and_render_plan_expose_the_scoped_override_warning(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    source = _waiver_source_take(db_session, sample_shot)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": source.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(take)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    timeline_response = client.get(f"/api/projects/{sample_project.id}/timeline")
    render_plan_response = client.post(
        f"/api/projects/{sample_project.id}/render-plan"
    )
    export_response = client.get(
        f"/api/projects/{sample_project.id}/export/timeline-manifest"
    )

    assert timeline_response.status_code == 200
    assert timeline_response.json()["warnings"][0]["message"] == (
        timeline_service.E2E_ASPECT_OVERRIDE_WARNING
    )
    assert timeline_response.json()["delivery_validation"]["delivery_spec_pass"] is False
    assert render_plan_response.status_code == 200
    assert timeline_service.E2E_ASPECT_OVERRIDE_WARNING in (
        render_plan_response.json()["warnings"]
    )
    assert render_plan_response.json()["warning_metadata"][0]["take_ids"] == [take.id]
    assert render_plan_response.json()["delivery_validation"]["pipeline_pass"] is True
    assert render_plan_response.json()["delivery_validation"]["delivery_spec_pass"] is False
    assert export_response.status_code == 200
    assert export_response.json()["warnings"][0]["take_ids"] == [take.id]


def test_project_archive_carries_the_scoped_waiver_and_take_lineage(
    client, db_session, sample_project, sample_shot
):
    """The archive is the whole-project record; a waived delivery cannot be
    invisible in it."""
    revisions.refresh_project(db_session, sample_project.id)
    source = _waiver_source_take(db_session, sample_shot)
    waived = _approved_take(
        sample_shot,
        current=True,
        created_at=source.created_at + timedelta(seconds=1),
        lineage={
            "waived_from_take_id": source.id,
            "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
        },
        **MISMATCHED_DIMENSIONS,
    )
    db_session.add(waived)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    archive = client.get(
        f"/api/projects/{sample_project.id}/export/project-archive"
    ).json()
    manifest = client.get(
        f"/api/projects/{sample_project.id}/export/manifest"
    ).json()

    assert archive["warnings"][0]["take_ids"] == [waived.id]
    assert archive["delivery_validation"] == {
        "pipeline_pass": True,
        "delivery_spec_pass": False,
    }
    archived_take = next(
        take
        for take in archive["scenes"][0]["shots"][0]["takes"]
        if take["id"] == waived.id
    )
    assert archived_take["lineage"]["waived_from_take_id"] == source.id
    # The generation manifest describes jobs and their takes; a take that was
    # only accepted under a waiver has to say so there too.
    assert manifest["delivery_validation"]["delivery_spec_pass"] is False


def test_project_archive_reports_a_clean_delivery_when_nothing_is_waived(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot, current=True, created_at=datetime.now(timezone.utc)
    )
    db_session.add(take)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    archive = client.get(
        f"/api/projects/{sample_project.id}/export/project-archive"
    ).json()

    assert archive["warnings"] == []
    assert archive["delivery_validation"] == {
        "pipeline_pass": True,
        "delivery_spec_pass": True,
    }


def test_timeline_waiver_does_not_bypass_default_aspect_preflight(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot,
        current=True,
        created_at=datetime.now(timezone.utc),
        lineage={
            "waived_from_take_id": "source-take",
            "waiver_reason": "User-approved E2E dimension exception",
        },
    )
    db_session.add(take)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)
    sample_project.aspect_ratio = "16:9"
    sample_project.target_resolution = "864x480"
    db_session.commit()

    response = client.get(f"/api/projects/{sample_project.id}/preflight")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert any(
        "does not match target resolution" in issue
        for shot_issues in body["issues"]
        for issue in shot_issues["issues"]
    )


def test_manifest_refuses_timeline_item_after_shot_revision_changes(
    client, db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot, current=True, created_at=datetime.now(timezone.utc)
    )
    db_session.add(take)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    sample_shot.action = "content changed after the cut was built"
    db_session.commit()

    with pytest.raises(timeline_service.StaleTimelineError):
        timeline_service.get_timeline_manifest(
            db_session, sample_project.id, strict_lineage=True
        )

    response = client.get(
        f"/api/projects/{sample_project.id}/export/timeline-manifest"
    )
    assert response.status_code == 409
    assert "stale or mismatched" in response.json()["detail"]
    assert db_session.query(TimelineItem).count() == 1


def test_generation_manifest_and_archive_report_pipeline_failure_on_stale_lineage(
    client, db_session, sample_project, sample_shot
):
    """These exports keep returning 200 - they describe the whole project, not
    just the cut - but they must not claim a pipeline pass that the timeline
    manifest itself refuses. A hard-coded True here would say otherwise."""
    revisions.refresh_project(db_session, sample_project.id)
    take = _approved_take(
        sample_shot, current=True, created_at=datetime.now(timezone.utc)
    )
    db_session.add(take)
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)

    sample_shot.action = "content changed after the cut was built"
    db_session.commit()

    manifest_response = client.get(
        f"/api/projects/{sample_project.id}/export/manifest"
    )
    archive_response = client.get(
        f"/api/projects/{sample_project.id}/export/project-archive"
    )

    assert manifest_response.status_code == 200
    assert manifest_response.json()["delivery_validation"] == {
        "pipeline_pass": False,
        "delivery_spec_pass": False,
    }
    assert manifest_response.json()["warnings"][0]["code"] == "stale_timeline_lineage"
    assert archive_response.status_code == 200
    assert archive_response.json()["delivery_validation"] == {
        "pipeline_pass": False,
        "delivery_spec_pass": False,
    }
    assert archive_response.json()["warnings"][0]["code"] == "stale_timeline_lineage"


def test_refused_stale_update_preserves_the_existing_current_timeline(
    db_session, sample_project, sample_shot
):
    revisions.refresh_project(db_session, sample_project.id)
    now = datetime.now(timezone.utc)
    current = _approved_take(sample_shot, current=True, created_at=now)
    stale = _approved_take(
        sample_shot, current=False, created_at=now + timedelta(seconds=1)
    )
    db_session.add_all([current, stale])
    db_session.commit()
    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    original = timeline_service.save_timeline_items(
        db_session, sample_project.id, built
    )[0]

    replacement = {**built[0], "id": str(uuid.uuid4()), "take_id": stale.id}
    with pytest.raises(timeline_service.StaleTimelineError):
        timeline_service.save_timeline_items(
            db_session, sample_project.id, [replacement]
        )

    stored = db_session.query(TimelineItem).all()
    assert [item.id for item in stored] == [original.id]