"""A style's name is for the person reading the list, not for the model.

Starting an episode under a channel copies the channel's visual bible into the
episode's own Story Bible, and named that style after the channel so a project
with two of them could be told apart. It put the name in `medium`, which is a
prompt field: the compiler prepends it, so every image this application
generated for that channel began with the words "ODDVERSE house look".

A model given that draws it. A delivery label in the last shot of an episode
came back with ODDVERSE printed across the top of it, in a house style whose
negative prompt says "text, logo, watermark" - the model was not disobeying,
it was reading the brief. The channel's name was in the brief.

So the label is stored apart from the prompt fields, and `medium` says what
medium the pictures are in.
"""

from app.models import Style
from app.services import channels, prompt_context


def _channel(db):
    return channels.create_channel(db, {
        "name": "ODDVERSE",
        "visual_style": "Grounded documentary realism, muted neutral tones.",
        "negative_prompt": "text, logo, watermark",
        "camera_language": "Establishing, medium, detail, reveal.",
        "pillars": [{"key": "strange_files", "name": "STRANGE FILES"}],
        "hooks": [{"key": "H04", "name": "Discovery"}],
    })


def test_the_channel_name_does_not_reach_the_prompt(db_session):
    channel = _channel(db_session)

    project = channels.start_episode(db_session, channel, {
        "title": "The Extra Room", "pillar": "strange_files", "hook_type": "H04",
    })

    style = db_session.query(Style).filter(Style.project_id == project.id).one()
    for field in ("medium", "genre", "visual_keywords", "camera_language",
                  "palette", "lighting_rules"):
        assert "ODDVERSE" not in (getattr(style, field) or ""), field


def test_the_style_still_says_which_channel_it_came_from(db_session):
    """The reason it was named after the channel in the first place. A project
    with two styles has to say which is which."""
    channel = _channel(db_session)

    project = channels.start_episode(db_session, channel, {"title": "Episode"})

    style = db_session.query(Style).filter(Style.project_id == project.id).one()
    assert "ODDVERSE" in (style.label or "")


def test_the_medium_says_what_medium_the_pictures_are_in(db_session):
    channel = _channel(db_session)

    project = channels.start_episode(db_session, channel, {"title": "Episode"})

    style = db_session.query(Style).filter(Style.project_id == project.id).one()
    assert style.medium
    assert "house look" not in style.medium


def test_a_label_a_person_typed_is_still_kept_out_of_the_prompt(
    db_session, sample_project, sample_scene,
):
    """Not only the copied style. Whatever the label says, it is not a brief."""
    from app.models import Shot
    import uuid

    db_session.add(Style(
        id=str(uuid.uuid4()), project_id=sample_project.id,
        label="Do not draw these words",
        medium="live-action documentary photography",
        visual_keywords="muted neutral tones",
    ))
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image", image_prompt="An empty hallway.",
    )
    db_session.add(shot)
    db_session.commit()

    compiled = prompt_context.compile_for_shot(db_session, shot).compiled

    assert "Do not draw these words" not in compiled.positive_prompt
    assert "muted neutral tones" in compiled.positive_prompt


def test_a_style_written_before_labels_existed_still_reads(
    client, db_session, sample_project,
):
    """ADD COLUMN can only be NULL, so every style older than the label has
    one. A response model declaring `str = ""` does not coerce that."""
    from sqlalchemy import text
    import uuid

    style = Style(
        id=str(uuid.uuid4()), project_id=sample_project.id,
        medium="live-action documentary photography",
    )
    db_session.add(style)
    db_session.commit()
    db_session.execute(
        text("UPDATE styles SET label = NULL WHERE id = :id"), {"id": style.id}
    )
    db_session.commit()

    response = client.get(f"/api/projects/{sample_project.id}/styles")

    assert response.status_code == 200, response.text
    assert response.json()[0]["label"] == ""
