"""A line too long for its shot, said before the render rather than after.

Every cut of the first ODDVERSE episode came back with the same warning: four
or five narration lines run past the shot they belong to. It arrived at the
end, after forty minutes of generation and a render, and it was never a fault
in the voice - it is a script and a shot plan that disagree. The blueprint
writes seven sentences for thirty-two seconds, which is about 150 words per
minute and entirely reasonable; distributed across shots of four, two and three
seconds, several of them do not fit the shot they were assigned to.

All of that is knowable the moment the timeline is built. It needs no audio, no
provider and no money - only the words, the seconds, and a rate.

The tolerance is deliberate. Speaking rate is not a constant, and a check that
fires on a tenth of a second is ignored within a day; one that fires when a
line cannot fit at any plausible rate is worth reading.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Shot
from app.services.subtitle_service import DIALOGUE_FIELD
from app.services.timeline_service import get_timeline_manifest

#: The rate the Voice Bible asks for. Named here so the check and the
#: direction given to the narrator cannot drift apart.
WORDS_PER_MINUTE = 150.0

#: How much a line may exceed its shot before it is worth mentioning. A
#: narrator lands within a second of an estimate; a line that needs two more
#: seconds than it has was written for a different shot.
TOLERANCE_SEC = 0.75


def speaking_seconds(text: str) -> float:
    """How long a line takes to say, in words rather than characters.

    "Antidisestablishmentarianism" is one word and a second and a half;
    twenty-eight characters of "I do not know" is four words and under one.
    """
    words = len((text or "").split())
    return words / WORDS_PER_MINUTE * 60.0 if words else 0.0


def review(db: Session, project_id: str) -> list[dict[str, Any]]:
    """Every placed line that cannot fit the shot it belongs to."""
    manifest = get_timeline_manifest(db, project_id)
    shot_ids = [item.get("shot_id") for item in manifest.get("items", [])]
    shots = {
        shot.id: shot
        for shot in db.query(Shot).filter(Shot.id.in_(shot_ids)).all()
    } if shot_ids else {}

    problems: list[dict[str, Any]] = []
    for item in manifest.get("items", []):
        shot = shots.get(item.get("shot_id"))
        if shot is None:
            continue
        line = (getattr(shot, DIALOGUE_FIELD, "") or "").strip()
        if not line:
            continue
        needs = speaking_seconds(line)
        has = float(item["duration_sec"])
        if needs <= has + TOLERANCE_SEC:
            continue
        problems.append({
            "shot_id": shot.id,
            "order": item["order"],
            "needs_sec": needs,
            "has_sec": has,
            "shortfall_sec": needs - has,
            "text": line,
            # "Too long" leaves the fix to guesswork; the numbers are an edit
            # somebody can make.
            "message": (
                f"Shot {item['order']} is held for {has:.1f} seconds and its "
                f"line needs about {needs:.1f} seconds at "
                f"{WORDS_PER_MINUTE:g} words per minute. Lengthen the shot, "
                f"or shorten the line."
            ),
        })
    return problems


__all__ = ["WORDS_PER_MINUTE", "TOLERANCE_SEC", "speaking_seconds", "review"]
