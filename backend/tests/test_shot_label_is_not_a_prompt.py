"""A shot's name is for the person reading the list, not for the model.

Seen printed on the picture. A shot called "Tomorrow" produced a newspaper
whose masthead read *Tomorrow*; the shot after it, called "The Reveal",
produced a front page headlined *theE IINTD REVEAL*. The name had been put in
`shot_type`, which the compiler sends as the framing term - the field means
"wide shot", "medium close-up", "over-the-shoulder", and a model handed "The
Reveal" instead has nothing to frame with, so it drew the words.

This is the second field in this application to conflate a name with a brief.
A style's name was in `medium` and got printed onto a delivery label. The same
fix applies: the name lives where no prompt reads it, and the prompt field says
what it is for.

Both are kept because both are needed. A production run naming its shots is
right - "Shot 7" tells nobody which one broke - and the framing term is a real
part of the prompt. They are simply not the same string.
"""

import uuid

from sqlalchemy import text

from app.models import Shot
from app.services import generation_runs, prompt_context


def _shot(db, scene, **fields) -> Shot:
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=7,
        generation_mode="image", image_prompt="A folded newspaper at night.",
        **fields,
    )
    db.add(shot)
    db.commit()
    return shot


def test_a_shots_name_never_reaches_the_prompt(db_session, sample_scene):
    shot = _shot(db_session, sample_scene, label="The Reveal",
                 shot_type="extreme close-up")

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "The Reveal" not in compiled.positive_prompt
    assert "extreme close-up" in compiled.positive_prompt


def test_the_framing_term_still_reaches_the_prompt(db_session, sample_scene):
    """The half that is a brief. Removing the name must not remove this."""
    shot = _shot(db_session, sample_scene, shot_type="wide establishing shot")

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "wide establishing shot" in compiled.positive_prompt


def test_a_named_shot_is_called_by_its_name_on_screen(db_session, sample_scene):
    """The reason names exist. "Shot 7" tells nobody which one broke."""
    shot = _shot(db_session, sample_scene, label="The Reveal",
                 shot_type="extreme close-up")

    assert "The Reveal" in generation_runs.shot_display_name(shot)


def test_a_shot_with_no_name_still_describes_itself(db_session, sample_scene):
    shot = _shot(db_session, sample_scene, shot_type="extreme close-up")

    name = generation_runs.shot_display_name(shot)
    assert "Shot 7" in name
    assert "extreme close-up" in name


def test_a_shot_written_before_names_existed_reads_back(
    client, db_session, sample_project, sample_scene,
):
    """ADD COLUMN can only be NULL, so every shot older than this carries
    None, and a response model declaring `str = ""` does not coerce it."""
    shot = _shot(db_session, sample_scene, shot_type="wide shot")
    db_session.execute(
        text("UPDATE shots SET label = NULL WHERE id = :id"), {"id": shot.id}
    )
    db_session.commit()

    response = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots"
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["label"] == ""


def test_naming_a_shot_does_not_invalidate_what_it_generated(
    client, db_session, sample_project, sample_scene,
):
    """A name is not a brief, so writing one cannot make a generated frame
    stale. If it could, renaming a shot would cost a render."""
    from app.services import revisions

    shot = _shot(db_session, sample_scene, shot_type="wide shot")
    # A shot written straight into the database has no digest until the
    # project is refreshed; comparing against "" would prove nothing.
    revisions.refresh_project(db_session, sample_project.id)
    before = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots/{shot.id}"
    ).json()

    after = client.put(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots/{shot.id}",
        json={"label": "The Reveal"},
    )

    assert after.status_code == 200, after.text
    assert after.json()["label"] == "The Reveal"
    assert after.json()["content_sha256"] == before["content_sha256"]
