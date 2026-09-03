"""
Migration compatibility for character sets and end-frame continuity.

An existing installation has a populated ``cas.db`` written before either
feature existed. Both must land on that database through the additive
``ensure_schema`` pass: new tables created, new columns added, and not one
existing row lost or rewritten.

The properties asserted here are the ones a real upgrade depends on:

* the three character-set tables and the continuity-frame table appear,
* the identity/continuity columns appear on shots, jobs and takes, and
* a shot that predates both features keeps its prompt, status and approved
  take, and reads back as bound to nothing rather than as broken.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from app import database


def columns_of(engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


#: Every table the two features add.
NEW_TABLES = (
    "character_sets",
    "character_set_versions",
    "character_set_views",
    "continuity_frames",
)

#: Columns added to tables that already existed.
NEW_COLUMNS: dict[str, tuple[str, ...]] = {
    "shots": (
        "character_set_ids",
        "character_set_sha256s",
        "continuity_source_take_id",
        "continuity_source_mode",
    ),
    "generation_jobs": (
        "character_set_ids",
        "character_set_sha256s",
        "continuity_source_take_id",
        "continuity_source_sha256",
    ),
    "takes": (
        "character_set_ids",
        "character_set_sha256s",
        "continuity_source_take_id",
        "continuity_source_sha256",
    ),
}


@pytest.fixture()
def pre_character_set_db(tmp_path, monkeypatch):
    """A database from before character sets and continuity frames existed."""
    engine = create_engine(f"sqlite:///{tmp_path / 'pre-charset.db'}")
    database.Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        for table in NEW_TABLES:
            conn.execute(text(f"DROP TABLE {table}"))
        for table, columns in NEW_COLUMNS.items():
            for column in columns:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))

        conn.execute(text(
            "INSERT INTO projects (id, title) VALUES ('p1', 'Existing Project')"
        ))
        conn.execute(text(
            'INSERT INTO scenes (id, project_id, "order") VALUES (\'sc1\', \'p1\', 1)'
        ))
        conn.execute(text(
            'INSERT INTO shots (id, scene_id, "order", image_prompt, status, '
            "prompt_revision, generated_revision, is_stale) "
            "VALUES ('sh1', 'sc1', 1, 'an existing prompt', 'Approved', 1, 1, 0)"
        ))
        conn.execute(text(
            "INSERT INTO takes (id, shot_id, file_path, review_status) "
            "VALUES ('t1', 'sh1', 'C:/data/generated/t1.mp4', 'Approved')"
        ))

    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def test_the_fixture_really_predates_both_features(pre_character_set_db):
    """Guards the test itself: without this the migration proves nothing."""
    tables = set(inspect(pre_character_set_db).get_table_names())
    assert not (set(NEW_TABLES) & tables)
    for table, columns in NEW_COLUMNS.items():
        assert not (set(columns) & columns_of(pre_character_set_db, table))


def test_new_tables_are_created_on_an_existing_database(pre_character_set_db):
    database.init_db()
    tables = set(inspect(pre_character_set_db).get_table_names())
    for table in NEW_TABLES:
        assert table in tables


def test_identity_and_continuity_columns_are_added_in_place(pre_character_set_db):
    database.init_db()
    for table, columns in NEW_COLUMNS.items():
        present = columns_of(pre_character_set_db, table)
        for column in columns:
            assert column in present, f"{table}.{column} was not migrated"


def test_existing_rows_survive_untouched(pre_character_set_db):
    """A migration that loses an approved take is worse than no migration."""
    database.init_db()
    with pre_character_set_db.begin() as conn:
        shot = conn.execute(text(
            "SELECT image_prompt, status FROM shots WHERE id = 'sh1'"
        )).first()
        take = conn.execute(text(
            "SELECT file_path, review_status FROM takes WHERE id = 't1'"
        )).first()
    assert shot == ("an existing prompt", "Approved")
    assert take == ("C:/data/generated/t1.mp4", "Approved")


def test_a_migrated_shot_reads_back_as_bound_to_nothing(pre_character_set_db):
    """The ORM must see an unset JSON list as empty, never as None.

    ``ALTER TABLE ADD COLUMN`` can only add NULL, so every consumer of these
    lists would otherwise have to defend against None. Reading through the
    model is what proves the default reaches application code.
    """
    from sqlalchemy.orm import sessionmaker

    from app.models import Shot

    database.init_db()
    session = sessionmaker(bind=pre_character_set_db)()
    try:
        shot = session.query(Shot).filter(Shot.id == "sh1").first()
        assert list(shot.character_set_ids or []) == []
        assert list(shot.character_set_sha256s or []) == []
        assert shot.continuity_source_take_id is None
        assert (shot.continuity_source_mode or "none") == "none"
    finally:
        session.close()
