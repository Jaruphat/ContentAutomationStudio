"""Generation runs: the batch identity behind one press of Generate.

A run is created once, with the jobs it asked for, and is never rewritten.
Everything a caller wants to know about progress - counts, which jobs failed,
whether there is anything left to review - is derived from the jobs and takes
that point at it, so the stored row cannot drift away from what happened.

This module owns three things:

* creating runs (batch, regeneration and the migrated ones the backfill makes),
* summarising a run into what the UI needs: run-scoped counts, scene and shot
  names, and a media URL that is only published when it is actually servable,
* the duplicate-work check that stops one shot being queued twice at once.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app import paths
from app.models import GenerationJob, GenerationRun, Scene, Shot, Take
from app.services.media_probe import VIDEO_EXTENSIONS

logger = logging.getLogger("cas.generation_runs")

#: Job states that mean the shot is still being worked on. A shot in one of
#: these must not be queued again.
ACTIVE_JOB_STATUSES = ("Queued", "Running")

#: A run is one of these, derived from its jobs rather than stored.
RUN_STATUS_ORDER = ("Running", "Queued", "Failed", "Cancelled", "Completed")

KIND_BATCH = "batch"
KIND_REGENERATION = "regeneration"
KIND_MIGRATED = "migrated"

_KIND_SUFFIX = {
    KIND_REGENERATION: " (regenerate)",
    KIND_MIGRATED: " (imported)",
}

#: How far apart two legacy jobs may be and still be treated as one press of
#: Generate. Jobs from one request are written in a single commit, so anything
#: beyond a couple of seconds was a separate action.
BACKFILL_GAP = timedelta(seconds=2)


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def scene_display_name(scene: Scene | None) -> str:
    """What to call a scene on screen. Never an id."""
    if scene is None:
        return "Unassigned scene"
    title = (scene.title or "").strip()
    return title or f"Scene {scene.order}"


def shot_display_name(shot: Shot | None) -> str:
    """What to call a shot on screen: its position plus what it is of."""
    if shot is None:
        return "Deleted shot"
    label = f"Shot {shot.order}"
    descriptor = next(
        (
            value.strip()
            for value in (shot.subject, shot.action, shot.shot_type)
            if (value or "").strip()
        ),
        "",
    )
    if not descriptor:
        return label
    if len(descriptor) > 60:
        descriptor = descriptor[:57].rstrip() + "..."
    return f"{label} - {descriptor}"


def take_media_url(take: Take | None) -> str | None:
    """The URL a browser can load this take from, or None.

    Returned only when the file is really there and really inside the runtime
    data directory - the same rule the media endpoint enforces before it serves
    a byte. A link the UI cannot follow is worse than a placeholder, so a take
    whose media is missing or out of tree gets no URL at all.
    """
    if take is None or not (take.file_path or "").strip():
        return None
    if not paths.is_within_data_dir(take.file_path):
        return None
    if not os.path.isfile(take.file_path):
        return None
    if os.path.splitext(take.file_path)[1].lower() in VIDEO_EXTENSIONS:
        return f"/api/media/takes/{take.id}/thumbnail"
    return f"/api/media/takes/{take.id}/file"


# ---------------------------------------------------------------------------
# Creating runs
# ---------------------------------------------------------------------------

def next_sequence(db: Session, project_id: str) -> int:
    """The next per-project run number, counting from 1."""
    highest = (
        db.query(func.max(GenerationRun.sequence))
        .filter(GenerationRun.project_id == project_id)
        .scalar()
    )
    return int(highest or 0) + 1


def create_run(
    db: Session,
    project_id: str,
    *,
    kind: str = KIND_BATCH,
    shot_ids: Iterable[str] = (),
    created_at: datetime | None = None,
    flush: bool = True,
) -> GenerationRun:
    """Persist a new run. The caller then points its jobs at ``run.id``."""
    ids = list(shot_ids)
    sequence = next_sequence(db, project_id)
    run = GenerationRun(
        id=str(uuid.uuid4()),
        project_id=project_id,
        kind=kind,
        sequence=sequence,
        label=f"Run {sequence}{_KIND_SUFFIX.get(kind, '')}",
        requested_job_count=len(ids),
        shot_ids=ids,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(run)
    if flush:
        # Flushed rather than committed: the run and the jobs it exists for
        # have to land in the same transaction, or a failed Generate would
        # leave an empty run in the history.
        db.flush()
    return run


# ---------------------------------------------------------------------------
# Reading runs
# ---------------------------------------------------------------------------

def list_runs(db: Session, project_id: str) -> list[GenerationRun]:
    """Every run of a project, newest first."""
    return (
        db.query(GenerationRun)
        .filter(GenerationRun.project_id == project_id)
        .order_by(GenerationRun.sequence.desc())
        .all()
    )


def current_run(db: Session, project_id: str) -> GenerationRun | None:
    """The most recent run, which is the one the Generate page is about."""
    return (
        db.query(GenerationRun)
        .filter(GenerationRun.project_id == project_id)
        .order_by(GenerationRun.sequence.desc())
        .first()
    )


def get_run(db: Session, run_id: str) -> GenerationRun | None:
    return db.query(GenerationRun).filter(GenerationRun.id == run_id).first()


def shots_with_active_jobs(
    db: Session,
    shot_ids: Iterable[str],
    *,
    exclude_job_id: str | None = None,
) -> set[str]:
    """Which of these shots already have a Queued or Running job.

    Queueing a second job for a shot that is mid-flight produces two takes for
    one request and two chances to spend money on it, so both Generate and
    Regenerate refuse rather than deduplicate after the fact.
    """
    ids = [shot_id for shot_id in shot_ids if shot_id]
    if not ids:
        return set()
    query = db.query(GenerationJob.shot_id).filter(
        GenerationJob.shot_id.in_(ids),
        GenerationJob.status.in_(ACTIVE_JOB_STATUSES),
    )
    if exclude_job_id is not None:
        query = query.filter(GenerationJob.id != exclude_job_id)
    rows = query.distinct().all()
    return {row[0] for row in rows}


def run_status(counts: dict[str, int]) -> str:
    """Collapse a run's job states into the one that describes the run.

    Ordered by what the user needs to know first: something is still running,
    something is still queued, something failed, everything finished.
    """
    for status in RUN_STATUS_ORDER:
        if counts.get(status.lower()):
            return status
    return "Empty"


def summarise_run(
    db: Session,
    run: GenerationRun,
    *,
    job_status: str | None = None,
) -> dict[str, Any]:
    """Everything the UI needs about one run.

    ``job_status`` filters only the ``jobs`` list; the counts always describe
    the whole run, so narrowing the view can never misreport what happened.
    """
    jobs = (
        db.query(GenerationJob)
        .filter(GenerationJob.run_id == run.id)
        .order_by(GenerationJob.created_at)
        .all()
    )

    counts = {
        "queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0,
    }
    for job in jobs:
        key = (job.status or "").lower()
        if key in counts:
            counts[key] += 1

    shot_ids = {job.shot_id for job in jobs}
    shots = (
        {
            shot.id: shot
            for shot in db.query(Shot).filter(Shot.id.in_(shot_ids)).all()
        }
        if shot_ids
        else {}
    )
    scene_ids = {shot.scene_id for shot in shots.values()}
    scenes = (
        {
            scene.id: scene
            for scene in db.query(Scene).filter(Scene.id.in_(scene_ids)).all()
        }
        if scene_ids
        else {}
    )

    takes_by_job: dict[str, Take] = {}
    pending_take_count = 0
    if jobs:
        for take in (
            db.query(Take)
            .filter(Take.job_id.in_([job.id for job in jobs]))
            .order_by(Take.created_at)
            .all()
        ):
            takes_by_job.setdefault(take.job_id, take)
            if take.review_status == "Pending":
                pending_take_count += 1

    entries: list[dict[str, Any]] = []
    for job in jobs:
        if job_status and (job.status or "") != job_status:
            continue
        shot = shots.get(job.shot_id)
        scene = scenes.get(shot.scene_id) if shot else None
        take = takes_by_job.get(job.id)
        entries.append({
            "job_id": job.id,
            "run_id": run.id,
            "shot_id": job.shot_id,
            "scene_id": shot.scene_id if shot else None,
            "scene_name": scene_display_name(scene),
            "shot_name": shot_display_name(shot),
            "status": job.status,
            "attempts": job.attempts or 0,
            "error_message": job.error_message,
            "media_provider_id": job.media_provider_id or "comfyui",
            "media_model": job.media_model or "",
            "seed": job.seed,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "take_id": take.id if take else None,
            "take_review_status": take.review_status if take else None,
            "thumbnail_url": take_media_url(take),
        })

    terminal = counts["queued"] == 0 and counts["running"] == 0
    return {
        "id": run.id,
        "project_id": run.project_id,
        "kind": run.kind,
        "sequence": run.sequence,
        "label": run.label or f"Run {run.sequence}",
        "created_at": run.created_at,
        "requested_job_count": run.requested_job_count or 0,
        "shot_count": len(shot_ids),
        "total_jobs": len(jobs),
        "status": run_status(counts),
        "terminal": terminal,
        "pending_take_count": pending_take_count,
        # The one question the Generate page has to answer at the end of a run:
        # is there anything to go and look at?
        "ready_for_review": terminal and pending_take_count > 0,
        "jobs": entries,
        **counts,
    }


def matches_status_filter(summary: dict[str, Any], wanted: str) -> bool:
    """Whether a run summary satisfies a ``?status=`` value.

    ``active`` means "not finished", which is the question the UI actually
    asks; everything else compares against the run's derived status.
    """
    wanted = (wanted or "").strip().lower()
    if not wanted:
        return True
    if wanted == "active":
        return not summary["terminal"]
    if wanted == "terminal":
        return summary["terminal"]
    return summary["status"].lower() == wanted


# ---------------------------------------------------------------------------
# Migration backfill
# ---------------------------------------------------------------------------

_LEGACY_JOB_DEFAULTS: dict[str, Any] = {
    "workflow_version": "",
    "workflow_snapshot_path": "",
    "workflow_sha256": "",
    "parameter_map": {},
    "media_provider_id": "comfyui",
    "media_model": "workflow",
    "request_params": {},
    "usage": {},
    "provenance": {},
    "prompt_revision": 0,
    "prompt_sha256": "",
    "content_sha256": "",
    "reference_image_ids": [],
    "reference_sha256s": [],
    "reference_provenance": {},
    "character_set_ids": [],
    "character_set_sha256s": [],
    "continuity_source_sha256": "",
    "status": "Queued",
    "attempts": 0,
    "outputs": [],
}


def backfill_legacy_job_defaults(engine) -> int:
    """Fill response-required fields added after legacy jobs were written."""
    inspector = inspect(engine)
    if "generation_jobs" not in inspector.get_table_names():
        return 0
    columns = {column["name"] for column in inspector.get_columns("generation_jobs")}
    updated = 0
    with engine.begin() as conn:
        for column, value in _LEGACY_JOB_DEFAULTS.items():
            if column not in columns:
                continue
            stored = json.dumps(value) if isinstance(value, (dict, list)) else value
            result = conn.execute(
                text(
                    f'UPDATE generation_jobs SET "{column}" = :value '
                    f'WHERE "{column}" IS NULL'
                ),
                {"value": stored},
            )
            updated = max(updated, result.rowcount or 0)
    if updated:
        logger.info("Backfilled response defaults on %d legacy generation job(s)", updated)
    return updated

def backfill_legacy_runs(engine) -> int:
    """Give jobs written before runs existed a run to belong to.

    Runs are reconstructed from creation times: one Generate writes its jobs in
    a single commit, so a cluster of jobs within ``BACKFILL_GAP`` of each other
    was one press. This is a heuristic about the past, which is why those runs
    are labelled ``migrated`` rather than passed off as recorded ones - but it
    keeps every existing job and take visible in the history instead of
    stranding them outside every run.

    Returns the number of jobs adopted. Safe to run on every startup: jobs that
    already have a run are never touched.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not {"generation_jobs", "generation_runs"} <= tables:
        return 0

    adopted = 0
    with engine.begin() as conn:
        orphans = conn.execute(text(
            "SELECT j.id, s.project_id, j.shot_id, j.created_at "
            "FROM generation_jobs j "
            "JOIN shots sh ON sh.id = j.shot_id "
            "JOIN scenes s ON s.id = sh.scene_id "
            "WHERE j.run_id IS NULL "
            "ORDER BY s.project_id, j.created_at, j.id"
        )).all()
        if not orphans:
            return 0

        by_project: dict[str, list[tuple]] = {}
        for row in orphans:
            by_project.setdefault(row[1], []).append(row)

        for project_id, rows in by_project.items():
            sequence = int(conn.execute(
                text(
                    "SELECT COALESCE(MAX(sequence), 0) FROM generation_runs "
                    "WHERE project_id = :p"
                ),
                {"p": project_id},
            ).scalar() or 0)

            for cluster in _cluster_by_time(rows):
                sequence += 1
                run_id = str(uuid.uuid4())
                created_at = cluster[0][3]
                shot_ids = list(dict.fromkeys(row[2] for row in cluster))
                conn.execute(
                    text(
                        "INSERT INTO generation_runs "
                        "(id, project_id, kind, sequence, label, "
                        " requested_job_count, shot_ids, created_at) "
                        "VALUES (:id, :project_id, :kind, :sequence, :label, "
                        "        :count, :shot_ids, :created_at)"
                    ),
                    {
                        "id": run_id,
                        "project_id": project_id,
                        "kind": KIND_MIGRATED,
                        "sequence": sequence,
                        "label": f"Run {sequence}{_KIND_SUFFIX[KIND_MIGRATED]}",
                        "count": len(cluster),
                        "shot_ids": _json_list(shot_ids),
                        "created_at": created_at,
                    },
                )
                job_ids = [row[0] for row in cluster]
                _update_in(
                    conn,
                    "UPDATE generation_jobs SET run_id = :run_id WHERE id IN",
                    job_ids,
                    {"run_id": run_id},
                )
                if "takes" in tables:
                    _update_in(
                        conn,
                        "UPDATE takes SET run_id = :run_id "
                        "WHERE run_id IS NULL AND job_id IN",
                        job_ids,
                        {"run_id": run_id},
                    )
                adopted += len(cluster)

    logger.info("Backfilled %d generation job(s) into migrated runs", adopted)
    return adopted


def _cluster_by_time(rows: list[tuple]) -> list[list[tuple]]:
    """Split time-ordered job rows wherever the gap exceeds BACKFILL_GAP."""
    clusters: list[list[tuple]] = []
    previous: datetime | None = None
    for row in rows:
        created = _as_datetime(row[3])
        if (
            previous is None
            or created is None
            or created - previous > BACKFILL_GAP
        ):
            clusters.append([])
        clusters[-1].append(row)
        previous = created if created is not None else previous
    return clusters


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _json_list(values: list[str]) -> str:
    return json.dumps(values)


def _update_in(conn, prefix: str, ids: list[str], params: dict[str, Any]) -> None:
    """Run an ``... IN (...)`` update with bound parameters, in safe batches."""
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        names = [f"id{start + index}" for index in range(len(chunk))]
        placeholders = ", ".join(f":{name}" for name in names)
        conn.execute(
            text(f"{prefix} ({placeholders})"),
            {**params, **dict(zip(names, chunk))},
        )

