"""Turning approved stills into clips, without the bookkeeping.

Making a moving episode by hand takes four things that have nothing to do with
the film and everything to do with how the data is shaped, and every one of
them was learned by getting it wrong:

*A still and the clip made from it cannot be the same shot.* Changing a shot
to image-to-video moves its content revision, so a frame captured from its own
still is out of date the moment it is bound - and binding after the change
fails too, because only a current take may be captured. They have to be two
shots.

*The still must come off the cut.* Otherwise the film plays the picture and
then the clip made from it, one after the other.

*The clip has to be told where it starts.* Nothing is chained automatically,
which is right - the frame a clip begins on is a decision - but it means a
clip shot created and left alone is a clip of nothing.

*And the clips cannot exist before the stills are drawn.* Generate runs over
every eligible shot in the project, so a clip shot with no start frame yet is
a shot with no reference image, and preflight refuses the whole run for it.

None of that is a decision anybody wants to make per shot. The decision is
"animate this picture, for this long, doing this". This module takes that and
does the rest in one transaction.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Scene, Shot, Take
from app.services import continuity_frames, revisions

logger = logging.getLogger("cas.motion")

#: What a shot has to be for its take to be worth animating.
IMAGE_MODE = "image"
#: What the clip shot becomes.
VIDEO_MODE = "image-to-video"


class MotionError(Exception):
    """A clip that could not be created, with the reason."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def _scene_of(db: Session, shot: Shot) -> Scene:
    return db.query(Scene).filter(Scene.id == shot.scene_id).first()


def _clip_for_take(db: Session, project_id: str, take_id: str) -> Shot | None:
    """The clip shot already starting from this take, if there is one."""
    return (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(
            Scene.project_id == project_id,
            Shot.continuity_source_take_id == take_id,
        )
        .first()
    )


def candidates(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Every approved still in the project, and whether it is moving yet.

    Ordered the way the film reads, because the question a user is answering
    is "which of these should move", and the answer depends on what is either
    side of it.
    """
    rows = (
        db.query(Shot, Scene)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order, Shot.order)
        .all()
    )

    out: list[dict[str, Any]] = []
    for shot, scene in rows:
        if (shot.generation_mode or IMAGE_MODE) != IMAGE_MODE:
            continue
        take = (
            db.query(Take)
            .filter(Take.shot_id == shot.id, Take.review_status == "Approved")
            .order_by(Take.created_at.desc())
            .first()
        )
        if take is None or continuity_frames.is_video(take):
            continue
        clip = _clip_for_take(db, project_id, take.id)
        out.append({
            "shot_id": shot.id,
            "scene_id": scene.id,
            "shot_order": shot.order,
            "shot_label": f"{scene.title or 'Scene ' + str(scene.order)} · Shot {shot.order}",
            "subject": shot.subject or "",
            "dialogue": shot.dialogue or "",
            "planned_duration_sec": float(shot.planned_duration_sec or 0.0),
            "take_id": take.id,
            "take_url": f"/api/media/takes/{take.id}/file",
            "in_cut": bool(shot.include_in_cut),
            "clip_shot_id": clip.id if clip else None,
            "clip_status": clip.status if clip else "",
        })
    return out


def create_clip(
    db: Session,
    project_id: str,
    take_id: str,
    *,
    video_prompt: str,
    duration_sec: float,
    workflow_id: str,
) -> Shot:
    """Make the clip shot that animates ``take_id``, and wire it up.

    Everything the hand-built version had to remember: a new shot after the
    still, in video mode, on the video graph, holding the line the still was
    carrying, bound to the still as its start frame - and the still taken off
    the cut, because the film should play the clip, not both.
    """
    take = db.query(Take).filter(Take.id == take_id).first()
    if take is None:
        raise MotionError("That take does not exist.", "take_not_found")
    still = db.query(Shot).filter(Shot.id == take.shot_id).first()
    scene = _scene_of(db, still) if still else None
    if still is None or scene is None or scene.project_id != project_id:
        raise MotionError(
            "That take does not belong to this project.", "take_not_found"
        )
    if (take.review_status or "") != "Approved":
        raise MotionError(
            "Only an approved still can be animated. Approve it in Review "
            "first.",
            "take_not_approved",
        )
    if continuity_frames.is_video(take):
        raise MotionError(
            "That take is already a clip. Animate a still.", "take_is_video"
        )
    existing = _clip_for_take(db, project_id, take.id)
    if existing is not None:
        raise MotionError(
            "This still already has a clip. Re-generate that clip rather than "
            "making a second one from the same picture.",
            "clip_exists",
        )
    if not (video_prompt or "").strip():
        raise MotionError(
            "A clip needs to say what happens in it. A blank prompt still "
            "produces motion, and whatever it produces is what the film gets.",
            "missing_prompt",
        )
    if not workflow_id:
        raise MotionError(
            "A clip needs an image-to-video workflow.", "missing_workflow"
        )

    hold = float(duration_sec or 0.0) or float(still.planned_duration_sec or 0.0)
    if hold <= 0:
        raise MotionError(
            "A clip needs a length: it is how many frames are generated, not "
            "only how long the picture is held.",
            "missing_duration",
        )

    # The frame has to exist before it can be bound, and capturing it is the
    # same copy the continuity panel makes by hand.
    if continuity_frames.get_frame(db, take.id) is None:
        try:
            continuity_frames.extract_frame(db, take)
        except continuity_frames.ContinuityFrameError as exc:
            raise MotionError(str(exc), exc.code) from exc

    last = (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Scene.project_id == project_id)
        .order_by(Shot.order.desc())
        .first()
    )
    clip = Shot(
        scene_id=still.scene_id,
        order=(last.order if last else 0) + 1,
        subject=still.subject or "",
        # The line belongs to whatever is on the cut, and that is now the clip.
        dialogue=still.dialogue or "",
        planned_duration_sec=hold,
        generation_mode=VIDEO_MODE,
        workflow_preset_id=workflow_id,
        video_prompt=video_prompt.strip(),
        negative_prompt=still.negative_prompt or "",
        include_in_cut=True,
        status="Draft",
    )
    db.add(clip)
    db.flush()

    try:
        continuity_frames.bind_source(db, project_id, clip, take.id)
    except continuity_frames.ContinuityFrameError as exc:
        db.rollback()
        raise MotionError(str(exc), exc.code) from exc

    # The still's job is done the moment the clip starts from it.
    still.include_in_cut = False
    db.add(still)
    db.commit()
    db.refresh(clip)
    revisions.refresh_project(db, project_id)
    logger.info(
        "Project %s: shot %s animates the approved still of shot %s",
        project_id, clip.order, still.order,
    )
    return clip


__all__ = ["MotionError", "candidates", "create_clip", "IMAGE_MODE", "VIDEO_MODE"]
