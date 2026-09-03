"""
Database configuration for Content Automation Studio.
Uses synchronous SQLAlchemy with SQLite.
"""

import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import paths

logger = logging.getLogger("cas.database")

# Database path comes from the central paths module so that the DB, imported
# workflows, generated media and exports all live under one runtime tree.
# Handles Windows paths with spaces and Unicode characters.
_DB_PATH = paths.db_path()

# SQLite requires three slashes for an absolute path. On Windows the path
# already starts with a drive letter, so "sqlite:///C:/..." is correct.
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables, apply additive column migrations, then backfill."""
    # Import models so they are registered on Base.metadata before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    backfill_data()


def backfill_data():
    """Populate new columns that an ALTER TABLE could only add as NULL.

    ``ensure_schema`` can add a column but not fill it, so anything a new
    feature needs on existing rows is derived here instead. Imported lazily to
    keep this module free of service-layer imports at module scope.
    """
    from app.services import generation_runs, lineage_backfill

    generation_runs.backfill_legacy_job_defaults(engine)
    generation_runs.backfill_legacy_runs(engine)
    # Runs after the job defaults, so a take can still inherit the lineage its
    # job recorded before those columns are normalised. Shot revision columns
    # are deliberately left alone: the first revision refresh derives them, and
    # deriving is better than guessing.
    lineage_backfill.backfill_take_lineage(engine)
    lineage_backfill.backfill_timeline_lineage(engine)


def ensure_schema():
    """Add columns that exist on the ORM models but not yet in the database.

    ``create_all`` only creates missing tables, so a database written by an
    older build keeps its original columns. This walks every mapped table and
    issues ``ALTER TABLE ... ADD COLUMN`` for anything missing, which is the
    one schema change SQLite supports in place. Enough for the MVP's additive
    schema evolution; a destructive change would need a real migration tool.
    """
    import app.models  # noqa: F401

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                # SQLite rejects a non-constant DEFAULT on ADD COLUMN, so new
                # columns are added nullable and backfilled by the app layer.
                conn.exec_driver_sql(ddl)
                logger.info("Schema migration: added %s.%s", table.name, column.name)
