"""Migration compatibility for generation runs.

An existing installation has jobs and takes that predate the run concept. The
migration must be purely additive: the ``generation_runs`` table appears, the
``run_id`` columns appear, every existing job and take survives untouched, and
the backfill gives the old work a run identity so it still shows up in history
rather than vanishing from the Generate page.
"""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app import database
from app.models import GenerationJob
from app.schemas import GenerationJobResponse


def columns_of(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


@pytest.fixture()
def pre_run_db(tmp_path, monkeypatch):
    """A database from before generation runs existed, with real rows.

    Two Generate presses, three seconds apart: two jobs then one, which is the
    shape the backfill has to recover without any recorded run.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'pre-run.db'}")

    # Build the small schema an actual pre-run installation had. Recreating it
    # explicitly is more faithful than creating today's schema and trying to
    # DROP a foreign-key column, an operation SQLite intentionally rejects.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE projects (id VARCHAR PRIMARY KEY, title VARCHAR)"
        ))
        conn.execute(text(
            "CREATE TABLE scenes (id VARCHAR PRIMARY KEY, project_id VARCHAR, "
            "\"order\" INTEGER, title VARCHAR)"
        ))
        conn.execute(text(
            "CREATE TABLE shots (id VARCHAR PRIMARY KEY, scene_id VARCHAR, "
            "\"order\" INTEGER, image_prompt TEXT, status VARCHAR)"
        ))
        conn.execute(text(
            "CREATE TABLE generation_jobs (id VARCHAR PRIMARY KEY, "
            "shot_id VARCHAR, status VARCHAR, created_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE takes (id VARCHAR PRIMARY KEY, shot_id VARCHAR, "
            "job_id VARCHAR, file_path VARCHAR, review_status VARCHAR)"
        ))

        conn.execute(text(
            "INSERT INTO projects (id, title) VALUES ('p1', 'Existing Project')"
        ))
        conn.execute(text(
            "INSERT INTO scenes (id, project_id, \"order\", title) "
            "VALUES ('sc1', 'p1', 1, 'Opening')"
        ))
        for shot_id, order in (("sh1", 1), ("sh2", 2)):
            conn.execute(text(
                "INSERT INTO shots (id, scene_id, \"order\", image_prompt, status) "
                f"VALUES ('{shot_id}', 'sc1', {order}, 'an existing prompt', 'Approved')"
            ))
        # First press: two jobs within the same second.
        conn.execute(text(
            "INSERT INTO generation_jobs (id, shot_id, status, created_at) "
            "VALUES ('j1', 'sh1', 'Completed', '2026-08-01 10:00:00.100000')"
        ))
        conn.execute(text(
            "INSERT INTO generation_jobs (id, shot_id, status, created_at) "
            "VALUES ('j2', 'sh2', 'Completed', '2026-08-01 10:00:00.400000')"
        ))
        # Second press: minutes later.
        conn.execute(text(
            "INSERT INTO generation_jobs (id, shot_id, status, created_at) "
            "VALUES ('j3', 'sh1', 'Failed', '2026-08-01 10:07:00.000000')"
        ))
        conn.execute(text(
            "INSERT INTO takes (id, shot_id, job_id, file_path, review_status) "
            "VALUES ('t1', 'sh1', 'j1', 'C:/data/generated/t1.png', 'Approved')"
        ))
        conn.execute(text(
            "INSERT INTO takes (id, shot_id, job_id, file_path, review_status) "
            "VALUES ('t2', 'sh2', 'j2', 'C:/data/generated/t2.png', 'Pending')"
        ))

    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def test_run_table_and_columns_are_added_to_an_existing_database(pre_run_db):
    assert "generation_runs" not in inspect(pre_run_db).get_table_names()

    database.init_db()

    assert "generation_runs" in inspect(pre_run_db).get_table_names()
    assert "run_id" in columns_of(pre_run_db, "generation_jobs")
    assert "run_id" in columns_of(pre_run_db, "takes")


def test_every_existing_job_and_take_survives_the_migration(pre_run_db):
    database.init_db()

    with pre_run_db.begin() as conn:
        jobs = conn.execute(text(
            "SELECT id, shot_id, status FROM generation_jobs ORDER BY id"
        )).all()
        takes = conn.execute(text(
            "SELECT id, file_path, review_status FROM takes ORDER BY id"
        )).all()

    assert [tuple(row) for row in jobs] == [
        ("j1", "sh1", "Completed"),
        ("j2", "sh2", "Completed"),
        ("j3", "sh1", "Failed"),
    ]
    assert [tuple(row) for row in takes] == [
        ("t1", "C:/data/generated/t1.png", "Approved"),
        ("t2", "C:/data/generated/t2.png", "Pending"),
    ]


def test_legacy_jobs_are_grouped_into_the_runs_they_were_created_in(pre_run_db):
    database.init_db()

    with pre_run_db.begin() as conn:
        runs = conn.execute(text(
            "SELECT id, project_id, kind, sequence, requested_job_count "
            "FROM generation_runs ORDER BY sequence"
        )).all()
        job_runs = dict(conn.execute(text(
            "SELECT id, run_id FROM generation_jobs"
        )).all())

    assert len(runs) == 2
    assert [row[1] for row in runs] == ["p1", "p1"]
    assert [row[2] for row in runs] == ["migrated", "migrated"]
    assert [row[3] for row in runs] == [1, 2]
    assert [row[4] for row in runs] == [2, 1]
    # The two jobs created together share a run; the later one does not.
    assert job_runs["j1"] == job_runs["j2"]
    assert job_runs["j3"] != job_runs["j1"]
    assert all(job_runs.values())


def test_legacy_takes_inherit_the_run_of_the_job_that_made_them(pre_run_db):
    database.init_db()

    with pre_run_db.begin() as conn:
        take_runs = dict(conn.execute(text("SELECT id, run_id FROM takes")).all())
        job_runs = dict(conn.execute(text(
            "SELECT id, run_id FROM generation_jobs"
        )).all())

    assert take_runs["t1"] == job_runs["j1"]
    assert take_runs["t2"] == job_runs["j2"]


def test_the_backfill_is_idempotent(pre_run_db):
    database.init_db()
    with pre_run_db.begin() as conn:
        first = conn.execute(text(
            "SELECT id, run_id FROM generation_jobs ORDER BY id"
        )).all()

    database.init_db()

    with pre_run_db.begin() as conn:
        again = conn.execute(text(
            "SELECT id, run_id FROM generation_jobs ORDER BY id"
        )).all()
        run_count = conn.execute(text(
            "SELECT COUNT(*) FROM generation_runs"
        )).scalar()

    assert again == first
    assert run_count == 2


def test_a_migrated_run_summarises_without_a_recorded_shot_list(pre_run_db):
    """Backfilled runs must read back through the same summary path as new ones."""
    from app.services import generation_runs

    database.init_db()
    session = sessionmaker(bind=pre_run_db)()
    try:
        runs = generation_runs.list_runs(session, "p1")
        summary = generation_runs.summarise_run(session, runs[-1])
    finally:
        session.close()

    assert summary["total_jobs"] == 2
    assert summary["completed"] == 2
    assert summary["terminal"] is True
    assert {entry["shot_name"] for entry in summary["jobs"]} == {"Shot 1", "Shot 2"}
    assert {entry["scene_name"] for entry in summary["jobs"]} == {"Opening"}


def test_legacy_job_gets_non_null_response_defaults(pre_run_db):
    """A sparse real legacy row must serialize through today's API schema."""
    database.init_db()
    session = sessionmaker(bind=pre_run_db)()
    try:
        job = session.query(GenerationJob).filter(GenerationJob.id == "j1").one()
        response = GenerationJobResponse.model_validate(job)
    finally:
        session.close()

    assert response.workflow_version == ""
    assert response.workflow_snapshot_path == ""
    assert response.workflow_sha256 == ""
    assert response.parameter_map == {}
    assert response.media_provider_id == "comfyui"
    assert response.media_model == "workflow"
    assert response.request_params == {}
    assert response.usage == {}
    assert response.provenance == {}
    assert response.prompt_revision == 0
    assert response.prompt_sha256 == ""
    assert response.content_sha256 == ""
    assert response.reference_image_ids == []
    assert response.reference_sha256s == []
    assert response.reference_provenance == {}
    assert response.attempts == 0
    assert response.outputs == []

