"""What moves, said apart from how the camera behaves.

Two films measured, two ways of getting the same wrong answer.

The first asked every shot for "slow gentle camera drift" and produced
twenty-three held paintings with a push in: mean frame-to-frame difference
3.96. The second asked for "locked-off observational camera; mist drifts
across the platform, one lamp flickers, nothing else moves" - a direction that
names two things that move - and produced clips that are 86% identical frames.

The model does not weigh those clauses evenly. Given a sentence about the
camera and a sentence about the world, it takes the camera instruction as the
whole brief, and reads "nothing else moves" as permission to move nothing at
all.

So they are two fields rather than one sentence. What happens in the frame
leads, because that is what an image-to-video model is being asked to invent;
how the camera behaves follows, because it is a qualifier on that. And a
direction that describes only the camera is warned about before the render
rather than measured after it - four hundred seconds a shot is far too long to
learn this at the end.
"""

from __future__ import annotations

import re

#: Words that describe the camera rather than the world. A direction built
#: only from these has not said what should happen.
_CAMERA_WORDS = (
    "camera", "shot", "lens", "push in", "pull back", "dolly", "pan", "tilt",
    "zoom", "drift", "handheld", "locked-off", "locked off", "static",
    "tracking", "crane", "framing", "angle",
)

#: Phrases that read as a brief to hold still. Each one has produced a
#: near-frozen clip in a real run.
_STILLNESS_PHRASES = (
    "nothing else moves", "nothing moves", "no movement", "no motion",
    "completely still", "perfectly still", "frozen", "motionless",
)

_WRITE_INSTEAD = (
    "Write what happens in the frame - what moves, what changes, what a "
    "viewer would see occur - and put how the camera behaves in the camera "
    "direction, where it stays a qualifier instead of becoming the brief."
)


def compose(*, subject_motion: str, camera_motion: str) -> str:
    """One direction, with what happens leading.

    Order is the whole point. Leading with the camera tells the model the
    movement has already been decided, and it obliges by inventing none.
    """
    parts = [
        part.strip() for part in (subject_motion, camera_motion) if part.strip()
    ]
    return " ".join(parts)


def review(*, subject_motion: str, camera_motion: str) -> list[str]:
    """What is likely to come back as a still, said before it is rendered."""
    problems: list[str] = []
    subject = (subject_motion or "").strip()
    camera = (camera_motion or "").strip()
    combined = f"{subject} {camera}".lower()

    if not subject and not camera:
        problems.append(
            "This shot has no motion direction at all, so it will animate "
            "whatever the model decides - usually very little. " + _WRITE_INSTEAD
        )
        return problems

    if not subject:
        problems.append(
            "This shot's direction describes only how the camera behaves, and "
            "nothing about what happens in the frame. A previous film asked "
            "every shot for 'slow gentle camera drift' and came back as "
            "twenty-three held paintings. " + _WRITE_INSTEAD
        )

    for phrase in _STILLNESS_PHRASES:
        if phrase in combined:
            problems.append(
                f"The direction contains '{phrase}', which the model reads as "
                f"the brief rather than as a qualifier - a clip that came back "
                f"86% identical frames said exactly this. Describe what does "
                f"move and leave out what does not."
            )
            break

    if subject and _only_camera_words(subject):
        problems.append(
            "The 'what happens' direction is written in camera terms, so it "
            "says nothing about the world. " + _WRITE_INSTEAD
        )

    return problems


def _only_camera_words(text: str) -> bool:
    """Whether a sentence is about the camera and nothing else.

    Deliberately crude: it is looking for a direction with no verb about the
    world in it, and being wrong here costs a warning nobody needed rather
    than a render.
    """
    stripped = text.lower()
    for word in _CAMERA_WORDS:
        stripped = stripped.replace(word, " ")
    remaining = re.sub(r"[^a-z]+", " ", stripped).split()
    filler = {
        "a", "an", "the", "with", "and", "of", "very", "slow", "slowly",
        "subtle", "slight", "slightly", "gentle", "gently", "natural",
        "naturally", "in", "on", "at", "to", "is", "it", "its", "micro",
        "movement", "observational", "restrained", "steady", "hold", "held",
    }
    return not [word for word in remaining if word not in filler]


__all__ = ["compose", "review"]
