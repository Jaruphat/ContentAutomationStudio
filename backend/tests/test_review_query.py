"""Polling Review must not issue one query per scene."""
from sqlalchemy import event

from app.models import Scene, Shot, Take
from app.routers.review import list_project_takes


def test_review_query_count_is_constant_and_shots_are_named(db_session, sample_project):
    for i in range(8):
        scene = Scene(project_id=sample_project.id, title=f"Scene {i+1}", order=i+1)
        db_session.add(scene)
        db_session.flush()
        shot = Shot(scene_id=scene.id, order=1, shot_type="Close-up")
        db_session.add(shot)
        db_session.flush()
        db_session.add(Take(shot_id=shot.id, file_path="test.png"))
    db_session.commit()
    pid = sample_project.id
    selects = []
    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        takes = list_project_takes(pid, run=None, db=db_session)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(takes) == 8
    assert all("Close-up" in take.shot_label for take in takes)
    assert len(selects) == 2  # project existence, then the joined take query
