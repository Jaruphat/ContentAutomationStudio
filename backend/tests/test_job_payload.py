"""
Tests for the job payload builder.

Covers the seam that turns a persisted job plus a registered workflow into a
concrete ComfyUI payload: mapping injection, snapshot provenance, the
mock-provider passthrough, and the validation errors a real provider must
raise rather than submitting a malformed graph.
"""

import json
import os
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import GenerationJob, Shot, Workflow
from app.services import job_payload, workflow_registry
from app.services.job_payload import (
    NEGATIVE_PROMPT,
    POSITIVE_PROMPT,
    SEED,
    WIDTH,
    BuiltPayload,
    WorkflowValidationError,
    build_payload,
    logical_values_for_job,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registered_workflow(db_session: Session, sample_workflow_json: bytes) -> Workflow:
    """A workflow imported from JSON with a valid mapping."""
    record = workflow_registry.import_workflow(
        raw_bytes=sample_workflow_json,
        name="H3 Image Test",
        purpose="image",
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = {
        POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        NEGATIVE_PROMPT: {"nodeId": "7", "field": "text"},
        SEED: {"nodeId": "3", "field": "seed"},
        WIDTH: {"nodeId": "5", "field": "width"},
    }
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    workflow.validation_status = "valid"
    db_session.add(workflow)
    db_session.commit()
    db_session.refresh(workflow)
    return workflow


def make_job(db_session: Session, shot: Shot, workflow_id: str | None) -> GenerationJob:
    job = GenerationJob(
        id=str(uuid.uuid4()),
        shot_id=shot.id,
        workflow_id=workflow_id,
        parameter_map={
            POSITIVE_PROMPT: "a lone traveller on a ridge",
            NEGATIVE_PROMPT: "blurry, watermark",
            SEED: 1234,
            WIDTH: 1280,
            "generation_mode": "image",  # not a logical field; must be dropped
        },
        seed=1234,
        status="Queued",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# logical_values_for_job
# ---------------------------------------------------------------------------

class TestLogicalValues:
    def test_keeps_only_canonical_fields(self, db_session, sample_shot):
        job = make_job(db_session, sample_shot, None)
        values = logical_values_for_job(job)
        assert set(values) == {POSITIVE_PROMPT, NEGATIVE_PROMPT, SEED, WIDTH}
        assert "generation_mode" not in values

    def test_seed_column_wins_over_parameter_map(self, db_session, sample_shot):
        job = make_job(db_session, sample_shot, None)
        job.seed = 999
        db_session.commit()
        assert logical_values_for_job(job)[SEED] == 999


# ---------------------------------------------------------------------------
# Mapped payload construction
# ---------------------------------------------------------------------------

class TestMappedPayload:
    def test_values_are_injected_into_mapped_nodes(
        self, db_session, sample_shot, registered_workflow
    ):
        job = make_job(db_session, sample_shot, registered_workflow.id)
        built = build_payload(db_session, job, require_workflow=True)

        assert not built.passthrough
        assert built.payload["6"]["inputs"]["text"] == "a lone traveller on a ridge"
        assert built.payload["7"]["inputs"]["text"] == "blurry, watermark"
        assert built.payload["3"]["inputs"]["seed"] == 1234
        assert built.payload["5"]["inputs"]["width"] == 1280

    def test_unmapped_node_inputs_are_preserved(
        self, db_session, sample_shot, registered_workflow
    ):
        """Only mapped fields change; the rest of the graph is untouched."""
        job = make_job(db_session, sample_shot, registered_workflow.id)
        built = build_payload(db_session, job, require_workflow=True)
        assert built.payload["3"]["inputs"]["steps"] == 20
        assert built.payload["3"]["inputs"]["sampler_name"] == "euler"
        assert built.payload["4"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"

    def test_payload_is_a_copy_not_the_source(
        self, db_session, sample_shot, registered_workflow
    ):
        job = make_job(db_session, sample_shot, registered_workflow.id)
        build_payload(db_session, job, require_workflow=True)
        on_disk = workflow_registry.load_workflow_source(
            registered_workflow.source_json_path
        )
        assert on_disk["6"]["inputs"]["text"] != "a lone traveller on a ridge"

    def test_snapshot_written_with_submitted_payload(
        self, db_session, sample_shot, registered_workflow
    ):
        job = make_job(db_session, sample_shot, registered_workflow.id)
        built = build_payload(db_session, job, require_workflow=True)

        assert os.path.isfile(built.snapshot_path)
        with open(built.snapshot_path, encoding="utf-8") as f:
            snapshot = json.load(f)
        assert snapshot == built.payload

    def test_snapshot_carries_workflow_hash(
        self, db_session, sample_shot, registered_workflow
    ):
        job = make_job(db_session, sample_shot, registered_workflow.id)
        built = build_payload(db_session, job, require_workflow=True)
        assert built.workflow_sha256 == registered_workflow.sha256_hash
        assert len(built.workflow_sha256) == 64

    def test_unmapped_logical_fields_are_reported(
        self, db_session, sample_shot, registered_workflow
    ):
        job = make_job(db_session, sample_shot, registered_workflow.id)
        job.parameter_map = dict(job.parameter_map, outputPrefix="shot01")
        db_session.commit()
        built = build_payload(db_session, job, require_workflow=True)
        assert "outputPrefix" in built.unmapped_fields


# ---------------------------------------------------------------------------
# Mock passthrough
# ---------------------------------------------------------------------------

class TestPassthrough:
    def test_no_workflow_passes_logical_values_through(self, db_session, sample_shot):
        job = make_job(db_session, sample_shot, None)
        built = build_payload(db_session, job, require_workflow=False)
        assert built.passthrough is True
        assert built.payload[POSITIVE_PROMPT] == "a lone traveller on a ridge"
        assert built.snapshot_path == ""

    def test_unmapped_workflow_passes_through(
        self, db_session, sample_shot, registered_workflow
    ):
        registered_workflow.parameter_mapping = {}
        db_session.commit()
        job = make_job(db_session, sample_shot, registered_workflow.id)
        built = build_payload(db_session, job, require_workflow=False)
        assert built.passthrough is True

    def test_stale_mapping_passes_through_in_mock_mode(
        self, db_session, sample_shot, registered_workflow
    ):
        """A mapping pointing at a node that no longer exists must not crash
        the mock flow; it degrades to passthrough."""
        registered_workflow.parameter_mapping = {
            POSITIVE_PROMPT: {"nodeId": "999", "field": "text"},
        }
        db_session.commit()
        job = make_job(db_session, sample_shot, registered_workflow.id)
        built = build_payload(db_session, job, require_workflow=False)
        assert built.passthrough is True


# ---------------------------------------------------------------------------
# Real-provider validation
# ---------------------------------------------------------------------------

class TestRequireWorkflow:
    def test_missing_workflow_raises(self, db_session, sample_shot):
        job = make_job(db_session, sample_shot, None)
        with pytest.raises(WorkflowValidationError, match="no registered workflow"):
            build_payload(db_session, job, require_workflow=True)

    def test_empty_mapping_raises(
        self, db_session, sample_shot, registered_workflow
    ):
        registered_workflow.parameter_mapping = {}
        db_session.commit()
        job = make_job(db_session, sample_shot, registered_workflow.id)
        with pytest.raises(WorkflowValidationError, match="no parameter"):
            build_payload(db_session, job, require_workflow=True)

    def test_stale_node_id_raises_with_details(
        self, db_session, sample_shot, registered_workflow
    ):
        """This is the H3 risk from the PRD: re-exporting a workflow renumbers
        its nodes, so a previously valid mapping silently points at nothing."""
        registered_workflow.parameter_mapping = {
            POSITIVE_PROMPT: {"nodeId": "999", "field": "text"},
            SEED: {"nodeId": "3", "field": "seed"},
        }
        db_session.commit()
        job = make_job(db_session, sample_shot, registered_workflow.id)

        with pytest.raises(WorkflowValidationError) as exc_info:
            build_payload(db_session, job, require_workflow=True)
        assert any("999" in e for e in exc_info.value.errors)

    def test_missing_required_field_raises(
        self, db_session, sample_shot, registered_workflow
    ):
        registered_workflow.parameter_mapping = {
            NEGATIVE_PROMPT: {"nodeId": "7", "field": "text"},
        }
        db_session.commit()
        job = make_job(db_session, sample_shot, registered_workflow.id)

        with pytest.raises(WorkflowValidationError) as exc_info:
            build_payload(db_session, job, require_workflow=True)
        message = str(exc_info.value)
        assert POSITIVE_PROMPT in message and SEED in message

    def test_missing_source_file_raises(
        self, db_session, sample_shot, registered_workflow
    ):
        os.remove(registered_workflow.source_json_path)
        job = make_job(db_session, sample_shot, registered_workflow.id)
        with pytest.raises(WorkflowValidationError, match="Cannot load workflow"):
            build_payload(db_session, job, require_workflow=True)


# ---------------------------------------------------------------------------
# Canonical field names
# ---------------------------------------------------------------------------

class TestCanonicalFields:
    def test_required_fields_are_a_subset_of_logical_fields(self):
        assert set(job_payload.REQUIRED_LOGICAL_FIELDS) <= set(
            job_payload.LOGICAL_FIELDS
        )

    def test_built_payload_defaults(self):
        built = BuiltPayload(payload={})
        assert built.snapshot_path == ""
        assert built.unmapped_fields == []
        assert built.passthrough is False
