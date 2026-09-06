"""Settings baked into a graph that nothing in the application can reach.

Two shots of an episode were written as close views and came back as the
scene plate's wide view with the subject somewhere inside it. A second, far
more explicit prompt - naming the framing and the door twice - moved neither.
On that workflow the plate, not the prompt, decides the composition.

The parameter that plausibly balances the two is the sampler's guidance scale,
and it sits in the graph as a constant: `SamplerCustom.cfg = 3.5`. There is no
logical field for it, because it is not something a shot decides - it is
something a workflow is configured with. So it could not be changed, and the
hypothesis could not be tested.

A workflow's `constants` are logical-field values fixed for that workflow and
merged into every job it drives. That is enough to make the question
answerable: copy the shot into an experiment, change the number, generate, and
measure. It does not answer it. The point is that it can now be asked.

Two rules make this safe rather than a back door into the payload:

* **A shot's own value wins.** Constants fill in what the request did not say;
  they never overwrite a prompt, a seed or a frame count the shot decided.
* **They are recorded on the job.** A run whose settings are not in its own
  record is a run nobody can reproduce, and reproducibility is the whole
  reason for changing one number at a time.
"""

import uuid

import pytest

from app.models import Shot, Workflow
from app.services import job_payload


def _workflow(db, sample_workflow_json, constants=None) -> Workflow:
    from app.services import workflow_registry

    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json, name="Edit", purpose="image",
    )
    workflow = Workflow(**record)
    workflow.validation_status = "valid"
    workflow.parameter_mapping = {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        "samplerCfg": {"nodeId": "3", "field": "cfg"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    if constants is not None:
        workflow.constants = constants
    db.add(workflow)
    db.commit()
    return workflow


def _shot(db, scene) -> Shot:
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=1, status="Ready",
        generation_mode="image", image_prompt="A narrow hallway at night.",
    )
    db.add(shot)
    db.commit()
    return shot


def test_a_constant_reaches_the_job_that_uses_the_workflow(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    workflow = _workflow(db_session, sample_workflow_json, {"samplerCfg": 6.5})
    sample_project.default_image_workflow_id = workflow.id
    shot = _shot(db_session, sample_scene)
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [shot.id]},
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["parameter_map"]["samplerCfg"] == 6.5


def test_a_constant_never_overwrites_what_the_shot_decided(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    """Constants fill in what the request did not say. A workflow that could
    overwrite a prompt or a seed would make every shot's own settings a
    suggestion."""
    workflow = _workflow(db_session, sample_workflow_json, {
        "samplerCfg": 6.5,
        job_payload.POSITIVE_PROMPT: "a completely different picture",
        job_payload.SEED: 999,
    })
    sample_project.default_image_workflow_id = workflow.id
    shot = _shot(db_session, sample_scene)
    shot.seed_policy = "fixed"
    shot.seed = 42
    db_session.commit()

    job = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [shot.id]},
    ).json()[0]

    assert "narrow hallway" in job["parameter_map"][job_payload.POSITIVE_PROMPT]
    assert job["parameter_map"][job_payload.SEED] == 42
    assert job["parameter_map"]["samplerCfg"] == 6.5


def test_no_constants_changes_nothing(
    client, db_session, sample_project, sample_scene, sample_workflow_json,
):
    workflow = _workflow(db_session, sample_workflow_json)
    sample_project.default_image_workflow_id = workflow.id
    shot = _shot(db_session, sample_scene)
    db_session.commit()

    job = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [shot.id]},
    ).json()[0]

    assert "samplerCfg" not in job["parameter_map"]


def test_constants_are_set_and_read_through_the_mapping_endpoint(
    client, db_session, sample_workflow_json,
):
    workflow = _workflow(db_session, sample_workflow_json)

    updated = client.put(f"/api/workflows/{workflow.id}/mapping", json={
        "parameter_mapping": workflow.parameter_mapping,
        "constants": {"samplerCfg": 7.0},
    })

    assert updated.status_code == 200, updated.text
    assert updated.json()["constants"] == {"samplerCfg": 7.0}


def test_a_constant_for_an_unmapped_field_is_refused(
    client, db_session, sample_workflow_json,
):
    """A value that reaches no node is a setting the user believes is applied.
    Silence there is worse than a refusal."""
    workflow = _workflow(db_session, sample_workflow_json)

    response = client.put(f"/api/workflows/{workflow.id}/mapping", json={
        "parameter_mapping": workflow.parameter_mapping,
        "constants": {"samplerDenoise": 0.6},
    })

    assert response.status_code == 422
    assert "samplerDenoise" in response.text


def test_a_workflow_written_before_constants_reads_back_empty(
    client, db_session, sample_workflow_json,
):
    from sqlalchemy import text

    workflow = _workflow(db_session, sample_workflow_json)
    db_session.execute(
        text("UPDATE workflows SET constants = NULL WHERE id = :id"),
        {"id": workflow.id},
    )
    db_session.commit()

    response = client.get(f"/api/workflows/{workflow.id}")

    assert response.status_code == 200, response.text
    assert response.json()["constants"] == {}


@pytest.mark.parametrize("value", [{"samplerCfg": {"nested": 1}}, {"samplerCfg": [1]}])
def test_a_constant_must_be_a_plain_value(
    client, db_session, sample_workflow_json, value,
):
    """These are written straight into a graph input. A structure there is a
    payload the model cannot read, discovered at submission time."""
    workflow = _workflow(db_session, sample_workflow_json)

    response = client.put(f"/api/workflows/{workflow.id}/mapping", json={
        "parameter_mapping": workflow.parameter_mapping, "constants": value,
    })

    assert response.status_code == 422
