"""A setting that changes the picture has to change the shot's digest.

Workflow constants decide what a graph produces - a guidance scale of 9.0 gives
a different picture from 3.5, from the same prompt, references and seed. That
was measured on a real shot. So a take generated under one set of constants is
not a take of the shot as it stands under another, and the staleness check has
to say so; otherwise an approved frame silently stops matching what the
application would now generate, which is the exact failure `content_sha256`
exists to catch for prompts, workflows and references.

They are hashed only when a workflow actually has them. Every workflow in
every existing project has none, and hashing an empty dict would advance every
shot in every project on the first refresh - marking a whole delivered film
stale to record that nothing had changed.
"""

import uuid

from app.models import Shot, Workflow
from app.services import revisions


def _project_with_workflow(db, sample_project, sample_workflow_json, constants):
    from app.services import job_payload, workflow_registry

    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Edit", purpose="image",
    )
    workflow = Workflow(**record)
    workflow.validation_status = "valid"
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        "samplerCfg": {"nodeId": "3", "field": "cfg"},
    }
    workflow.constants = constants
    db.add(workflow)
    sample_project.default_image_workflow_id = workflow.id
    db.commit()
    return workflow


def _shot(db, scene):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=1,
        generation_mode="image", image_prompt="A narrow hallway at night.",
    )
    db.add(shot)
    db.commit()
    return shot


def test_changing_a_constant_moves_the_shots_content_digest(
    db_session, sample_project, sample_scene, sample_workflow_json,
):
    workflow = _project_with_workflow(
        db_session, sample_project, sample_workflow_json, {"samplerCfg": 3.5},
    )
    shot = _shot(db_session, sample_scene)
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)
    before = shot.content_sha256

    workflow.constants = {"samplerCfg": 9.0}
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    assert before
    assert shot.content_sha256 != before


def test_a_workflow_with_no_constants_hashes_as_it_always_did(
    db_session, sample_project, sample_scene, sample_workflow_json,
):
    """Hashing an empty dict would advance every shot in every existing
    project on the first refresh, to record that nothing had changed."""
    workflow = _project_with_workflow(
        db_session, sample_project, sample_workflow_json, {},
    )
    shot = _shot(db_session, sample_scene)
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)
    before = shot.content_sha256

    workflow.constants = None
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    assert shot.content_sha256 == before


def test_an_approved_take_goes_stale_when_the_constant_changes(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    """The point of the digest. An approved frame that no longer matches what
    would be generated must not stay current."""
    from app.models import Take

    workflow = _project_with_workflow(
        db_session, sample_project, sample_workflow_json, {"samplerCfg": 3.5},
    )
    shot = _shot(db_session, sample_scene)
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)
    db_session.add(Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="C:/tmp/frame.png",
        review_status="Approved", prompt_revision=shot.prompt_revision,
        content_sha256=shot.content_sha256,
    ))
    # What generating actually records on the shot, and what staleness reads.
    shot.generated_revision = shot.prompt_revision
    shot.generated_content_sha256 = shot.content_sha256
    db_session.commit()

    workflow.constants = {"samplerCfg": 9.0}
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    db_session.refresh(shot)

    assert shot.is_stale
