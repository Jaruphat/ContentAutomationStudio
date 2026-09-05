"""Choosing what to make, before an hour of GPU time is spent on it.

The blueprint's first step was a scoring exercise: nine niches rated on viral
potential, repeatability, fit with the tools to hand, story potential,
automation difficulty and policy risk, weighted, ranked, top three taken
forward. It was done once, in a document. Every premise since has been chosen
the way premises usually are - whichever one was in mind that morning.

The same rubric, kept beside the channel it belongs to, is worth more than the
arithmetic suggests. It makes the choice comparable across weeks, and it makes
rejecting an idea cheap - which matters because every premise that survives
this screen costs an hour of rendering to find out about.

One gate outranks the scores, the same way the two-second question does at the
other end of the pipeline. The blueprint's story rule: every episode must
answer in one sentence *what is the one strange thing?* A premise that cannot
is rejected before it is scored, because it does not become a better film with
better production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCALE_MIN, SCALE_MAX = 1, 10

#: The rule's whole point is that it fits in a sentence. This is a cap that
#: catches a paragraph, not a style guide.
MAX_STRANGE_THING_WORDS = 30

STATUS_CANDIDATE = "candidate"
STATUS_IN_PRODUCTION = "in_production"
STATUS_REJECTED = "rejected"


class PremiseError(ValueError):
    """A premise that cannot be recorded or scored, with the reason."""


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    weight: float
    question: str


CRITERIA: tuple[Criterion, ...] = (
    Criterion("viral_potential", "Viral potential", 0.25,
              "Would somebody stop scrolling on the first two seconds of this, "
              "without knowing the channel?"),
    Criterion("story_potential", "Story potential", 0.20,
              "Is there a turn in it - something that changes what the opening "
              "meant - rather than only an image?"),
    Criterion("repeatability", "Repeatability", 0.20,
              "Could ten more episodes be made in this shape without any of "
              "them feeling like a template?"),
    Criterion("tool_fit", "Fit with the tools", 0.15,
              "Can the pipeline as it stands actually make this look right, "
              "or does it need something that does not exist yet?"),
    Criterion("automation_ease", "Ease of automation", 0.10,
              "How much of this can be produced without hand work - "
              "compositing, retakes, fixing text?"),
    Criterion("policy_safety", "Policy safety", 0.10,
              "Is it clearly original and clearly within platform policy, or "
              "does it sit near a line?"),
)

_BY_KEY = {criterion.key: criterion for criterion in CRITERIA}


@dataclass
class ScoreResult:
    total: float
    #: The criterion furthest below the others, so a ranking leaves something
    #: to fix rather than only a verdict.
    weakest: dict[str, Any] = field(default_factory=dict)
    breakdown: list[dict[str, Any]] = field(default_factory=list)


def score(scores: dict[str, Any]) -> ScoreResult:
    """Weight and total a scorecard, out of one hundred."""
    unknown = sorted(set(scores) - set(_BY_KEY))
    if unknown:
        raise PremiseError(
            f"Not scoring criteria: {', '.join(unknown)}. "
            f"The rubric is: {', '.join(sorted(_BY_KEY))}."
        )
    missing = sorted(set(_BY_KEY) - set(scores))
    if missing:
        # Counted as zero it drags a good premise below a mediocre one that
        # was filled in completely; ignored, it flatters whoever skipped it.
        raise PremiseError(
            f"Unscored: {', '.join(missing)}. Every criterion has to be "
            f"scored, or the totals are not comparable between premises."
        )
    for key, value in scores.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise PremiseError(f"'{key}' must be a number, got {value!r}.")
        if not (SCALE_MIN <= value <= SCALE_MAX):
            raise PremiseError(
                f"'{key}' scored {value}, outside the {SCALE_MIN}-{SCALE_MAX} scale."
            )

    breakdown = [
        {
            "key": criterion.key,
            "label": criterion.label,
            "scored": float(scores[criterion.key]),
            "weight": criterion.weight,
            "contribution": float(scores[criterion.key]) * criterion.weight * 10,
        }
        for criterion in CRITERIA
    ]
    weakest = min(breakdown, key=lambda entry: entry["scored"])
    return ScoreResult(
        total=sum(entry["contribution"] for entry in breakdown),
        weakest=weakest,
        breakdown=breakdown,
    )


def validate_one_strange_thing(text: str) -> str:
    """The gate that outranks the scores.

    A premise that cannot name its one strange thing in a sentence has not
    found its idea yet, and no amount of production rescues that.
    """
    value = (text or "").strip()
    if not value:
        raise PremiseError(
            "Say the one strange thing, in one sentence. A premise that "
            "cannot answer that does not become a better film with better "
            "production - it is rejected here so it costs a minute instead of "
            "an hour of rendering."
        )
    words = len(value.split())
    if words > MAX_STRANGE_THING_WORDS:
        raise PremiseError(
            f"The one strange thing runs to {words} words. The rule is one "
            f"sentence; needing a paragraph means the idea has not been found "
            f"yet."
        )
    return value


def describe_rubric() -> list[dict[str, Any]]:
    return [
        {
            "key": criterion.key,
            "label": criterion.label,
            "weight": criterion.weight,
            "question": criterion.question,
        }
        for criterion in CRITERIA
    ]


__all__ = [
    "CRITERIA", "Criterion", "PremiseError", "ScoreResult",
    "SCALE_MIN", "SCALE_MAX", "MAX_STRANGE_THING_WORDS",
    "STATUS_CANDIDATE", "STATUS_IN_PRODUCTION", "STATUS_REJECTED",
    "score", "validate_one_strange_thing", "describe_rubric",
]
