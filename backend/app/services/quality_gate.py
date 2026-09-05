"""Whether an episode is good enough to publish, written down.

Take review answers one question per shot: is this usable. That is the wrong
unit for the decision that actually matters, which is made once about the whole
episode: does this go out.

Nine measures with a target each, and one extra question that outranks all
nine - *would I know this was AI within two seconds?* A film that reads as
generated in the first two seconds is not rescued by nines everywhere else,
because nobody watching gets as far as the nines.

An affirmative answer must name its cause. "It looks like AI" regenerates
nothing; "the faces are plastic in shots 6 and 7" regenerates two shots. That
is the whole difference between a score and a note that can be acted on, so it
is enforced rather than encouraged.

The targets live here and only here. A gate whose thresholds are written in two
files is a gate that will eventually disagree with itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: The scale every metric is scored on.
SCALE_MIN, SCALE_MAX = 1, 10


class QualityGateError(ValueError):
    """A scorecard that cannot be evaluated, with the reason."""


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    target: int
    #: What the reviewer is actually being asked. A number with no question
    #: behind it gets scored 8 every time.
    question: str


METRICS: tuple[Metric, ...] = (
    Metric("hook_strength", "Hook strength", 8,
           "Does the first two seconds present something that has to be "
           "explained, before any setup?"),
    Metric("story_clarity", "Story clarity", 8,
           "Can a first-time viewer say afterwards what the one strange thing "
           "was, in one sentence?"),
    Metric("visual_realism", "Visual realism", 7,
           "Does this look like a frame from a low-budget drama rather than a "
           "generated picture?"),
    Metric("world_consistency", "World consistency", 8,
           "Is it the same place in every shot - same architecture, same "
           "weather, same time of night?"),
    Metric("character_consistency", "Character consistency", 8,
           "Is it the same person in every shot they appear in, including "
           "face, hair and wardrobe?"),
    Metric("ai_artifact", "Freedom from artifacts", 8,
           "Are there hands, faces, text, architecture or motion that fall "
           "apart when you look directly at them?"),
    Metric("pacing", "Pacing", 7,
           "Does every shot last as long as it needs and no longer, and does "
           "the escalation arrive before attention does?"),
    Metric("ending", "Ending and reveal", 8,
           "Does the payoff answer the hook, and does it land rather than "
           "simply stop?"),
    Metric("audio", "Audio", 7,
           "Is the voice clear over the bed, and does the sound make the world "
           "more believable rather than less?"),
)

_BY_KEY = {metric.key: metric for metric in METRICS}

#: What the two-second question refuses on, when it is answered yes.
AI_TELL_REASON = (
    "A viewer would know this was AI within two seconds, which no other score "
    "compensates for: nobody watching gets as far as the rest of the film."
)


def target_for(key: str) -> int:
    try:
        return _BY_KEY[key].target
    except KeyError as exc:
        raise QualityGateError(f"'{key}' is not a quality metric.") from exc


@dataclass
class GateResult:
    passed: bool
    #: One entry per metric that missed, with what it scored and needed.
    shortfalls: list[dict[str, Any]] = field(default_factory=list)
    #: Plain sentences naming why the gate refused, for a person to read.
    reasons: list[str] = field(default_factory=list)


def evaluate(
    scores: dict[str, Any], *, ai_tell: bool, ai_tell_causes: str
) -> GateResult:
    """Score one episode against the rubric.

    Refuses rather than guesses: a misspelt metric key scored 9 would leave
    the real metric unscored while the card looked complete, and an
    out-of-scale number means the reviewer and the rubric disagree about what
    they are doing.
    """
    unknown = sorted(set(scores) - set(_BY_KEY))
    if unknown:
        raise QualityGateError(
            f"Not quality metrics: {', '.join(unknown)}. "
            f"The rubric is: {', '.join(sorted(_BY_KEY))}."
        )
    for key, value in scores.items():
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise QualityGateError(f"'{key}' must be a number, got {value!r}.")
        if not (SCALE_MIN <= value <= SCALE_MAX):
            raise QualityGateError(
                f"'{key}' scored {value}, outside the {SCALE_MIN}-{SCALE_MAX} scale."
            )
    if ai_tell and not (ai_tell_causes or "").strip():
        raise QualityGateError(
            "Say what gives it away. 'It looks like AI' regenerates nothing; "
            "naming plastic faces, cinematic lighting, impossible architecture "
            "or unnatural motion in specific shots regenerates those shots."
        )

    shortfalls: list[dict[str, Any]] = []
    for metric in METRICS:
        scored = scores.get(metric.key)
        # An unscored metric is a shortfall, not a pass. Silence is the
        # easiest way to clear a gate by accident.
        if scored is None or scored < metric.target:
            shortfalls.append({
                "key": metric.key,
                "label": metric.label,
                "scored": scored,
                "target": metric.target,
            })

    reasons = [
        f"{item['label']} scored "
        + (f"{item['scored']:g}" if item["scored"] is not None else "nothing")
        + f", and needs {item['target']}."
        for item in shortfalls
    ]
    if ai_tell:
        reasons.insert(0, AI_TELL_REASON)

    return GateResult(
        passed=not shortfalls and not ai_tell,
        shortfalls=shortfalls,
        reasons=reasons,
    )


def describe_rubric() -> list[dict[str, Any]]:
    """The rubric as data, so a reviewer's form is built from one source."""
    return [
        {
            "key": metric.key,
            "label": metric.label,
            "target": metric.target,
            "question": metric.question,
        }
        for metric in METRICS
    ]


__all__ = [
    "METRICS", "SCALE_MIN", "SCALE_MAX", "AI_TELL_REASON",
    "QualityGateError", "GateResult", "Metric",
    "evaluate", "target_for", "describe_rubric",
]
