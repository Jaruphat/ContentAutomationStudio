"""Migration compatibility for take and timeline lineage.

An installation that predates content-revision tracking has approved takes and
a finished timeline, and none of the lineage columns those features compare.
``ALTER TABLE`` can only add them as NULL, so without a backfill every legacy
take stops matching its shot: the auto-build places nothing and then replaces
the user's cut with that nothing.

These tests pin the two halves of the fix - lineage is recovered or honestly
marked unverified, and a build that resolves to nothing never overwrites a real
timeline.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.models import Shot, Take, TimelineItem
from app.routers import review as review_router
from app.schemas import TakeResponse
from app.services import revisions, timeline_service


def columns_of(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


@pytest.fixture()
def pre_lineage_db(tmp_path, monkeypatch):
    """A database from before lineage tracking, with a finished project in it.

    Two approved takes on the timeline. One still has the job that produced it
    (with digests, so its lineage is recoverable); the other's job is gone,
    which is the case nothing can recover and must therefore mark unverified.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'pre-lineage.db'}")

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE projects (id VARCHAR PRIMARY KEY, title VARCHAR, "
            "aspect_ratio VARCHAR, target_resolution VARCHAR, frame_rate FLOAT)"
        ))
        conn.execute(text(
            "CREATE TABLE scenes (id VARCHAR PRIMARY KEY, project_id VARCHAR, "
            "\"order\" INTEGER, title VARCHAR)"
        ))
        conn.execute(text(
            "CREATE TABLE shots (id VARCHAR PRIMARY KEY, scene_id VARCHAR, "
            "\"order\" INTEGER, subject TEXT, image_prompt TEXT, "
            "planned_duration_sec FLOAT, generation_mode VARCHAR, status VARCHAR)"
        ))
        conn.execute(text(
            "CREATE TABLE generation_jobs (id VARCHAR PRIMARY KEY, "
            "shot_id VARCHAR, status VARCHAR, created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE takes (id VARCHAR PRIMARY KEY, shot_id VARCHAR, "
            "job_id VARCHAR, file_path VARCHAR, review_status VARCHAR, "
            "duration_sec FLOAT, width INTEGER, height INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE timeline_items (id VARCHAR PRIMARY KEY, "
            "project_id VARCHAR, shot_id VARCHAR, take_id VARCHAR, "
            "\"order\" INTEGER, in_point_sec FLOAT, out_point_sec FLOAT, "
            "duration_sec FLOAT)"
        ))

        conn.execute(text(
            "INSERT INTO projects (id, title, aspect_ratio, target_resolution, "
            "frame_rate) VALUES ('p1', 'Delivered Project', '16:9', "
            "'1920x1080', 24.0)"
        ))
        conn.execute(text(
            "INSERT INTO scenes (id, project_id, \"order\", title) "
            "VALUES ('sc1', 'p1', 1, 'Opening')"
        ))
        for shot_id, order in (("sh1", 1), ("sh2", 2)):
            conn.execute(text(
                "INSERT INTO shots (id, scene_id, \"order\", subject, "
                "image_prompt, planned_duration_sec, generation_mode, status) "
                f"VALUES ('{shot_id}', 'sc1', {order}, 'a subject', "
                f"'an existing prompt', 4.0, 'image', 'Approved')"
            ))
        conn.execute(text(
            "INSERT INTO generation_jobs (id, shot_id, status, created_at) "
            "VALUES ('j1', 'sh1', 'Completed', '2026-08-01 10:00:00.000000')"
        ))
        conn.execute(text(
            "INSERT INTO takes (id, shot_id, job_id, file_path, review_status, "
            "duration_sec, width, height) VALUES "
            "('t1', 'sh1', 'j1', 'C:/data/generated/t1.png', 'Approved', "
            "4.0, 1920, 1080)"
        ))
        conn.execute(text(
            "INSERT INTO takes (id, shot_id, job_id, file_path, review_status, "
            "duration_sec, width, height) VALUES "
            "('t2', 'sh2', NULL, 'C:/data/generated/t2.png', 'Approved', "
            "4.0, 1920, 1080)"
        ))
        for item_id, shot_id, take_id, order in (
            ("ti1", "sh1", "t1", 0), ("ti2", "sh2", "t2", 1),
        ):
            conn.execute(text(
                "INSERT INTO timeline_items (id, project_id, shot_id, take_id, "
                "\"order\", in_point_sec, out_point_sec, duration_sec) VALUES "
                f"('{item_id}', 'p1', '{shot_id}', '{take_id}', {order}, "
                f"{order * 4.0}, {(order + 1) * 4.0}, 4.0)"
            ))

    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def migrated_session(pre_lineage_db):
    """The legacy database after the app has started against it once."""
    database.init_db()
    session = sessionmaker(bind=pre_lineage_db)()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Nothing is lost
# ---------------------------------------------------------------------------

def test_lineage_columns_are_added_and_every_row_survives(pre_lineage_db):
    assert "content_sha256" not in columns_of(pre_lineage_db, "takes")

    database.init_db()

    assert "content_sha256" in columns_of(pre_lineage_db, "takes")
    assert "take_prompt_revision" in columns_of(pre_lineage_db, "timeline_items")
    with pre_lineage_db.begin() as conn:
        takes = conn.execute(text(
            "SELECT id, file_path, review_status FROM takes ORDER BY id"
        )).all()
        items = conn.execute(text(
            "SELECT id, shot_id, take_id FROM timeline_items ORDER BY id"
        )).all()
    assert [tuple(row) for row in takes] == [
        ("t1", "C:/data/generated/t1.png", "Approved"),
        ("t2", "C:/data/generated/t2.png", "Approved"),
    ]
    assert [tuple(row) for row in items] == [
        ("ti1", "sh1", "t1"), ("ti2", "sh2", "t2"),
    ]


def test_a_legacy_take_serialises_through_todays_schema(migrated_session):
    """NULL is not a value any lineage field is allowed to reach the API as."""
    take = migrated_session.query(Take).filter(Take.id == "t2").one()
    response = TakeResponse.model_validate(take)

    assert response.review_status == "Approved"
    assert response.thumbnail_path == ""
    assert response.codec == ""
    assert response.notes == ""
    assert response.created_at is not None
    # The lineage columns the timeline compares are values, not NULLs.
    assert take.prompt_revision == 0
    assert take.prompt_sha256 == ""
    assert take.content_sha256 == ""
    assert take.reference_image_ids == []
    assert take.reference_sha256s == []


def test_unrecoverable_lineage_is_marked_unverified_not_guessed(migrated_session):
    """A take whose origin is gone is labelled, not given someone else's."""
    revisions.refresh_project(migrated_session, "p1")
    take = migrated_session.query(Take).filter(Take.id == "t2").one()
    shot = take.shot

    assert revisions.is_legacy_lineage(take) is True
    assert revisions.take_lineage_state(take, shot) == revisions.LINEAGE_UNVERIFIED
    # It is emphatically not passed off as matching the current shot.
    assert take.content_sha256 != shot.content_sha256


def test_timeline_items_keep_revision_columns_that_are_not_null(migrated_session):
    items = migrated_session.query(TimelineItem).order_by(TimelineItem.order).all()
    assert [item.take_prompt_revision for item in items] == [0, 0]
    assert all(item.shot_prompt_revision is not None for item in items)


# ---------------------------------------------------------------------------
# The cut survives the upgrade
# ---------------------------------------------------------------------------

def test_the_auto_build_still_places_legacy_approved_takes(migrated_session):
    """This is the regression: matching on NULL lineage placed nothing at all."""
    built = timeline_service.build_timeline_from_approved_takes(
        migrated_session, "p1"
    )

    assert [item["shot_id"] for item in built] == ["sh1", "sh2"]
    assert [item["take_id"] for item in built] == ["t1", "t2"]


def test_a_legacy_cut_is_reported_as_unverified_rather_than_clean(migrated_session):
    manifest = timeline_service.get_timeline_manifest(migrated_session, "p1")

    codes = [warning["code"] for warning in manifest["warnings"]]
    assert "legacy_take_lineage" in codes
    # Unverified is not stale, so the pipeline has not failed - but the cut
    # must not claim to meet the delivery spec either.
    assert manifest["delivery_validation"] == {
        "pipeline_pass": True,
        "delivery_spec_pass": False,
    }


def test_a_legacy_timeline_is_not_refused_as_stale(migrated_session):
    """The strict read is what every export and the render go through."""
    manifest = timeline_service.get_timeline_manifest(
        migrated_session, "p1", strict_lineage=True
    )
    assert manifest["item_count"] == 2


def test_an_empty_derived_build_never_replaces_a_real_timeline(migrated_session):
    """The failure mode this whole fix exists for: delete, then save nothing."""
    with pytest.raises(timeline_service.EmptyTimelineReplacementError):
        timeline_service.save_timeline_items(
            migrated_session, "p1", [], allow_empty_replacement=False
        )

    remaining = migrated_session.query(TimelineItem).all()
    assert {item.id for item in remaining} == {"ti1", "ti2"}


# ---------------------------------------------------------------------------
# ...but the preservation ends where the shot changes
#
# "Unverified" is a claim about a moment: this take predates lineage tracking,
# and the shot has not moved since the migration looked at it. Editing the shot
# ends that. A take that stays permanently unverified is worse than one that
# was never migrated, because it keeps passing as deliverable through approve,
# the timeline and the render while the brief moves away underneath it.
# ---------------------------------------------------------------------------

def _edit_shot(session, shot_id: str) -> None:
    """Change a migrated shot's content, the way a user editing it would."""
    shot = session.query(Shot).filter(Shot.id == shot_id).one()
    shot.image_prompt = "a prompt this take was never generated from"
    session.commit()
    revisions.refresh_project(session, "p1")
    session.refresh(shot)


def test_the_migration_records_the_revision_a_legacy_take_is_unverified_at(
    migrated_session
):
    """Without a baseline there is nothing for a later edit to be measured against."""
    take = migrated_session.query(Take).filter(Take.id == "t2").one()
    revisions.refresh_project(migrated_session, "p1")

    assert revisions.is_legacy_lineage(take) is True
    assert revisions.legacy_baseline_revision(take) == take.shot.prompt_revision


def test_an_edited_shot_makes_its_legacy_take_stale_not_unverified(migrated_session):
    revisions.refresh_project(migrated_session, "p1")
    take = migrated_session.query(Take).filter(Take.id == "t2").one()
    assert revisions.take_lineage_state(take, take.shot) == revisions.LINEAGE_UNVERIFIED

    _edit_shot(migrated_session, "sh2")

    assert revisions.take_lineage_state(take, take.shot) == revisions.LINEAGE_STALE
    # Selective, as ever: the shot that was not touched keeps its take.
    other = migrated_session.query(Take).filter(Take.id == "t1").one()
    assert revisions.take_lineage_state(other, other.shot) == (
        revisions.LINEAGE_UNVERIFIED
    )


def test_a_legacy_take_cannot_be_approved_after_its_shot_changes(migrated_session):
    """Approving is what marks a shot delivered; an edited shot was not."""
    take = migrated_session.query(Take).filter(Take.id == "t2").one()
    take.review_status = "Pending"
    migrated_session.commit()
    _edit_shot(migrated_session, "sh2")

    with pytest.raises(HTTPException) as exc:
        review_router.approve_take("t2", None, migrated_session)

    assert exc.value.status_code == 409
    migrated_session.refresh(take)
    assert take.review_status == "Pending"
    assert take.shot.status != "Approved"


def test_an_edited_shot_drops_its_legacy_take_off_a_rebuilt_cut(migrated_session):
    _edit_shot(migrated_session, "sh2")

    built = timeline_service.build_timeline_from_approved_takes(
        migrated_session, "p1"
    )

    assert [item["shot_id"] for item in built] == ["sh1"]
    reasons = {
        entry["shot_id"]: entry["reason"]
        for entry in timeline_service.timeline_coverage(
            migrated_session, "p1"
        )["missing"]
    }
    assert reasons == {}  # nothing missing yet: the old cut still covers sh2


def test_an_edited_shot_cannot_have_its_legacy_take_placed(migrated_session):
    _edit_shot(migrated_session, "sh2")

    with pytest.raises(timeline_service.StaleTimelineError):
        timeline_service.save_timeline_items(migrated_session, "p1", [{
            "shot_id": "sh2",
            "take_id": "t2",
            "order": 0,
            "duration_sec": 4.0,
        }])

    # The refusal is not allowed to delete the cut it refused to replace.
    assert {item.id for item in migrated_session.query(TimelineItem).all()} == {
        "ti1", "ti2"
    }


def test_an_edited_shot_makes_the_existing_cut_fail_the_strict_read(
    migrated_session
):
    """The strict read is what every export and the render go through."""
    _edit_shot(migrated_session, "sh2")

    manifest = timeline_service.get_timeline_manifest(migrated_session, "p1")
    assert manifest["delivery_validation"]["pipeline_pass"] is False

    with pytest.raises(timeline_service.StaleTimelineError):
        timeline_service.get_timeline_manifest(
            migrated_session, "p1", strict_lineage=True
        )
    with pytest.raises(timeline_service.StaleTimelineError):
        timeline_service.generate_render_plan(migrated_session, "p1")


def test_the_backfill_is_idempotent(pre_lineage_db):
    database.init_db()
    with pre_lineage_db.begin() as conn:
        first = conn.execute(text(
            "SELECT id, prompt_revision, prompt_sha256, content_sha256, lineage "
            "FROM takes ORDER BY id"
        )).all()

    database.init_db()

    with pre_lineage_db.begin() as conn:
        again = conn.execute(text(
            "SELECT id, prompt_revision, prompt_sha256, content_sha256, lineage "
            "FROM takes ORDER BY id"
        )).all()
    assert again == first
