"""
Migration compatibility for the Visual Reference Bible and revision columns.

An existing installation has a populated ``cas.db``. Adding reference sheets,
reference images and per-shot revision tracking must land on that database
without a rebuild and without losing a row - which is the whole point of the
additive ``ensure_schema`` pass.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from app import database


def columns_of(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


@pytest.fixture()
def pre_reference_db(tmp_path, monkeypatch):
    """A database from before the Reference Bible existed, with real rows."""
    engine = create_engine(f"sqlite:///{tmp_path / 'pre-reference.db'}")
    database.Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE reference_images"))
        conn.execute(text("DROP TABLE reference_sheets"))
        for column in (
            "prompt_revision", "prompt_sha256", "content_sha256",
            "reference_sha256s", "generated_revision",
            "generated_content_sha256", "is_stale",
        ):
            conn.execute(text(f"ALTER TABLE shots DROP COLUMN {column}"))
        for column in (
            "prompt_revision", "prompt_sha256", "content_sha256",
            "reference_image_ids", "reference_sha256s", "reference_provenance",
        ):
            conn.execute(text(f"ALTER TABLE generation_jobs DROP COLUMN {column}"))
        for column in (
            "prompt_revision", "prompt_sha256", "content_sha256",
            "reference_image_ids", "reference_sha256s", "lineage",
        ):
            conn.execute(text(f"ALTER TABLE takes DROP COLUMN {column}"))
        for column in ("take_prompt_revision", "shot_prompt_revision"):
            conn.execute(text(f"ALTER TABLE timeline_items DROP COLUMN {column}"))

        conn.execute(text(
            "INSERT INTO projects (id, title) VALUES ('p1', 'Existing Project')"
        ))
        conn.execute(text(
            "INSERT INTO scenes (id, project_id, \"order\") VALUES ('sc1', 'p1', 1)"
        ))
        conn.execute(text(
            "INSERT INTO shots (id, scene_id, \"order\", image_prompt, status) "
            "VALUES ('sh1', 'sc1', 1, 'an existing prompt', 'Approved')"
        ))
        conn.execute(text(
            "INSERT INTO takes (id, shot_id, file_path, review_status) "
            "VALUES ('t1', 'sh1', 'C:/data/generated/t1.png', 'Approved')"
        ))

    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def test_reference_tables_are_created_on_an_existing_database(pre_reference_db):
    assert "reference_sheets" not in inspect(pre_reference_db).get_table_names()

    database.init_db()

    tables = inspect(pre_reference_db).get_table_names()
    assert "reference_sheets" in tables
    assert "reference_images" in tables


def test_revision_columns_are_added_to_existing_tables(pre_reference_db):
    database.ensure_schema()

    assert {"prompt_revision", "content_sha256", "is_stale"} <= columns_of(
        pre_reference_db, "shots"
    )
    assert {"reference_image_ids", "reference_provenance"} <= columns_of(
        pre_reference_db, "generation_jobs"
    )
    assert {"lineage", "prompt_revision"} <= columns_of(pre_reference_db, "takes")
    assert {"take_prompt_revision", "shot_prompt_revision"} <= columns_of(
        pre_reference_db, "timeline_items"
    )


def test_existing_rows_survive_the_migration(pre_reference_db):
    database.init_db()

    with pre_reference_db.begin() as conn:
        shot = conn.execute(text(
            "SELECT image_prompt, status, prompt_revision, is_stale "
            "FROM shots WHERE id = 'sh1'"
        )).one()
        take = conn.execute(text(
            "SELECT file_path, review_status FROM takes WHERE id = 't1'"
        )).one()

    assert shot[0] == "an existing prompt"
    assert shot[1] == "Approved"
    # New columns backfill as NULL; the app layer reads that as "not yet known"
    # and the first revision refresh fills them in.
    assert shot[2] is None
    assert shot[3] is None
    assert take[0] == "C:/data/generated/t1.png"
    assert take[1] == "Approved"


def test_migration_is_idempotent(pre_reference_db):
    database.init_db()
    first = columns_of(pre_reference_db, "shots")
    database.init_db()
    assert columns_of(pre_reference_db, "shots") == first


def test_a_migrated_shot_gets_a_revision_on_first_refresh(pre_reference_db):
    """Null revision columns must not break the first pass over old data."""
    from sqlalchemy.orm import sessionmaker

    from app.models import Shot
    from app.services import revisions

    database.init_db()
    session = sessionmaker(bind=pre_reference_db)()
    try:
        revisions.refresh_project(session, "p1")
        shot = session.query(Shot).filter(Shot.id == "sh1").first()
        assert shot.prompt_revision == 1
        assert shot.content_sha256
        assert shot.is_stale is False
    finally:
        session.close()


def test_reference_directory_is_created_lazily(tmp_path, monkeypatch):
    """A migrated installation has no references directory until it needs one."""
    from app import paths

    monkeypatch.setenv("CAS_DATA_DIR", str(tmp_path / "migrated"))
    created = paths.references_dir("p1")
    import os

    assert os.path.isdir(created)
    assert os.path.commonpath([paths.data_dir(), created]) == paths.data_dir()
