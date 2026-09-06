"""What a shot's place in its scene says about how it should be generated.

There are two ways to make a clip here and they are not interchangeable.

*Key image, then animate* generates a still for the scene, has somebody approve
it, and animates that. Composition comes from a picture a person looked at.

*Reference to video* hands the model the canonical character views and the
prompt. It is roughly four times faster and needs no still - and it composes
**from the reference**. Given nothing but a character sheet, a clip opens with
the subject centred in the sheet's pose against the sheet's backdrop and drifts
into the described scene partway through. Across one shot that reads as a
style; across twenty-three it reads as a defect, and by then the render is
paid for.

The distinction that decides which is right is not the workflow, it is the
shot's role in its scene. A shot that **establishes** a scene has to invent a
composition. A shot that **continues** one already has its composition, in the
last frame of the clip before it. So the role is what this module reasons
about: inferred from position within the scene, overridable by the person
writing the film, and turned into advice that names both the consequence and
the way out.

It only ever advises. Rerouting a render the user configured would spend their
GPU time on a shot they did not order, and the composition trade is a real
trade - the fast route is the reason a three-minute film is an overnight job
rather than a four-hour one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Scene, Shot, Take
from app.services import shot_route

#: Unset. The role is then read off the shot's position in its scene.
ROLE_AUTO = ""
#: This shot opens a scene: nothing before it in this scene shares its framing.
ROLE_ESTABLISHING = "establishing"
#: This shot carries on from the one before it in the same scene.
ROLE_CONTINUATION = "continuation"

ROLES = (ROLE_AUTO, ROLE_ESTABLISHING, ROLE_CONTINUATION)

#: A still that a later shot animates. Composition is decided by a human.
PIPELINE_KEY_IMAGE = "key-image"
#: A clip that begins on a bound frame - an approved scene image, or the end
#: frame captured from the previous clip.
PIPELINE_CONTINUATION = "frame-continuation"
#: A clip composed by the model from reference images plus the prompt.
PIPELINE_REFERENCE = "reference-to-video"
#: A clip composed from the prompt alone.
PIPELINE_TEXT = "text-to-video"
#: No workflow assigned, so there is nothing to describe yet.
PIPELINE_UNKNOWN = "unassigned"

_PIPELINE_LABELS = {
    PIPELINE_KEY_IMAGE: "a key image for the scene",
    PIPELINE_CONTINUATION: "a clip continuing from a bound frame",
    PIPELINE_REFERENCE: "a clip composed from its reference images",
    PIPELINE_TEXT: "a clip composed from its prompt alone",
    PIPELINE_UNKNOWN: "nothing yet - no workflow is assigned",
}


@dataclass
class ScenePlan:
    """The role, the route it implies, and what disagrees between them."""

    role: str
    #: True when the role came from position rather than from the user.
    inferred: bool
    #: What will happen if Generate is pressed as the shot stands.
    pipeline: str
    #: What the role suggests instead, or the same value when they agree.
    recommended_pipeline: str
    summary: str
    warnings: list[str] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return self.pipeline == self.recommended_pipeline


def infer_role(db: Session, shot: Shot) -> str:
    """Establishing if nothing in this scene comes before it.

    Deliberately scoped to the scene rather than the project: shot order runs
    on across a film, so position in the project would make exactly one shot
    establishing and the other twenty-two continuations of it. A scene
    boundary is where a look is allowed to change, and where continuity is
    meant to reset.
    """
    earlier = (
        db.query(Shot)
        .filter(Shot.scene_id == shot.scene_id, Shot.id != shot.id)
        .filter(Shot.order < (shot.order or 0))
        .count()
    )
    return ROLE_CONTINUATION if earlier else ROLE_ESTABLISHING


def _bound_start_frame(shot: Shot) -> bool:
    return bool(
        (shot.continuity_source_take_id
         and (shot.continuity_source_mode or "none") != "none")
        # A manually attached scene image is also the first I2V frame.
        # Canonical character sets alone are not (preflight enforces that).
        or (shot.generation_mode == "image-to-video" and shot.reference_asset_ids)
    )


def _source_scene_id(db: Session, shot: Shot) -> str:
    """The scene the shot's start frame was captured in, if it has one."""
    if not shot.continuity_source_take_id:
        return ""
    take = (
        db.query(Take).filter(Take.id == shot.continuity_source_take_id).first()
    )
    if take is None:
        return ""
    source = db.query(Shot).filter(Shot.id == take.shot_id).first()
    return source.scene_id if source else ""


def _has_cast(shot: Shot) -> bool:
    return bool(shot.character_set_ids or shot.reference_asset_ids)


def _observed_pipeline(db: Session, project_id: str, shot: Shot) -> str:
    """What the shot as configured will actually do - never what it should."""
    route = shot_route.describe(db, project_id, shot)
    mode = (shot.generation_mode or "image").lower()

    if mode == "image":
        return PIPELINE_KEY_IMAGE
    if not route["workflow_name"] and route["provider_id"] == "comfyui":
        return PIPELINE_UNKNOWN
    if mode == "image-to-video" or _bound_start_frame(shot):
        return PIPELINE_CONTINUATION
    if route["reference_capacity"] > 0 and _has_cast(shot):
        return PIPELINE_REFERENCE
    return PIPELINE_TEXT


def plan(db: Session, project_id: str, shot: Shot) -> ScenePlan:
    """Describe the shot's role, its route, and where the two disagree."""
    if not project_id:
        scene = db.query(Scene).filter(Scene.id == shot.scene_id).first()
        project_id = scene.project_id if scene else ""

    stated = (getattr(shot, "scene_role", "") or "").strip().lower()
    if stated in (ROLE_ESTABLISHING, ROLE_CONTINUATION):
        role, inferred = stated, False
    else:
        role, inferred = infer_role(db, shot), True

    pipeline = _observed_pipeline(db, project_id, shot)
    recommended = pipeline
    warnings: list[str] = []

    if role == ROLE_ESTABLISHING and pipeline == PIPELINE_REFERENCE:
        recommended = PIPELINE_KEY_IMAGE
        warnings.append(
            "This shot opens its scene, but reference-to-video takes its "
            "composition from the reference images, not from the prompt - so "
            "the clip will open framed like the character sheet and only "
            "drift into the described scene partway through. To decide the "
            "framing yourself, generate a key image for this shot, approve "
            "it, and animate that in the shot after it. Staying on this route "
            "is roughly four times faster and is a reasonable trade when the "
            "opening framing does not matter."
        )
    elif role == ROLE_CONTINUATION and pipeline == PIPELINE_REFERENCE:
        recommended = PIPELINE_CONTINUATION
        warnings.append(
            "This shot continues its scene, but nothing binds it to the shot "
            "before it, so it will be composed from its reference images and "
            "start somewhere unrelated to where the previous clip left off. "
            "Capture the end frame of the previous approved take and bind it "
            "as this shot's start frame under Explicit shot continuity."
        )
    elif pipeline == PIPELINE_CONTINUATION and not _bound_start_frame(shot):
        recommended = PIPELINE_CONTINUATION
        warnings.append(
            "This shot is routed to continue from a frame, but no start frame "
            "is bound to it. Capture the end frame of the previous approved "
            "take, or approve a scene image for this shot, and bind it under "
            "Explicit shot continuity."
        )

    if _bound_start_frame(shot):
        source_scene = _source_scene_id(db, shot)
        if source_scene and source_scene != shot.scene_id:
            warnings.append(
                "This shot's start frame was captured in a different scene. A "
                "scene boundary is where continuity is meant to reset, so this "
                "is usually a binding left behind by a reordered cut - it will "
                "carry the other scene's lighting and framing into this one. "
                "Rebind it to a take from this scene, or clear it."
            )

    summary = (
        f"{'Opens' if role == ROLE_ESTABLISHING else 'Continues'} the scene "
        f"({'inferred from shot order' if inferred else 'set by hand'}); "
        f"generates {_PIPELINE_LABELS[pipeline]}."
    )

    return ScenePlan(
        role=role,
        inferred=inferred,
        pipeline=pipeline,
        recommended_pipeline=recommended,
        summary=summary,
        warnings=warnings,
    )


__all__ = [
    "ROLE_AUTO", "ROLE_ESTABLISHING", "ROLE_CONTINUATION", "ROLES",
    "PIPELINE_KEY_IMAGE", "PIPELINE_CONTINUATION", "PIPELINE_REFERENCE",
    "PIPELINE_TEXT", "PIPELINE_UNKNOWN",
    "ScenePlan", "infer_role", "plan",
]
