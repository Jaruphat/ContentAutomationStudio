"""
Reference capacity comes from the workflow, not from a constant.

One reference image was never a property of ComfyUI; it was a property of the
one workflow that happened to be registered first. The nodes this project
drives take several: Boogu's editor grows to sixteen, MiniMax H3's
reference-to-video to nine, Qwen's edit encoder to three. A shot that binds a
canonical identity *and* continues from a previous clip needs two at once, so
the number has to be read off the workflow that will actually run.
"""

from app.services import job_payload


def test_the_first_reference_slot_keeps_its_original_name():
    """Existing workflows and persisted jobs must not need rewriting.

    Every mapping already in the database names the single slot
    ``referenceImage``. Numbering from the second slot leaves those untouched.
    """
    assert job_payload.reference_image_field(0) == "referenceImage"
    assert job_payload.reference_image_field(1) == "referenceImage2"
    assert job_payload.reference_image_field(2) == "referenceImage3"


def test_every_reference_slot_is_a_recognised_logical_field():
    """A value only survives into the payload if it is a known logical field."""
    for index in range(job_payload.MAX_REFERENCE_IMAGES):
        assert job_payload.reference_image_field(index) in job_payload.LOGICAL_FIELDS


def test_capacity_is_what_the_workflow_maps():
    """An unmapped slot cannot be filled, so it does not count as capacity."""
    assert job_payload.reference_capacity({}) == 0
    assert job_payload.reference_capacity({"referenceImage": {}}) == 1
    assert job_payload.reference_capacity(
        {"referenceImage": {}, "referenceImage2": {}}
    ) == 2
    assert job_payload.reference_capacity(
        {"positivePrompt": {}, "seed": {}}
    ) == 0


def test_capacity_stops_at_the_first_gap():
    """Slots are filled in order, so a hole ends the usable run.

    A mapping that binds slot 1 and slot 3 but not slot 2 cannot take three
    images: the third would have to be submitted into an unmapped input.
    Counting the contiguous run is what keeps the promise honest.
    """
    assert job_payload.reference_capacity(
        {"referenceImage": {}, "referenceImage3": {}}
    ) == 1
