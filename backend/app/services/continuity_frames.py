"""
End-frame continuity.

An image-to-video shot has to start from a picture. When that picture is the
last frame of the previous shot, a pile of clips becomes a sequence - and that
is the one continuity constraint no amount of prompt text can express.

Three rules hold throughout:

* **Only an approved video take hands off.** A pending take is not a decision,
  and a still has no end frame. Both are refused with a reason, because a shot
  built on either would be built on something nobody chose.
* **The frame is an ordinary reference image.** The extracted bytes are stored
  through :mod:`app.services.reference_bible`, so a continuity frame reaches a
  provider by the same validated, ownership-checked path as a hand-uploaded
  plate. There is exactly one way an image can condition a job.
* **The binding is explicit.** A shot names the take it continues from.
  Inferring it from shot order would silently rewire the cut the moment
  someone reorders or deletes a shot, and would do it without saying so.

One take holds one hand-off frame. Re-cutting at a different timestamp
replaces it in place; the hash moving is exactly what makes every shot seeded
from it stale.
"""

import logging
import os
import tempfile
from typing import Any

from sqlalchemy.orm import Session

from app.models import ContinuityFrame, ReferenceImage, ReferenceSheet, Take
from app.services import media_probe, reference_bible

logger = logging.getLogger("cas.continuity_frames")

#: How the frame's timestamp was chosen.
SELECTION_LAST = "last"
SELECTION_EXPLICIT = "explicit"

#: What a shot's ``continuity_source_mode`` may hold.
MODE_NONE = "none"
MODE_END_FRAME = "end_frame"

#: The name of the per-project sheet extracted frames are filed under. Held as
#: a constant because it is also how the sheet is found again.
CONTINUITY_SHEET_NAME = "Continuity Frames"

#: How far back from the end of a clip ffmpeg is asked to decode when cutting
#: the final frame. Every frame in that window is written over the same file,
#: so the last one to be decoded is the one left behind - which is the only
#: reliable way to name "the last frame" without knowing the exact final PTS.
LAST_FRAME_WINDOW_SEC = 1.0


class ContinuityFrameError(Exception):
    """A continuity operation was refused, with a machine-readable reason."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# The sheet frames are filed on
# ---------------------------------------------------------------------------

def continuity_sheet(db: Session, project_id: str) -> ReferenceSheet:
    """The project's continuity sheet, created on first use.

    One sheet per project rather than one per shot: a hand-off frame belongs to
    the project's continuity, and a per-shot sheet would multiply the Reference
    Bible by the storyboard without telling anyone anything new.
    """
    sheet = (
        db.query(ReferenceSheet)
        .filter(
            ReferenceSheet.project_id == project_id,
            ReferenceSheet.kind == reference_bible.KIND_CONTINUITY,
        )
        .order_by(ReferenceSheet.created_at)
        .first()
    )
    if sheet is not None:
        return sheet
    return reference_bible.create_sheet(
        db,
        project_id=project_id,
        kind=reference_bible.KIND_CONTINUITY,
        name=CONTINUITY_SHEET_NAME,
        notes=(
            "End frames lifted from approved takes, used to seed the first "
            "frame of the shots that continue from them."
        ),
    )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _project_id_for_take(db: Session, take: Take) -> str:
    from app.models import Scene, Shot

    row = (
        db.query(Scene.project_id)
        .join(Shot, Shot.scene_id == Scene.id)
        .filter(Shot.id == take.shot_id)
        .first()
    )
    return row[0] if row else ""


def is_video(take: Take) -> bool:
    """Whether this take holds moving pictures.

    The extension is what a still is distinguished by, not the duration: a
    one-frame clip is still a video, and a take row can carry a zero duration
    simply because no probe ever ran on it.
    """
    extension = os.path.splitext(take.file_path or "")[1].lower()
    return extension in media_probe.VIDEO_EXTENSIONS


def _clip_duration(take: Take) -> float:
    """The clip's real duration, probed rather than trusted from the row.

    A take's ``duration_sec`` is written by whatever produced it and may be
    zero on a machine that had no ffprobe at the time. Falling back to the
    stored value keeps this usable on such a machine instead of refusing
    every cut.
    """
    probed = media_probe.probe_media_file(take.file_path or "")
    duration = float(probed.get("duration_sec") or 0.0)
    return duration if duration > 0 else float(take.duration_sec or 0.0)


def _cut_frame(file_path: str, destination: str, at_sec: float | None) -> bool:
    """Write one frame of ``file_path`` to ``destination``; True when it landed.

    ``at_sec`` of None means the final frame, which is taken by decoding the
    tail of the clip into the same output file so the last frame decoded is the
    one that survives. An exact timestamp uses output seeking, which decodes up
    to the requested moment rather than jumping to the nearest keyframe - the
    frame the user picked is the frame they get.
    """
    ffmpeg = media_probe.ffmpeg_path()
    if not ffmpeg:
        raise ContinuityFrameError(
            "FFmpeg is not installed on this machine, so an end frame cannot "
            "be extracted. Install FFmpeg and put it on PATH, then try again.",
            "ffmpeg_missing",
        )

    if at_sec is None:
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-sseof", f"-{LAST_FRAME_WINDOW_SEC:g}",
            "-i", file_path,
            "-update", "1", "-frames:v", str(10**6),
            destination,
        ]
    else:
        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", file_path,
            "-ss", f"{at_sec:.6f}",
            "-frames:v", "1", "-update", "1",
            destination,
        ]

    returncode, _stdout, stderr = media_probe.run_captured(cmd, timeout=120)
    if returncode != 0:
        logger.warning("end-frame extraction failed: %s", stderr[-300:])
        return False
    return os.path.isfile(destination) and os.path.getsize(destination) > 0


def extract_frame(
    db: Session, take: Take, *, at_sec: float | None = None
) -> ContinuityFrame:
    """Lift a still out of an approved video take and file it as a reference.

    ``at_sec`` of None takes the final frame - the usual hand-off. Passing a
    timestamp records the choice as explicit, because "the last frame" and
    "this frame" are different promises: only the first one is still true after
    the take is replaced by a longer one.
    """
    if (take.review_status or "") != "Approved":
        raise ContinuityFrameError(
            "Only an approved take can hand off to the next shot. Approve this "
            "take in Review first, or pick a different one.",
            "take_not_approved",
        )
    if not is_video(take):
        raise ContinuityFrameError(
            "This take is a still image, so it has no end frame. Use it as an "
            "ordinary reference instead.",
            "not_a_video",
        )
    if not take.file_path or not os.path.isfile(take.file_path):
        raise ContinuityFrameError(
            "The media file for this take is missing from disk, so no frame "
            "can be cut from it. Regenerate the shot.",
            "media_missing",
        )

    project_id = _project_id_for_take(db, take)
    if not project_id:
        raise ContinuityFrameError(
            "This take is not attached to a project.", "project_missing"
        )

    duration = _clip_duration(take)
    if at_sec is not None:
        if at_sec < 0:
            raise ContinuityFrameError(
                "A frame time cannot be negative.", "timestamp_out_of_range"
            )
        if duration > 0 and at_sec >= duration:
            raise ContinuityFrameError(
                f"This take is {duration:.2f}s long, so there is no frame at "
                f"{at_sec:.2f}s. Choose a time inside the clip.",
                "timestamp_out_of_range",
            )

    with tempfile.TemporaryDirectory(prefix="cas-endframe-") as tmp:
        destination = os.path.join(tmp, "frame.png")
        if not _cut_frame(take.file_path, destination, at_sec):
            raise ContinuityFrameError(
                "FFmpeg could not read a frame out of this take. The file may "
                "be truncated; regenerate the shot and try again.",
                "extraction_failed",
            )
        with open(destination, "rb") as f:
            data = f.read()

    selection = SELECTION_LAST if at_sec is None else SELECTION_EXPLICIT
    # The last frame's own timestamp is not knowable without decoding the whole
    # clip, so the clip's duration is recorded as where the hand-off sits.
    frame_time = duration if at_sec is None else float(at_sec)

    sheet = continuity_sheet(db, project_id)
    image = reference_bible.store_image(
        db,
        sheet=sheet,
        data=data,
        original_filename=f"endframe-{take.id[:8]}.png",
        content_type="image/png",
        role="canonical",
        caption=f"End frame of take {take.id[:8]}",
        source="continuity_frame",
        source_detail={
            "take_id": take.id,
            "shot_id": take.shot_id,
            "selection": selection,
            "frame_time_sec": round(frame_time, 3),
        },
    )

    frame = (
        db.query(ContinuityFrame)
        .filter(ContinuityFrame.take_id == take.id)
        .first()
    )
    previous_image_id = frame.reference_image_id if frame else None
    if frame is None:
        frame = ContinuityFrame(take_id=take.id, project_id=project_id)
        db.add(frame)

    frame.shot_id = take.shot_id
    frame.reference_image_id = image.id
    frame.frame_time_sec = round(frame_time, 3)
    frame.selection = selection
    frame.sha256 = image.sha256 or ""
    frame.width = image.width or 0
    frame.height = image.height or 0
    frame.source_duration_sec = duration
    db.commit()
    db.refresh(frame)

    if previous_image_id and previous_image_id != image.id:
        _discard_superseded_image(db, previous_image_id)
    return frame


def _discard_superseded_image(db: Session, image_id: str) -> None:
    """Remove the frame a re-cut replaced, unless something still uses it.

    A shot may have been conditioned on the old frame directly through its
    reference list. Deleting it there would break that shot rather than
    tidying up, so it is left alone and simply stops being the hand-off.
    """
    image = reference_bible.get_image(db, image_id)
    if image is None:
        return
    if reference_bible.shots_using(db, [image.id]):
        return
    still_referenced = (
        db.query(ContinuityFrame)
        .filter(ContinuityFrame.reference_image_id == image.id)
        .count()
    )
    if still_referenced:
        return
    try:
        reference_bible.delete_image(db, image, force=False)
    except reference_bible.ReferenceBibleError:
        logger.info("Superseded continuity frame %s is still in use", image.id)


def get_frame(db: Session, take_id: str) -> ContinuityFrame | None:
    return (
        db.query(ContinuityFrame)
        .filter(ContinuityFrame.take_id == take_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Candidates and binding
# ---------------------------------------------------------------------------

def candidates(db: Session, project_id: str, shot: Any) -> list[ContinuityFrame]:
    """Every frame in this project that could seed ``shot``, newest last.

    The shot's own frames are excluded: a shot cannot continue from itself, and
    offering that choice would only make it possible to build a loop.
    """
    query = (
        db.query(ContinuityFrame)
        .filter(ContinuityFrame.project_id == project_id)
        .order_by(ContinuityFrame.created_at)
    )
    shot_id = getattr(shot, "id", None) if shot is not None else None
    return [frame for frame in query.all() if frame.shot_id != shot_id]


def bind_source(
    db: Session, project_id: str, shot: Any, take_id: str
) -> Any:
    """Wire ``shot`` to start from the end frame of ``take_id``.

    Refused unless the take belongs to this project, is not one of this shot's
    own, and already has an extracted frame: binding names a frame that exists
    now, not one somebody might cut later.
    """
    take = db.query(Take).filter(Take.id == take_id).first()
    if take is None or _project_id_for_take(db, take) != project_id:
        raise ContinuityFrameError(
            "That take does not exist in this project.", "take_not_found"
        )
    if take.shot_id == shot.id:
        raise ContinuityFrameError(
            "A shot cannot continue from its own take. Choose a take from the "
            "shot that comes before it.",
            "self_continuity",
        )
    frame = get_frame(db, take.id)
    if frame is None:
        raise ContinuityFrameError(
            "That take has no extracted end frame yet. Cut one in Review "
            "first, then bind it here.",
            "no_continuity_frame",
        )

    shot.continuity_source_take_id = take.id
    shot.continuity_source_mode = MODE_END_FRAME
    db.commit()
    db.refresh(shot)
    return shot


def clear_source(db: Session, shot: Any) -> Any:
    """Stop this shot continuing from anything."""
    shot.continuity_source_take_id = None
    shot.continuity_source_mode = MODE_NONE
    db.commit()
    db.refresh(shot)
    return shot


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_source_image(
    db: Session, project_id: str, shot: Any
) -> tuple[ReferenceImage | None, list[str]]:
    """The image a bound shot starts from, or why it cannot be used.

    Problems are returned rather than swallowed. A shot that names a continuity
    source is asking to begin on that frame, so a vanished take or a missing
    file has to reach preflight as a blocker instead of quietly producing a
    clip that starts somewhere else.
    """
    if (shot.continuity_source_mode or MODE_NONE) != MODE_END_FRAME:
        return None, []
    take_id = shot.continuity_source_take_id or ""
    if not take_id:
        return None, [
            "This shot is set to continue from another take, but no take is "
            "selected. Choose one, or turn continuity off."
        ]

    frame = get_frame(db, take_id)
    if frame is None or frame.project_id != project_id:
        return None, [
            "The continuity source this shot starts from no longer exists. "
            "Pick another approved take, or turn continuity off."
        ]

    images, problems = reference_bible.resolve_images(
        db, project_id, [frame.reference_image_id or ""]
    )
    if problems:
        return None, [
            "The continuity frame this shot starts from cannot be used: "
            + problems[0].message
        ]
    return images[0], []


def source_fingerprint(db: Session, shot: Any) -> dict[str, Any]:
    """What the shot's continuity binding currently amounts to, for hashing.

    Folded into the shot's content digest, so re-cutting a hand-off frame makes
    exactly the shots that start from it stale - and nothing else.
    """
    mode = shot.continuity_source_mode or MODE_NONE
    if mode != MODE_END_FRAME:
        return {"mode": MODE_NONE, "take_id": "", "sha256": ""}
    take_id = shot.continuity_source_take_id or ""
    frame = get_frame(db, take_id) if take_id else None
    return {
        "mode": mode,
        "take_id": take_id,
        # "unresolved" rather than "" so a shot pointing at a deleted frame
        # hashes differently from one pointing at nothing.
        "sha256": (frame.sha256 or "") if frame is not None else "unresolved",
    }
