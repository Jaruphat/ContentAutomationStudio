"""What the audience did, joined to what we chose.

Nine pilots are only an experiment if the results can be read against the
decisions, and that needs two things: somewhere to put the numbers a platform
reports, and a comparison that groups episodes by the choices that varied -
pillar, hook, ending, length - rather than by title.

The arithmetic is trivial. The judgement is not, and it is all about refusing
to answer.

Three episodes per pillar cannot tell you which pillar wins. Neither can nine
when eight are unpublished. A comparison that ranks anyway produces a winner,
the winner gets scaled, and a month of work follows a number that was noise. So
this reports what it has, states the sample it had it from, and declines to
name a winner it cannot support. Declining is the part that changes what
somebody does on Monday.

Two smaller refusals in the same spirit: an episode with no numbers is counted
as unmeasured rather than as zero - counting an unpublished episode as zero
retention drags its group down and buries the format that was working - and a
dimension nobody filled in produces no groups at all, because nine blanks are
not a group of nine.
"""

from __future__ import annotations

from typing import Any

#: Below this a group is an anecdote. Three is the smallest number at which a
#: difference is worth looking at twice, and it matches the blueprint's own
#: three-episodes-per-pillar pilot.
MIN_GROUP_SIZE = 3

#: What a winner is ranked on. Views measure distribution; this measures
#: whether the thing was watched, which is what the format decision is about.
#: Named in the report because views and retention disagree constantly, and a
#: ranking that does not say which it used cannot be argued with.
RANKING_METRIC = "avg_percent_viewed"

#: How far apart two groups must be before the difference is called a result
#: rather than a tie, in percentage points of retention.
WINNING_MARGIN = 3.0

#: The choices a comparison groups by.
DIMENSIONS = ("pillar", "hook_type", "ending_type")

#: Fields that are counts, and fields that are percentages. Kept apart because
#: a percentage pasted as a fraction is the difference between 6% and 60%.
COUNT_FIELDS = (
    "views_24h", "views_7d", "impressions", "engaged_views", "likes",
    "comments", "shares", "subscribers_gained",
)
PERCENT_FIELDS = ("avg_percent_viewed", "chose_to_view_percent")


class AnalyticsError(ValueError):
    """A capture that cannot be recorded, with the reason."""


def validate_capture(values: dict[str, Any]) -> None:
    """Refuse a number that cannot mean what it says."""
    for field in COUNT_FIELDS:
        value = values.get(field)
        if value is None:
            continue
        if value < 0:
            raise AnalyticsError(f"'{field}' is {value}, and a count cannot be negative.")
    for field in PERCENT_FIELDS:
        value = values.get(field)
        if value is None:
            continue
        if not (0.0 <= value <= 100.0):
            raise AnalyticsError(
                f"'{field}' is {value}, outside 0-100. Platforms report this as "
                f"a percentage; pasted as a fraction it turns 60% into 0.6."
            )
    duration = values.get("avg_view_duration_sec")
    if duration is not None and duration < 0:
        raise AnalyticsError("Average view duration cannot be negative.")


def _mean(values: list[float]) -> float | None:
    usable = [value for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def group_by(rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    """Group measured episodes by one choice, largest group first.

    A blank value produces no group. Nine episodes with no ending type
    recorded are not a group of nine; they are a dimension nobody filled in,
    and presenting them as a result invites a conclusion about nothing.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value = str(row.get(dimension) or "").strip()
        if not value:
            continue
        buckets.setdefault(value, []).append(row)

    groups = [
        {
            "dimension": dimension,
            "value": value,
            "sample_size": len(members),
            RANKING_METRIC: _mean([m.get(RANKING_METRIC) for m in members]),
            "views_24h": _mean([m.get("views_24h") for m in members]),
            "engaged_views": _mean([m.get("engaged_views") for m in members]),
            "episode_ids": [m["project_id"] for m in members],
        }
        for value, members in buckets.items()
    ]
    groups.sort(
        key=lambda g: (
            g[RANKING_METRIC] if g[RANKING_METRIC] is not None else -1.0
        ),
        reverse=True,
    )
    return groups


def pick_winner(groups: list[dict[str, Any]], dimension: str) -> dict[str, Any]:
    """Name the best group on this dimension, or say why it cannot be named."""
    eligible = [
        group for group in groups
        if group["sample_size"] >= MIN_GROUP_SIZE
        and group[RANKING_METRIC] is not None
    ]
    if len(eligible) < 2:
        return {
            dimension: None,
            "sample_size": 0,
            "reason": (
                f"Not enough measured episodes to compare {dimension}. Two "
                f"groups of at least {MIN_GROUP_SIZE} are needed; there "
                f"{'is' if len(eligible) == 1 else 'are'} {len(eligible)}."
            ),
        }

    best, second = eligible[0], eligible[1]
    margin = best[RANKING_METRIC] - second[RANKING_METRIC]
    if margin < WINNING_MARGIN:
        return {
            dimension: None,
            "sample_size": best["sample_size"],
            "reason": (
                f"Too close to call - a tie. '{best['value']}' leads "
                f"'{second['value']}' by {margin:.1f} points of "
                f"{RANKING_METRIC}, and {WINNING_MARGIN:g} is the least this "
                f"sample can distinguish from noise."
            ),
        }
    return {
        dimension: best["value"],
        "sample_size": best["sample_size"],
        RANKING_METRIC: best[RANKING_METRIC],
        "margin": margin,
        "reason": (
            f"'{best['value']}' leads on {RANKING_METRIC} by {margin:.1f} "
            f"points across {best['sample_size']} episodes."
        ),
    }


def build_report(
    measured: list[dict[str, Any]], unmeasured_count: int
) -> dict[str, Any]:
    """The whole comparison: groups per dimension, and what can be concluded."""
    groups = {
        dimension: group_by(measured, dimension) for dimension in DIMENSIONS
    }
    return {
        "ranked_on": RANKING_METRIC,
        "minimum_group_size": MIN_GROUP_SIZE,
        "episode_count": len(measured),
        "unmeasured_count": unmeasured_count,
        "episodes": measured,
        "groups": groups,
        "winner": pick_winner(groups["pillar"], "pillar"),
        "winner_by_hook": pick_winner(groups["hook_type"], "hook_type"),
    }


__all__ = [
    "MIN_GROUP_SIZE", "RANKING_METRIC", "WINNING_MARGIN", "DIMENSIONS",
    "COUNT_FIELDS", "PERCENT_FIELDS", "AnalyticsError",
    "validate_capture", "group_by", "pick_winner", "build_report",
]
