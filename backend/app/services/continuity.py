"""Lightweight continuity checks for explicit recurring-prop requirements."""

from __future__ import annotations

import re
from typing import Any

_COUNT_WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|\\d+"
_REQUIREMENT_PATTERNS = (
    re.compile(
        rf"(?:exactly\s+)?(?P<count>{_COUNT_WORDS})\s+recurring\s+"
        r"(?P<color>[a-z][\w-]*)\s+(?P<identity>[a-z][\w -]*?)"
        r"(?=\s+(?:throughout|across|in every)\b|[.;,]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"recurring\s+(?:prop|object)\s*:\s*(?:exactly\s+)?"
        rf"(?P<count>{_COUNT_WORDS})\s+(?P<color>[a-z][\w-]*)\s+"
        r"(?P<identity>[a-z][\w -]*?)(?=[.;,]|$)",
        re.IGNORECASE,
    ),
)
_COUNT_ALIASES = {
    "one": ("one", "single", "1"),
    "two": ("two", "pair", "2"),
}


def _parse_requirement(text: str) -> dict[str, str] | None:
    for pattern in _REQUIREMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            return {
                key: " ".join(value.casefold().split())
                for key, value in match.groupdict().items()
            }
    return None


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE) is not None


def find_continuity_issues(
    shots: list[dict[str, Any]],
    requirements: list[str | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return shot-addressable issues for explicit recurring prop constraints.

    A requirement may be plain guidance or a mapping with ``text`` and the
    ``shot_ids`` to which a Story Bible location constraint applies.
    """
    issues: list[dict[str, Any]] = []
    for raw in requirements:
        text = str(raw.get("text") or "") if isinstance(raw, dict) else str(raw)
        parsed = _parse_requirement(text)
        if parsed is None:
            continue
        scoped_ids = set(raw.get("shot_ids") or []) if isinstance(raw, dict) else set()
        identity = parsed["identity"]
        identity_words = identity.split()

        for shot in shots:
            shot_id = str(shot.get("id") or "")
            source = " ".join(
                str(shot.get(field) or "")
                for field in ("subject", "action", "environment")
            )
            if scoped_ids:
                relevant = shot_id in scoped_ids
            else:
                relevant = all(_contains_phrase(source, word) for word in identity_words)
            if not relevant:
                continue

            prompt = str(shot.get("image_prompt") or shot.get("video_prompt") or "")
            count = parsed["count"]
            aliases = _COUNT_ALIASES.get(count, (count,))
            missing: list[str] = []
            if not any(_contains_phrase(prompt, alias) for alias in aliases):
                missing.append(f"count:{count}")
            if not _contains_phrase(prompt, parsed["color"]):
                missing.append(f"color:{parsed['color']}")
            if not all(_contains_phrase(prompt, word) for word in identity_words):
                missing.append(f"identity:{identity}")
            if missing:
                issues.append({
                    "shot_id": shot_id,
                    "code": "recurring_prop_continuity",
                    "requirement": text,
                    "missing": missing,
                })
    return issues
