"""Regenerating for a stated reason, instead of rolling the dice again.

Regeneration was one button that picked a new seed. When a take is nearly
right that is the wrong move: the seed is most of what fixes composition, so
re-rolling throws away the framing that worked along with the thing that did
not. The only alternative was editing the prompt by hand, which changes the
shot's content revision and marks every earlier take of it stale - a heavy
price for "try that again, later in the day".

What people actually ask for is small and finite, and two of the commonest
requests want opposite things from the sampler:

* *Same shot, different framing* needs a **new seed**. Keeping it and asking
  for a wider shot mostly returns the same shot.
* *Same framing, different light* needs the **seed held**. Holding it while
  the prompt changes is what makes the structure persist and the light move,
  which is the entire request.

That is not something a user should have to know, so an intent carries both
the directive and the seed policy. The shot is never edited: an intent asks
for one take, and the directive rides on the job that produces it.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownIntent(ValueError):
    """A named intent that is not in the vocabulary.

    Raised rather than ignored: silently dropping an unrecognised intent
    returns an ordinary re-roll while the user believes they asked for
    something specific, and the take that comes back looks like the feature
    not working rather than the name being wrong.
    """


@dataclass(frozen=True)
class Intent:
    key: str
    label: str
    #: Appended to the compiled positive prompt for this run only.
    directive: str
    #: Whether to reuse the seed of the take being improved. See the module
    #: docstring: this is the half users cannot be expected to work out.
    keep_seed: bool
    #: Shown beside the choice, so a dropdown of verbs is not a worse prompt
    #: box. It says what will happen to the image and why.
    explanation: str


_INTENTS: tuple[Intent, ...] = (
    Intent(
        key="reframe",
        label="Different framing",
        directive="recompose this shot with different framing",
        keep_seed=False,
        explanation=(
            "Re-rolls the seed, because the seed is most of what fixes a "
            "composition. Everything else about the shot is kept."
        ),
    ),
    Intent(
        key="relight",
        label="Same framing, different light",
        directive="the same composition under different lighting",
        keep_seed=True,
        explanation=(
            "Holds the seed of the take you are improving, which is what "
            "keeps the framing while the light and time of day move."
        ),
    ),
    Intent(
        key="restage",
        label="Different staging",
        directive="stage the same moment differently, with the subject placed anew",
        keep_seed=False,
        explanation=(
            "Re-rolls the seed. Where the subject stands is decided with the "
            "composition, so holding it would return the same blocking."
        ),
    ),
    Intent(
        key="closer",
        label="Closer on the subject",
        directive="a tighter shot, closer on the subject",
        keep_seed=False,
        explanation=(
            "Re-rolls the seed, because shot size is part of the composition "
            "and a held seed resists changing it."
        ),
    ),
    Intent(
        key="wider",
        label="Wider, more of the scene",
        directive="a wider shot showing more of the surrounding scene",
        keep_seed=False,
        explanation=(
            "Re-rolls the seed, because shot size is part of the composition "
            "and a held seed resists changing it."
        ),
    ),
    Intent(
        key="restyle",
        label="Same framing, different treatment",
        directive="the same composition rendered with a different treatment",
        keep_seed=True,
        explanation=(
            "Holds the seed so the picture stays the same picture while its "
            "colour, texture and finish move."
        ),
    ),
)

_BY_KEY = {intent.key: intent for intent in _INTENTS}


def all_intents() -> tuple[Intent, ...]:
    """Every intent, in the order a picker should offer them."""
    return _INTENTS


def get(key: str | None) -> Intent | None:
    """Look one up. Blank means the plain re-roll that already existed."""
    normalised = (key or "").strip().lower()
    if not normalised:
        return None
    try:
        return _BY_KEY[normalised]
    except KeyError as exc:
        offered = ", ".join(sorted(_BY_KEY))
        raise UnknownIntent(
            f"'{key}' is not a regeneration intent. Use one of: {offered}."
        ) from exc


def apply_to_prompt(prompt: str, intent: Intent | None, note: str = "") -> str:
    """Add the directive, and the user's own words, to one run's prompt.

    Appended rather than substituted: the shot's compiled prompt is still what
    the shot is, and the intent is a modification asked of this take only.
    """
    parts = [prompt.strip()] if prompt and prompt.strip() else []
    if intent is not None:
        parts.append(intent.directive)
    if (note or "").strip():
        parts.append(note.strip())
    return ". ".join(part.rstrip(". ") for part in parts if part).strip()


__all__ = ["Intent", "UnknownIntent", "all_intents", "get", "apply_to_prompt"]
