"""A sound at a moment, which is what an audio timeline actually is.

The blueprint's sound design is a list of times: cold night ambience from 0:00,
a clock ticking at 0:04, rail vibration rising at 0:06, a pneumatic door at
0:14, footsteps at 0:17. None of it is expressible as a property of a shot -
half of it starts inside one shot and runs through the next, and the rest is a
specific instant rather than a duration.

So a cue is a sound, a place and a level, and the place is given **relative to
a shot**. A cue pinned to an absolute second detaches from the thing it was
made for the first time somebody trims an earlier shot, and it detaches
silently: the film still renders, the door still bangs, just not when the door
opens. Anchoring to a shot means the cut can be re-edited and the sound
follows.

Two refusals come from the same principle. A cue on a shot that is not in the
cut has no moment to be placed at, and one that starts after the film ends
plays to nobody - both would otherwise be silence that reports success.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.models import SoundCue
from app.services.timeline_service import get_timeline_manifest


class SoundCueError(ValueError):
    """A cue that cannot be placed, with the reason."""


def _placements(db: Session, project_id: str) -> dict[str, dict[str, float]]:
    """Where each shot sits in the cut right now, by shot id."""
    manifest = get_timeline_manifest(db, project_id)
    return {
        item["shot_id"]: {
            "start": float(item["in_point_sec"]),
            "end": float(item["out_point_sec"]),
        }
        for item in manifest.get("items", [])
        if item.get("shot_id")
    }


def _film_length(placements: dict[str, dict[str, float]]) -> float:
    return max((entry["end"] for entry in placements.values()), default=0.0)


def create_cue(
    db: Session,
    project_id: str,
    *,
    shot_id: str,
    file_path: str,
    offset_sec: float = 0.0,
    gain_db: float = 0.0,
    label: str = "",
) -> SoundCue:
    """Attach a sound to a moment inside a shot."""
    if not os.path.isfile(file_path or ""):
        raise SoundCueError(
            f"There is no sound file at {file_path or 'that path'}."
        )
    if offset_sec < 0:
        raise SoundCueError("A cue cannot start before the shot it belongs to.")

    placements = _placements(db, project_id)
    placement = placements.get(shot_id)
    if placement is None:
        raise SoundCueError(
            "That shot is not in the cut, so there is no moment to place this "
            "cue at. Build the timeline first, or attach the cue to a shot "
            "that is on it."
        )

    start = placement["start"] + offset_sec
    length = _film_length(placements)
    if start >= length:
        raise SoundCueError(
            f"This cue would start at {start:g}s, after the film ends at "
            f"{length:g}s. It would play to nobody and say nothing about it."
        )

    cue = SoundCue(
        project_id=project_id,
        shot_id=shot_id,
        file_path=file_path,
        offset_sec=float(offset_sec),
        gain_db=float(gain_db),
        label=label or os.path.basename(file_path),
    )
    db.add(cue)
    db.commit()
    db.refresh(cue)
    return cue


def list_cues(db: Session, project_id: str) -> list[SoundCue]:
    return (
        db.query(SoundCue)
        .filter(SoundCue.project_id == project_id)
        .order_by(SoundCue.created_at)
        .all()
    )


def delete_cue(db: Session, cue: SoundCue) -> None:
    db.delete(cue)
    db.commit()


def resolve_cues(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Every cue with the moment it currently lands at.

    Resolved against the cut as it stands rather than stored, which is the
    point: re-editing the cut moves the sounds with it.
    """
    placements = _placements(db, project_id)
    length = _film_length(placements)
    resolved: list[dict[str, Any]] = []
    for cue in list_cues(db, project_id):
        placement = placements.get(cue.shot_id or "")
        if placement is None:
            # The shot left the cut after the cue was made. Reported rather
            # than dropped: a sound that quietly stopped happening is exactly
            # what somebody would spend an afternoon looking for.
            resolved.append({
                "cue_id": cue.id,
                "label": cue.label or "",
                "file_path": cue.file_path,
                "gain_db": cue.gain_db or 0.0,
                "start_sec": None,
                "placed": False,
                "runs_past_the_end": False,
                "problem": (
                    "The shot this cue is attached to is no longer in the cut."
                ),
            })
            continue
        start = placement["start"] + float(cue.offset_sec or 0.0)
        resolved.append({
            "cue_id": cue.id,
            "label": cue.label or "",
            "file_path": cue.file_path,
            "gain_db": cue.gain_db or 0.0,
            "start_sec": start,
            "placed": start < length,
            # Ambience is meant to run through a cut, so this is information
            # rather than a fault.
            "runs_past_the_end": start + _duration(cue.file_path) > length,
            "problem": "",
        })
    return resolved


def _duration(file_path: str) -> float:
    from app.services.media_probe import probe_media_file

    if not file_path or not os.path.isfile(file_path):
        return 0.0
    return float(probe_media_file(file_path).get("duration_sec") or 0.0)


__all__ = [
    "SoundCueError", "create_cue", "list_cues", "delete_cue", "resolve_cues",
]
