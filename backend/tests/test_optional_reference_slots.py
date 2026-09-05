"""One workflow that serves a cast of one, two or three.

Reference inputs on the nodes this project drives are autogrow: the encoder
takes up to sixteen images and the reference-to-video node up to nine, with a
minimum of zero. An exported graph, though, wires a fixed number of loaders,
and every wired loader must be given an image - a reference input nothing was
sent to keeps whatever filename was baked in at export time.

That left a trap. A two-slot workflow could not render a solo shot, so a
project needed one registered workflow per size of cast and every shot had to
be pointed at the right one by hand. Marking a slot optional says the graph
tolerates it being absent, and the unfilled loader is then removed from the
submitted payload rather than left holding a stranger.

Removal is deliberately timid: a node is dropped only when nothing else in the
graph reads from it. A loader that also feeds a latent size or a comparison
node is load-bearing, and taking it out would change the render rather than
trim it.
"""

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import GenerationJob, Workflow
from app.services import job_payload, workflow_registry


def _register(db, raw_bytes, mapping, name="Flexible cast"):
    record = workflow_registry.import_workflow(
        raw_bytes=raw_bytes, name=name, purpose="image",
    )
    workflow = Workflow(**record)
    workflow.parameter_mapping = mapping
    workflow.output_mapping = [{"nodeId": "9", "type": "image"}]
    workflow.validation_status = "valid"
    db.add(workflow)
    db.commit()
    return workflow


# ---------------------------------------------------------------------------
# Declaring it
# ---------------------------------------------------------------------------

def test_capacity_still_counts_every_slot_a_workflow_binds():
    """Optional describes whether a slot may be empty, not whether it exists."""
    mapping = {
        "referenceImage": {"nodeId": "4", "field": "image"},
        "referenceImage2": {"nodeId": "5", "field": "image", "optional": True},
    }
    assert job_payload.reference_capacity(mapping) == 2


def test_required_slots_are_the_ones_not_marked_optional():
    mapping = {
        "referenceImage": {"nodeId": "4", "field": "image"},
        "referenceImage2": {"nodeId": "5", "field": "image", "optional": True},
        "referenceImage3": {"nodeId": "6", "field": "image", "optional": True},
    }
    assert job_payload.required_reference_count(mapping) == 1


def test_a_workflow_with_no_optional_slots_requires_all_of_them():
    """The existing shape keeps its meaning: unmarked means mandatory."""
    mapping = {
        "referenceImage": {"nodeId": "4", "field": "image"},
        "referenceImage2": {"nodeId": "5", "field": "image"},
    }
    assert job_payload.required_reference_count(mapping) == 2


# ---------------------------------------------------------------------------
# Pruning the payload
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_loader_graph():
    """A graph whose second loader feeds nothing but the encoder."""
    return json.dumps({
        "3": {"class_type": "KSampler", "inputs": {"seed": 0, "latent": ["8", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "baked-in-one.png"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": "baked-in-two.png"}},
        "8": {"class_type": "Encode",
              "inputs": {"image_1": ["4", 0], "image_2": ["5", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }).encode()


def _job(db, shot_id, workflow, values):
    job = GenerationJob(
        id=str(uuid.uuid4()), shot_id=shot_id, workflow_id=workflow.id,
        parameter_map=values, seed=values.get("seed", 1), status="Queued",
    )
    db.add(job)
    db.commit()
    return job


def test_an_unfilled_optional_slot_is_removed_rather_than_left_baked_in(
    db_session: Session, sample_shot, two_loader_graph,
):
    """The whole point: a solo shot on a two-slot graph renders one character.

    Left in place, loader 5 would submit `baked-in-two.png` - and on the
    machine that exported the graph that file exists, so the render would
    succeed with a stranger in it.
    """
    workflow = _register(db_session, two_loader_graph, {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
        job_payload.reference_image_field(1): {
            "nodeId": "5", "field": "image", "optional": True,
        },
    })
    job = _job(db_session, sample_shot.id, workflow, {
        job_payload.POSITIVE_PROMPT: "a hare alone",
        job_payload.SEED: 7,
        job_payload.REFERENCE_IMAGE: "cas/job/hare.png",
    })

    built = job_payload.build_payload(db_session, job, require_workflow=True)

    assert "5" not in built.payload, "the unfilled loader must not be submitted"
    assert built.payload["4"]["inputs"]["image"] == "cas/job/hare.png"
    assert "image_2" not in built.payload["8"]["inputs"], (
        "the input that read from it has to go too, or the graph dangles"
    )
    assert built.payload["8"]["inputs"]["image_1"] == ["4", 0]


def test_a_filled_optional_slot_is_submitted_like_any_other(
    db_session: Session, sample_shot, two_loader_graph,
):
    workflow = _register(db_session, two_loader_graph, {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
        job_payload.reference_image_field(1): {
            "nodeId": "5", "field": "image", "optional": True,
        },
    })
    job = _job(db_session, sample_shot.id, workflow, {
        job_payload.POSITIVE_PROMPT: "a hare and a tortoise",
        job_payload.SEED: 7,
        job_payload.REFERENCE_IMAGE: "cas/job/hare.png",
        job_payload.reference_image_field(1): "cas/job/tortoise.png",
    })

    built = job_payload.build_payload(db_session, job, require_workflow=True)

    assert built.payload["4"]["inputs"]["image"] == "cas/job/hare.png"
    assert built.payload["5"]["inputs"]["image"] == "cas/job/tortoise.png"
    assert built.payload["8"]["inputs"]["image_2"] == ["5", 0]


def test_a_loader_something_else_depends_on_is_never_removed(
    db_session: Session, sample_shot,
):
    """Timid on purpose: dropping a load-bearing node changes the render.

    Here the second loader also sizes the latent, so removing it would not
    trim the graph, it would break it. The slot stays, with whatever the
    export baked in - and the run is refused elsewhere rather than silently
    altered here.
    """
    graph = json.dumps({
        "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "one.png"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": "two.png"}},
        "7": {"class_type": "GetImageSize", "inputs": {"image": ["5", 0]}},
        "8": {"class_type": "Encode",
              "inputs": {"image_1": ["4", 0], "image_2": ["5", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }).encode()
    workflow = _register(db_session, graph, {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
        job_payload.reference_image_field(1): {
            "nodeId": "5", "field": "image", "optional": True,
        },
    }, name="Load bearing")
    job = _job(db_session, sample_shot.id, workflow, {
        job_payload.POSITIVE_PROMPT: "a hare alone", job_payload.SEED: 7,
        job_payload.REFERENCE_IMAGE: "cas/job/hare.png",
    })

    built = job_payload.build_payload(db_session, job, require_workflow=True)

    assert "5" in built.payload, "a node another input reads from stays"
    assert built.payload["7"]["inputs"]["image"] == ["5", 0]


def test_a_required_slot_left_empty_is_not_quietly_pruned(
    db_session: Session, sample_shot, two_loader_graph,
):
    """Only a slot declared optional may vanish. An unmarked one going missing
    is a mistake somewhere upstream, and hiding it would hide the mistake."""
    workflow = _register(db_session, two_loader_graph, {
        job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
        job_payload.SEED: {"nodeId": "3", "field": "seed"},
        job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
        job_payload.reference_image_field(1): {"nodeId": "5", "field": "image"},
    })
    job = _job(db_session, sample_shot.id, workflow, {
        job_payload.POSITIVE_PROMPT: "x", job_payload.SEED: 7,
        job_payload.REFERENCE_IMAGE: "cas/job/hare.png",
    })

    built = job_payload.build_payload(db_session, job, require_workflow=True)

    assert "5" in built.payload
