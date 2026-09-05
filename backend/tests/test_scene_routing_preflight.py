"""Scene-routing advice reaches the user before the render, not after.

The composition problem this advice describes is invisible until twenty-three
clips are watched in a row, by which point the GPU time is spent. Preflight is
the last screen before that spend, so it is where the advice belongs.

It is advice, though, and the trade it describes is real - the fast route is
why a three-minute film is an overnight job. So it appears as a warning that
never stops a run, and it is aggregated: the same sentence repeated for every
shot in a scene is noise nobody reads to the end of.
"""

import uuid

from app.models import CharacterSet, CharacterSetVersion, Shot, Workflow
from app.services import job_payload


def _r2v_workflow(db, sample_workflow_json):
    from app.services import workflow_registry

    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json,
        name="H3 reference to video",
        purpose="video",
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "10", "field": "image"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    workflow.validation_status = "valid"
    db.add(workflow)
    db.commit()
    return workflow


def _cast(db, project):
    character_set = CharacterSet(
        id=str(uuid.uuid4()), project_id=project.id, name="The sweeper",
    )
    db.add(character_set)
    db.flush()
    version = CharacterSetVersion(
        id=str(uuid.uuid4()), character_set_id=character_set.id,
        project_id=project.id, version=1, status="Approved",
    )
    db.add(version)
    character_set.approved_version_id = version.id
    db.commit()
    return character_set


def _video_shot(db, scene, order, workflow, character_set):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="video", video_prompt="a boy sweeps a rooftop",
        workflow_preset_id=workflow.id, status="Ready",
        character_set_ids=[character_set.id],
    )
    db.add(shot)
    db.commit()
    return shot


def test_preflight_warns_once_about_every_scene_opener_on_the_fast_route(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    workflow = _r2v_workflow(db_session, sample_workflow_json)
    character_set = _cast(db_session, sample_project)
    opener = _video_shot(db_session, sample_scene, 1, workflow, character_set)
    _video_shot(db_session, sample_scene, 2, workflow, character_set)

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    # "composed" also appears in the continuation advice, which is a
    # different, equally correct warning about shot 2; match the opener's.
    composition = [w for w in body["warnings"] if "opens its scene" in w.lower()]
    assert len(composition) == 1, (
        f"one aggregated warning, not one per shot: {body['warnings']}"
    )
    assert "key image" in composition[0].lower(), "it has to name the way out"
    assert str(opener.order) in composition[0], "and which shots it is about"


def test_the_advice_never_appears_as_a_shot_blocker(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    """A composition trade the user may have chosen deliberately cannot stop
    a run they configured."""
    workflow = _r2v_workflow(db_session, sample_workflow_json)
    character_set = _cast(db_session, sample_project)
    shot = _video_shot(db_session, sample_scene, 1, workflow, character_set)

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    for entry in body["issues"]:
        if entry["shot_id"] == shot.id:
            assert not any(
                "opens its scene" in issue.lower() for issue in entry["issues"]
            )


def test_a_project_the_advice_does_not_apply_to_is_left_alone(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    """No cast bound, so nothing borrows a composition and nothing is said."""
    workflow = _r2v_workflow(db_session, sample_workflow_json)
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", video_prompt="an empty rooftop at dawn",
        workflow_preset_id=workflow.id, status="Ready",
    )
    db_session.add(shot)
    db_session.commit()

    body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

    assert not [w for w in body["warnings"] if "opens its scene" in w.lower()]
