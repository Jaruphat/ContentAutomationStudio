"""How long a run will take, from how long the same route took before.

Cost is answered before a run and time is not, which on local hardware is the
wrong way round: nothing here is billed and a shot takes minutes. Twenty-three
shots is an hour on this machine, and the only way to learn that was to start
one and watch it.

Everything below is measured. Where a route has no history the answer is that
there is no answer, because somebody plans an evening around this and an
invented duration is worse than an absent one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import GenerationJob

logger = logging.getLogger("cas.run_duration")

#: How many recent completions to read per route. Enough for a median to mean
#: something, few enough that last month's hardware does not outvote today's.
SAMPLE_SIZE = 12
#: Completions older than this are ignored: models, step counts and the
#: machine itself change, and an old run is not evidence about the next one.
MAX_AGE = timedelta(days=14)


def _elapsed(job: GenerationJob) -> float | None:
    if not (job.started_at and job.completed_at):
        return None
    seconds = (job.completed_at - job.started_at).total_seconds()
    return seconds if seconds > 0 else None


def seconds_for_workflow(db: Session, workflow_id: str | None) -> int | None:
    """The median completion time of this workflow's recent runs.

    A median rather than a mean, so one job that waited behind a cold model
    load does not make every later prediction wrong.
    """
    if not workflow_id:
        return None
    cutoff = datetime.now(timezone.utc) - MAX_AGE
    jobs = (
        db.query(GenerationJob)
        .filter(
            GenerationJob.workflow_id == workflow_id,
            GenerationJob.status == "Completed",
        )
        .order_by(GenerationJob.completed_at.desc())
        .limit(SAMPLE_SIZE * 3)
        .all()
    )
    samples: list[float] = []
    for job in jobs:
        completed = job.completed_at
        if completed is not None and completed.tzinfo is None:
            completed = completed.replace(tzinfo=timezone.utc)
        if completed is not None and completed < cutoff:
            continue
        elapsed = _elapsed(job)
        if elapsed is not None:
            samples.append(elapsed)
        if len(samples) >= SAMPLE_SIZE:
            break
    if not samples:
        return None
    samples.sort()
    middle = len(samples) // 2
    median = (
        samples[middle]
        if len(samples) % 2
        else (samples[middle - 1] + samples[middle]) / 2
    )
    return int(round(median))


def estimate_run(db: Session, workflow_ids: list[str | None]) -> dict[str, Any]:
    """What a whole run is likely to take, and how much of it is guesswork.

    Shots on a route with no history are counted separately rather than given
    the average of the others: a partial total presented as a complete one is
    how an hour becomes three.
    """
    cache: dict[str | None, int | None] = {}
    total = 0
    known = 0
    unknown = 0
    for workflow_id in workflow_ids:
        if workflow_id not in cache:
            cache[workflow_id] = seconds_for_workflow(db, workflow_id)
        seconds = cache[workflow_id]
        if seconds is None:
            unknown += 1
        else:
            total += seconds
            known += 1
    return {
        "seconds": total if known else None,
        "known_shots": known,
        "unknown_shots": unknown,
    }


def describe(estimate: dict[str, Any]) -> str:
    """The estimate in words, honest about what it does not cover."""
    seconds = estimate.get("seconds")
    if not seconds:
        return "No timing history for this route yet."
    minutes = seconds / 60
    rough = (
        f"about {minutes:.0f} min"
        if minutes < 90
        else f"about {minutes / 60:.1f} hours"
    )
    unknown = estimate.get("unknown_shots") or 0
    if unknown:
        return f"{rough} for {estimate['known_shots']} shot(s), plus {unknown} never run before"
    return rough
