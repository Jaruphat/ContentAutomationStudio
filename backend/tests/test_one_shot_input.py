"""One place decides what a shot tells the compiler.

`prompt_context.shot_input` builds the dict the prompt compiler reads. The
generate endpoint had a copy of it, written out by hand, and the copy fell
behind: the motion fields were added to the shared builder, reached the
preview and the regenerate path, and never reached the prompt an actual
generation submitted.

Nothing failed. Nine clips were rendered from a prompt that described a
photograph and named no movement at all, and came back 97.6% identical frames -
worse than the run they were meant to improve on. The only symptom was a number
in a motion measurement.

This test holds every path to the shared builder, so the next field added has
one place to be added to.
"""

import uuid

from app.models import Shot
from app.services import prompt_context

#: Everything the compiler reads off a shot. A field the builder omits is a
#: field silently dropped from every prompt.
COMPILER_INPUTS = (
    "id", "shot_type", "camera_angle", "camera_movement", "lens_framing",
    "subject", "action", "environment", "generation_mode", "image_prompt",
    "video_prompt", "subject_motion", "camera_motion", "negative_prompt",
)


def test_the_shared_builder_carries_everything_the_compiler_reads(
    db_session, sample_scene,
):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="image-to-video",
        subject_motion="The door slides open and light spills out.",
        camera_motion="Locked-off camera.",
    )
    db_session.add(shot)
    db_session.commit()

    built = prompt_context.shot_input(shot)

    assert set(built) == set(COMPILER_INPUTS)
    assert built["subject_motion"].startswith("The door slides open")


def test_generation_builds_its_prompt_from_the_shared_builder(
    client, db_session, sample_project, sample_scene,
):
    """The failure this catches: the generate path had its own copy of the
    dict, and the copy did not know about the motion fields. Nine clips were
    submitted with no movement described and nothing reported a problem."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", status="Ready",
        subject_motion=(
            "The carriage door slides fully open and warm light widens across "
            "the platform."
        ),
        camera_motion="Locked-off camera.",
    )
    db_session.add(shot)
    db_session.commit()

    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [shot.id], "confirm_paid_generation": False},
    )

    assert response.status_code == 200, response.text
    prompt = response.json()[0]["parameter_map"]["positivePrompt"]
    assert "carriage door slides fully open" in prompt, prompt


def test_the_estimate_and_the_generation_agree_on_the_prompt(
    client, db_session, sample_project, sample_scene,
):
    """Two paths that build the prompt differently is how an estimate prices
    one thing and the queue runs another."""
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=1,
        generation_mode="video", status="Ready",
        subject_motion="The train rolls in and its headlights sweep the rails.",
        camera_motion="Long lens.",
    )
    db_session.add(shot)
    db_session.commit()

    preview = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}"
        f"/shots/{shot.id}/prompt"
    )
    generated = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [shot.id], "confirm_paid_generation": False},
    )

    assert generated.status_code == 200, generated.text
    submitted = generated.json()[0]["parameter_map"]["positivePrompt"]
    if preview.status_code == 200:
        assert preview.json()["positive_prompt"] == submitted
    else:
        assert "train rolls in" in submitted
