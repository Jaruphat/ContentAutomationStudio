"""Rows written before a column existed still have to be readable.

Schema evolution here is `ALTER TABLE ... ADD COLUMN`, which SQLite can only
do as NULL - the app layer backfills what it can, and everything else stays
NULL on every row that predates the column. That is fine in the database and
fatal at the API boundary: a response model declaring `scene_role: str = ""`
does not coerce None to "", it fails validation, and FastAPI turns that into a
500 on a plain GET.

Found the hard way. Adding `subject_motion` and `camera_motion` made every
shot created before that moment unreadable and unsavable - a production run
stopped on a shot it had generated an hour earlier, with no message beyond
"Internal Server Error".

A default is not a fallback. These tests hold the response models to coercing
the null, because the alternative is that every column added from here breaks
every project made before it.
"""

import uuid

import pytest
from sqlalchemy import text

from app.models import Project, Scene, Shot

#: Columns added by ALTER TABLE after rows already existed. Each is NULL on
#: every row older than it, and each is declared with a non-null type.
NULLABLE_ON_OLD_SHOTS = (
    "scene_role", "include_in_cut", "emphasis_text",
    "subject_motion", "camera_motion", "audio_mode", "audio_gain_db",
)
NULLABLE_ON_OLD_PROJECTS = (
    "channel_id", "pillar", "hook_type", "ending_type", "premise",
    "music_path", "music_gain_db", "tail_black_frames",
)


def _null_out(db, table: str, row_id: str, columns) -> None:
    """Put a row back into the state an older build left it in."""
    assignments = ", ".join(f"{name} = NULL" for name in columns)
    db.execute(text(f"UPDATE {table} SET {assignments} WHERE id = :id"),
               {"id": row_id})
    db.commit()


def test_a_shot_older_than_its_columns_can_still_be_read(
    client, db_session, sample_project, sample_scene,
):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", video_prompt="x",
    )
    db_session.add(shot)
    db_session.commit()
    _null_out(db_session, "shots", shot.id, NULLABLE_ON_OLD_SHOTS)

    response = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots"
    )

    assert response.status_code == 200, response.text
    body = response.json()[0]
    assert body["scene_role"] == ""
    assert body["subject_motion"] == ""
    assert body["include_in_cut"] is True


def test_a_shot_older_than_its_columns_can_still_be_edited(
    client, db_session, sample_project, sample_scene,
):
    """The failure that stopped a production run: the shot had been generated
    an hour earlier and could not be given a caption."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", video_prompt="x",
    )
    db_session.add(shot)
    db_session.commit()
    _null_out(db_session, "shots", shot.id, NULLABLE_ON_OLD_SHOTS)

    response = client.put(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots/{shot.id}",
        json={"emphasis_text": "IT WAS HIM.", "dialogue": "was him."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["emphasis_text"] == "IT WAS HIM."


def test_a_project_older_than_its_columns_can_still_be_read(
    client, db_session, sample_project,
):
    _null_out(db_session, "projects", sample_project.id, NULLABLE_ON_OLD_PROJECTS)

    response = client.get(f"/api/projects/{sample_project.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pillar"] == ""
    assert body["channel_id"] is None


@pytest.mark.parametrize("column", NULLABLE_ON_OLD_SHOTS)
def test_each_added_shot_column_survives_being_null_on_its_own(
    client, db_session, sample_project, sample_scene, column,
):
    """One at a time, so a failure names the column rather than the batch."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", video_prompt="x",
    )
    db_session.add(shot)
    db_session.commit()
    _null_out(db_session, "shots", shot.id, [column])

    response = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots"
    )

    assert response.status_code == 200, f"{column}: {response.text}"


def test_the_render_reads_a_shot_with_null_audio_direction(
    db_session, sample_project, sample_scene,
):
    """Not only the API. The renderer reads these columns too, and a None
    there would be a crash in the middle of an overnight assembly."""
    from app.services import render_service

    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", video_prompt="x",
    )
    db_session.add(shot)
    db_session.commit()
    _null_out(db_session, "shots", shot.id, ["audio_mode", "audio_gain_db"])
    db_session.expire_all()

    from app.models import Take

    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="clip.mp4",
        review_status="Approved", width=64, height=64,
    )
    db_session.add(take)
    db_session.commit()

    plan = render_service._shot_audio_direction(db_session, [({}, take)])

    assert plan == [(False, 0.0)]
