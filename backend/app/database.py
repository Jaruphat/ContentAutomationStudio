"""
Database configuration for Content Automation Studio.
Uses synchronous SQLAlchemy with SQLite.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import paths

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
    """Create all tables defined by ORM models."""
    # Import models so they are registered on Base.metadata before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
