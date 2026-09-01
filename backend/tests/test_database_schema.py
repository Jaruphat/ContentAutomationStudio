"""
Tests for additive schema migration.

``create_all`` only creates missing tables, so a database written by an earlier
build keeps its original columns. ``ensure_schema`` closes that gap, which is
what lets an existing project database survive a model change instead of
failing at the first query.
"""

import os

import pytest
from sqlalchemy import create_engine, inspect, text

from app import database


@pytest.fixture()
def legacy_db(tmp_path, monkeypatch):
    """A file-backed database missing the newer provenance columns."""
    db_file = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_file}")

    database.Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE generation_jobs DROP COLUMN workflow_snapshot_path"))
        conn.execute(text("ALTER TABLE generation_jobs DROP COLUMN workflow_sha256"))

    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def columns_of(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


class TestEnsureSchema:
    def test_adds_missing_columns(self, legacy_db):
        before = columns_of(legacy_db, "generation_jobs")
        assert "workflow_snapshot_path" not in before

        database.ensure_schema()

        after = columns_of(legacy_db, "generation_jobs")
        assert "workflow_snapshot_path" in after
        assert "workflow_sha256" in after

    def test_preserves_existing_rows(self, legacy_db):
        with legacy_db.begin() as conn:
            conn.execute(text(
                "INSERT INTO generation_jobs (id, shot_id, status, attempts) "
                "VALUES ('job-1', 'shot-1', 'Completed', 1)"
            ))

        database.ensure_schema()

        with legacy_db.begin() as conn:
            row = conn.execute(text(
                "SELECT status, workflow_snapshot_path FROM generation_jobs "
                "WHERE id = 'job-1'"
            )).one()
        assert row[0] == "Completed"
        # Backfilled as NULL; the app layer treats that as "no snapshot".
        assert row[1] is None

    def test_is_idempotent(self, legacy_db):
        database.ensure_schema()
        first = columns_of(legacy_db, "generation_jobs")
        database.ensure_schema()
        assert columns_of(legacy_db, "generation_jobs") == first

    def test_no_op_on_current_schema(self, tmp_path, monkeypatch):
        engine = create_engine(f"sqlite:///{tmp_path / 'current.db'}")
        database.Base.metadata.create_all(bind=engine)
        monkeypatch.setattr(database, "engine", engine)

        before = columns_of(engine, "generation_jobs")
        database.ensure_schema()
        assert columns_of(engine, "generation_jobs") == before
        engine.dispose()


class TestPaths:
    def test_data_dir_honours_environment_override(self, tmp_path, monkeypatch):
        from app import paths

        target = tmp_path / "custom data dir" / "ข้อมูล"
        monkeypatch.setenv("CAS_DATA_DIR", str(target))
        resolved = paths.data_dir()

        assert os.path.isdir(resolved)
        assert os.path.normcase(resolved) == os.path.normcase(str(target))

    def test_all_runtime_dirs_share_one_base(self, tmp_path, monkeypatch):
        """The bug this guards against: services resolving the backend
        directory one level too shallow and splitting runtime data across two
        trees."""
        from app import paths

        monkeypatch.setenv("CAS_DATA_DIR", str(tmp_path / "base"))
        base = paths.data_dir()

        for child in (
            paths.workflows_dir(),
            paths.snapshots_dir(),
            paths.generated_dir(),
            paths.exports_dir(),
            paths.exports_dir("project-123"),
            os.path.dirname(paths.db_path()),
        ):
            assert os.path.commonpath([base, child]) == base
