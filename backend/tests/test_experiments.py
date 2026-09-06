"""An experiment owns its inputs and cannot mutate the source production."""
import hashlib
from pathlib import Path

import pytest

from app import paths
from app.models import GenerationJob, Project, ReferenceImage, ReferenceSheet, Scene, Shot, Workflow
from app.services import experiments, prompt_context, revisions


def test_experiment_freezes_prompt_and_owns_reference_bytes(client, db_session, sample_shot, sample_style, sample_project):
    source = Path(paths.references_dir(sample_project.id)) / "source.png"
    source.write_bytes(b"owned reference bytes")
    sheet = ReferenceSheet(project_id=sample_project.id, name="Source", kind="location")
    db_session.add(sheet)
    db_session.flush()
    ref = ReferenceImage(project_id=sample_project.id, sheet_id=sheet.id,
        role="canonical", file_path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_filename="source.png", stored_filename="source.png", mime_type="image/png", size_bytes=source.stat().st_size)
    db_session.add(ref)
    db_session.flush()
    sample_shot.reference_asset_ids = [ref.id]
    workflow = Workflow(name="Reference workflow", purpose="image",
        parameter_mapping={"referenceImage": {"nodeId": "1", "inputName": "image"}})
    db_session.add(workflow)
    db_session.flush()
    sample_shot.workflow_preset_id = workflow.id
    sample_shot.seed = 123
    db_session.commit()
    revisions.refresh_project(db_session, sample_project.id)
    before = (sample_shot.prompt_revision, sample_shot.content_sha256, sample_shot.status)
    prompt = prompt_context.compile_for_shot(db_session, sample_shot).compiled.positive_prompt
    result = client.post(f"/api/shots/{sample_shot.id}/experiment")
    assert result.status_code == 201, result.text
    pid = result.json()["id"]
    copied = db_session.query(Shot).join(Scene).filter(Scene.project_id == pid).one()
    assert prompt_context.compile_for_shot(db_session, copied).compiled.positive_prompt == prompt
    assert copied.seed == 123 and copied.seed_policy == "fixed"
    copied_ref = db_session.get(ReferenceImage, copied.reference_asset_ids[0])
    assert copied_ref.id != ref.id and copied_ref.project_id == pid
    assert copied_ref.file_path != ref.file_path
    assert Path(copied_ref.file_path).read_bytes() == source.read_bytes()
    source.unlink()
    assert Path(copied_ref.file_path).read_bytes() == b"owned reference bytes"
    db_session.refresh(sample_shot)
    assert (sample_shot.prompt_revision, sample_shot.content_sha256, sample_shot.status) == before
    assert db_session.query(GenerationJob).count() == 0


def test_experiment_failure_rolls_back_rows(db_session, sample_shot, sample_project, monkeypatch):
    count = db_session.query(Project).count()
    def fail(*args, **kwargs):
        raise ValueError("Cannot compute inputs")
    monkeypatch.setattr(revisions, "shot_digest", fail)
    with pytest.raises(ValueError, match="Cannot compute"):
        experiments.create_from_shot(db_session, sample_shot)
    assert db_session.query(Project).count() == count
    assert db_session.get(Shot, sample_shot.id) is not None


def test_missing_shot_is_not_an_empty_experiment(client):
    assert client.post("/api/shots/missing/experiment").status_code == 404
