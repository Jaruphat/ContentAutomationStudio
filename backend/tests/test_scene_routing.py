"""Which pipeline a shot should take, and why.

The application supports two ways to make a clip, and the choice is the single
biggest lever on how a film looks.

* **Key image, then animate.** Generate a still for the scene, approve it,
  animate that. Composition comes from a picture somebody looked at.
* **Reference to video.** Hand the model the canonical character views and the
  prompt. Four times faster, needs no still - and composes *from the
  reference*, so every shot opens with the subject centred in the sheet's pose
  and drifts into the described scene partway through.

Nothing in the app said so. A whole film was generated on the second route and
every clip opened the same way, which is a legible defect that only appears
once twenty-three of them are watched in a row.

A shot's *role* in its scene is what decides this: a shot that establishes a
scene needs composition, a shot that continues one already has it in the
previous clip's last frame. The role is inferred from position and can be
stated, and the plan it produces is advice with reasons attached - never a
silent reroute, because the user paid for the render either way.
"""

import uuid

from app.models import (
    CharacterSet,
    CharacterSetVersion,
    Scene,
    Shot,
    Take,
    Workflow,
)
from app.services import job_payload, scene_routing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shot(db, scene, order, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode=kwargs.pop("generation_mode", "video"), **kwargs,
    )
    db.add(shot)
    db.commit()
    return shot


def _workflow(db, mapping, name="H3 reference to video", purpose="video"):
    workflow = Workflow(
        id=str(uuid.uuid4()), name=name, purpose=purpose,
        source_format="api", source_json_path="unused.json",
        parameter_mapping=mapping, validation_status="valid",
    )
    db.add(workflow)
    db.commit()
    return workflow


R2V_MAPPING = {
    job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
    job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
}
T2V_MAPPING = {job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"}}
I2V_MAPPING = {
    job_payload.POSITIVE_PROMPT: {"nodeId": "6", "field": "text"},
    job_payload.REFERENCE_IMAGE: {"nodeId": "4", "field": "image"},
}


def _cast(db, project, shot):
    """Give the shot an approved canonical character set to be conditioned on."""
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
    shot.character_set_ids = [character_set.id]
    db.commit()
    return character_set


def _bind_start_frame(db, shot, source_shot):
    take = Take(
        id=str(uuid.uuid4()), shot_id=source_shot.id, file_path="clip.mp4",
        review_status="Approved", width=576, height=1024,
    )
    db.add(take)
    db.commit()
    shot.continuity_source_take_id = take.id
    shot.continuity_source_mode = "start_frame"
    db.commit()
    return take


# ---------------------------------------------------------------------------
# Inferring the role
# ---------------------------------------------------------------------------

def test_the_first_shot_of_a_scene_establishes_it(db_session, sample_scene):
    first = _shot(db_session, sample_scene, order=1)
    plan = scene_routing.plan(db_session, sample_scene.project_id, first)

    assert plan.role == scene_routing.ROLE_ESTABLISHING
    assert plan.inferred is True


def test_a_later_shot_of_the_same_scene_continues_it(db_session, sample_scene):
    _shot(db_session, sample_scene, order=1)
    second = _shot(db_session, sample_scene, order=2)

    plan = scene_routing.plan(db_session, sample_scene.project_id, second)

    assert plan.role == scene_routing.ROLE_CONTINUATION
    assert plan.inferred is True


def test_the_first_shot_of_the_second_scene_establishes_it_too(
    db_session, sample_project, sample_scene,
):
    """Continuity resets at a scene boundary, which is what a scene is for.

    Shot order runs on across a project, so position in the project cannot
    answer this - only position within the scene can.
    """
    later = Scene(
        id=str(uuid.uuid4()), project_id=sample_project.id, order=2,
        title="A different rooftop",
    )
    db_session.add(later)
    db_session.commit()
    _shot(db_session, sample_scene, order=1)
    _shot(db_session, sample_scene, order=2)
    opener = _shot(db_session, later, order=3)

    plan = scene_routing.plan(db_session, sample_project.id, opener)

    assert plan.role == scene_routing.ROLE_ESTABLISHING


def test_a_stated_role_overrides_the_inferred_one(db_session, sample_scene):
    """A cut back to an established location mid-scene is a real thing, and
    only the person writing the film knows about it."""
    _shot(db_session, sample_scene, order=1)
    second = _shot(db_session, sample_scene, order=2)
    second.scene_role = scene_routing.ROLE_ESTABLISHING
    db_session.commit()

    plan = scene_routing.plan(db_session, sample_scene.project_id, second)

    assert plan.role == scene_routing.ROLE_ESTABLISHING
    assert plan.inferred is False


# ---------------------------------------------------------------------------
# The warning this whole feature exists for
# ---------------------------------------------------------------------------

def test_an_establishing_shot_conditioned_only_on_a_character_is_warned(
    db_session, sample_project, sample_scene,
):
    """PRD v0.3 section 4.1, made visible before the render rather than after.

    The reference decides the opening composition, so an establishing shot
    given nothing but a character sheet opens as the character sheet - the
    subject centred in the sheet's pose, against the sheet's backdrop.
    """
    workflow = _workflow(db_session, R2V_MAPPING)
    shot = _shot(db_session, sample_scene, order=1, workflow_preset_id=workflow.id)
    _cast(db_session, sample_project, shot)

    plan = scene_routing.plan(db_session, sample_project.id, shot)

    assert plan.pipeline == scene_routing.PIPELINE_REFERENCE
    joined = " ".join(plan.warnings).lower()
    assert "compos" in joined, plan.warnings
    assert "key image" in joined, "the warning has to name the way out"
    assert plan.recommended_pipeline == scene_routing.PIPELINE_KEY_IMAGE


def test_an_establishing_shot_with_no_cast_is_not_warned(
    db_session, sample_project, sample_scene,
):
    """No reference, no borrowed composition. A landscape is fine as it is."""
    workflow = _workflow(db_session, T2V_MAPPING, name="H3 text to video")
    shot = _shot(db_session, sample_scene, order=1, workflow_preset_id=workflow.id)

    plan = scene_routing.plan(db_session, sample_project.id, shot)

    assert plan.warnings == []
    assert plan.pipeline == scene_routing.PIPELINE_TEXT


def test_an_establishing_image_shot_is_the_key_image_and_is_not_warned(
    db_session, sample_project, sample_scene,
):
    """Making a still to animate is the route the warning recommends. It
    cannot then be warned about."""
    workflow = _workflow(
        db_session, R2V_MAPPING, name="Boogu edit", purpose="image",
    )
    shot = _shot(
        db_session, sample_scene, order=1,
        generation_mode="image", workflow_preset_id=workflow.id,
    )
    _cast(db_session, sample_project, shot)

    plan = scene_routing.plan(db_session, sample_project.id, shot)

    assert plan.pipeline == scene_routing.PIPELINE_KEY_IMAGE
    assert plan.warnings == []


# ---------------------------------------------------------------------------
# Continuation
# ---------------------------------------------------------------------------

def test_a_continuation_with_a_bound_start_frame_needs_no_advice(
    db_session, sample_project, sample_scene,
):
    workflow = _workflow(db_session, I2V_MAPPING, name="H3 image to video")
    first = _shot(db_session, sample_scene, order=1)
    second = _shot(
        db_session, sample_scene, order=2,
        generation_mode="image-to-video", workflow_preset_id=workflow.id,
    )
    _bind_start_frame(db_session, second, first)

    plan = scene_routing.plan(db_session, sample_project.id, second)

    assert plan.pipeline == scene_routing.PIPELINE_CONTINUATION
    assert plan.warnings == []


def test_a_continuation_with_nothing_to_continue_from_is_warned(
    db_session, sample_project, sample_scene,
):
    """This is the same defect as the establishing case, seen from the other
    side: the shot claims to carry on from somewhere and starts from a sheet."""
    workflow = _workflow(db_session, R2V_MAPPING)
    _shot(db_session, sample_scene, order=1)
    second = _shot(db_session, sample_scene, order=2, workflow_preset_id=workflow.id)
    _cast(db_session, sample_project, second)

    plan = scene_routing.plan(db_session, sample_project.id, second)

    joined = " ".join(plan.warnings).lower()
    assert "end frame" in joined, plan.warnings
    assert plan.recommended_pipeline == scene_routing.PIPELINE_CONTINUATION


def test_continuing_from_a_shot_in_another_scene_is_flagged(
    db_session, sample_project, sample_scene,
):
    """A scene boundary is where the look is allowed to change. Carrying a
    frame across one is usually a leftover binding from a reordered cut, and
    it is invisible in the storyboard."""
    other = Scene(
        id=str(uuid.uuid4()), project_id=sample_project.id, order=2,
        title="Elsewhere",
    )
    db_session.add(other)
    db_session.commit()
    workflow = _workflow(db_session, I2V_MAPPING, name="H3 image to video")
    source = _shot(db_session, sample_scene, order=1)
    opener = _shot(
        db_session, other, order=2,
        generation_mode="image-to-video", workflow_preset_id=workflow.id,
    )
    _bind_start_frame(db_session, opener, source)

    plan = scene_routing.plan(db_session, sample_project.id, opener)

    joined = " ".join(plan.warnings).lower()
    assert "scene" in joined, plan.warnings


def test_a_plan_always_explains_itself(db_session, sample_project, sample_scene):
    """Advice with no reason attached gets clicked past."""
    workflow = _workflow(db_session, R2V_MAPPING)
    shot = _shot(db_session, sample_scene, order=1, workflow_preset_id=workflow.id)
    _cast(db_session, sample_project, shot)

    plan = scene_routing.plan(db_session, sample_project.id, shot)

    assert plan.summary
    assert all(len(w) > 40 for w in plan.warnings), "a warning must say what to do"


# ---------------------------------------------------------------------------
# It advises; it never reroutes
# ---------------------------------------------------------------------------

def test_the_plan_never_changes_the_shot(db_session, sample_project, sample_scene):
    """Rerouting a render the user configured, without being asked, spends
    their GPU time on a shot they did not order."""
    workflow = _workflow(db_session, R2V_MAPPING)
    shot = _shot(db_session, sample_scene, order=1, workflow_preset_id=workflow.id)
    _cast(db_session, sample_project, shot)
    before = (shot.workflow_preset_id, shot.generation_mode, shot.scene_role)

    scene_routing.plan(db_session, sample_project.id, shot)

    db_session.refresh(shot)
    assert (shot.workflow_preset_id, shot.generation_mode, shot.scene_role) == before


def test_an_unassigned_workflow_gives_advice_rather_than_a_crash(
    db_session, sample_project, sample_scene,
):
    shot = _shot(db_session, sample_scene, order=1)
    plan = scene_routing.plan(db_session, sample_project.id, shot)
    assert plan.pipeline == scene_routing.PIPELINE_UNKNOWN
    assert plan.summary
