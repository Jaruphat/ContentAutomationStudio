"""A write that drops half its body must not answer 201.

Found the hard way. A production script posted a house style as
``{"name", "description", "negative_prompt"}`` - plausible field names, none of
them real - and the API created an empty Style and returned 201 Created. Every
later request looked healthy: the style existed, the project listed it, nothing
warned. The look simply never reached a single prompt.

This is the same failure as a reference input nobody filled: the operation
reports success while doing something other than what was asked. The difference
between a typo and a silent no-op is one line of configuration.

Scoped deliberately to the Story Bible's own write models. The shot and project
models are posted by a client that sends a whole record back, including
read-only fields, so forbidding extras there would break a working caller to
prevent a mistake it does not make.
"""

import pytest


@pytest.mark.parametrize("payload", [
    {"name": "ODDVERSE house look", "description": "muted documentary realism"},
    {"visual_keywords": "muted realism", "negative_prompt": "neon"},
])
def test_a_style_written_with_invented_field_names_is_refused(
    client, sample_project, payload,
):
    """The exact shape that got through: real-sounding names, no real fields.

    ``negative_prompt`` is the trap - the column is ``negative_constraints``,
    and a negative prompt silently dropped is how a film ends up full of the
    thing it was told to avoid.
    """
    response = client.post(f"/api/projects/{sample_project.id}/styles", json=payload)

    assert response.status_code == 422, response.text
    assert client.get(f"/api/projects/{sample_project.id}/styles").json() == []


def test_a_style_written_with_real_field_names_is_accepted(client, sample_project):
    response = client.post(f"/api/projects/{sample_project.id}/styles", json={
        "medium": "live-action documentary photography",
        "visual_keywords": "muted neutral tones, subtle 35mm grain",
        "negative_constraints": "cyberpunk, neon, glossy skin",
    })

    assert response.status_code == 201, response.text
    assert response.json()["negative_constraints"].startswith("cyberpunk")


def test_a_location_written_with_invented_field_names_is_refused(
    client, sample_project,
):
    response = client.post(f"/api/projects/{sample_project.id}/locations", json={
        "name": "The abandoned station", "world": "northern England",
    })

    assert response.status_code == 422, response.text


def test_a_location_written_with_real_field_names_is_accepted(
    client, sample_project,
):
    response = client.post(f"/api/projects/{sample_project.id}/locations", json={
        "name": "The abandoned station",
        "description": "Small abandoned rural railway station, weathered brick.",
        "time_of_day": "night",
    })

    assert response.status_code == 201, response.text
    assert response.json()["time_of_day"] == "night"


def test_editing_a_style_with_an_invented_field_is_refused_too(
    client, sample_project,
):
    """An edit that quietly changes nothing is worse than a create that
    quietly creates nothing: the user is looking at the old value and being
    told it was saved."""
    style = client.post(f"/api/projects/{sample_project.id}/styles", json={
        "visual_keywords": "muted realism",
    }).json()

    response = client.put(
        f"/api/projects/{sample_project.id}/styles/{style['id']}",
        json={"description": "high-contrast neon"},
    )

    assert response.status_code == 422, response.text
