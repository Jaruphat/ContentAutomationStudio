"""Recover take and timeline lineage on a database written before it existed.

``ensure_schema`` can add a column but only as NULL, and every consumer of a
take's lineage compares it for equality. Left alone, that turns an upgrade into
a silent data loss: legacy approved takes stop matching their shots, the auto
build places nothing, and the cut the user had is replaced by an empty one.

Two passes fix that, in order of how much they can prove:

1. **Recovered.** The generation job that produced a take recorded exactly what
   it was compiled from. Copying that onto the take is not a guess.
2. **Unverified.** Where no job survives, or the job predates digests either,
   nothing can be recovered - so the take is marked
   ``legacy_unverified_lineage`` rather than given a lineage it never had.
   Downstream that is a state of its own: placeable, but never reported as
   verified (see :mod:`app.services.timeline_service`).

Both passes only ever touch rows whose columns are still NULL, so running this
on every startup is a no-op once a database has been migrated.
"""

import json
import logging

from sqlalchemy import inspect, text

from app.services.revisions import (
    FIRST_TRACKED_REVISION,
    LEGACY_BASELINE_FLAG,
    LEGACY_LINEAGE_FLAG,
)

logger = logging.getLogger("cas.lineage_backfill")

#: Columns added to ``takes`` after lineage tracking arrived, with the value a
#: row that predates them should carry when nothing better can be recovered.
_TAKE_LINEAGE_DEFAULTS: dict[str, object] = {
    "prompt_revision": 0,
    "prompt_sha256": "",
    "content_sha256": "",
    "reference_image_ids": [],
    "reference_sha256s": [],
    "lineage": {},
    "media_provider_id": "comfyui",
    "media_model": "workflow",
    "request_params": {},
    "usage": {},
    "provenance": {},
    "review_status": "Pending",
    "file_path": "",
    "thumbnail_path": "",
    "duration_sec": 0.0,
    "width": 0,
    "height": 0,
    "frame_rate": 0.0,
    "codec": "",
    "notes": "",
}

#: The same for ``timeline_items``: a row with NULL revisions reads as a
#: mismatch against any shot, which is what makes a migrated cut look stale.
_TIMELINE_LINEAGE_COLUMNS = ("take_prompt_revision", "shot_prompt_revision")


def _record_legacy_baselines(conn) -> int:
    """Stamp each flagged take with the revision of the shot it belongs to.

    A migrated shot has no revision yet - the column was added moments ago and
    the first revision refresh derives it - so the value it will settle on,
    :data:`FIRST_TRACKED_REVISION`, is what a NULL means here. Idempotent: a
    take that already carries a baseline is not selected.
    """
    rows = conn.execute(text(
        "SELECT t.id, s.prompt_revision FROM takes t "
        "LEFT JOIN shots s ON s.id = t.shot_id "
        f"WHERE t.lineage LIKE '%\"{LEGACY_LINEAGE_FLAG}\"%' "
        f"  AND t.lineage NOT LIKE '%\"{LEGACY_BASELINE_FLAG}\"%'"
    )).all()
    if not rows:
        return 0

    for take_id, shot_revision in rows:
        baseline = (
            int(shot_revision)
            if isinstance(shot_revision, int) and shot_revision >= FIRST_TRACKED_REVISION
            else FIRST_TRACKED_REVISION
        )
        conn.execute(
            text("UPDATE takes SET lineage = :lineage WHERE id = :id"),
            {
                "lineage": json.dumps({
                    LEGACY_LINEAGE_FLAG: True,
                    LEGACY_BASELINE_FLAG: baseline,
                }),
                "id": take_id,
            },
        )
    logger.info(
        "Recorded a lineage baseline on %d legacy take(s)", len(rows)
    )
    return len(rows)


def backfill_take_lineage(engine) -> int:
    """Give legacy takes the lineage of the job that produced them.

    Returns the number of takes touched.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "takes" not in tables:
        return 0
    columns = {column["name"] for column in inspector.get_columns("takes")}

    touched = 0
    with engine.begin() as conn:
        # 1. Recover what the job row still knows.
        if "generation_jobs" in tables:
            recoverable = [
                name
                for name in (
                    "prompt_revision",
                    "prompt_sha256",
                    "content_sha256",
                    "reference_image_ids",
                    "reference_sha256s",
                )
                if name in columns
            ]
            for name in recoverable:
                result = conn.execute(text(
                    f'UPDATE takes SET "{name}" = ('
                    f'  SELECT j."{name}" FROM generation_jobs j '
                    f'  WHERE j.id = takes.job_id'
                    f') '
                    f'WHERE "{name}" IS NULL AND job_id IS NOT NULL AND EXISTS ('
                    f'  SELECT 1 FROM generation_jobs j '
                    f'  WHERE j.id = takes.job_id AND j."{name}" IS NOT NULL'
                    f')'
                ))
                touched = max(touched, result.rowcount or 0)

        # 2. Mark whatever is still unrecoverable, before filling defaults -
        #    once the digests are "" they are indistinguishable from a take
        #    that genuinely resolved to nothing.
        if {"lineage", "prompt_sha256", "content_sha256"} <= columns:
            flagged = conn.execute(
                text(
                    "UPDATE takes SET lineage = :flag "
                    "WHERE lineage IS NULL "
                    "  AND COALESCE(prompt_sha256, '') = '' "
                    "  AND COALESCE(content_sha256, '') = ''"
                ),
                {"flag": json.dumps({LEGACY_LINEAGE_FLAG: True})},
            )
            if flagged.rowcount:
                logger.info(
                    "Marked %d legacy take(s) as unverified lineage",
                    flagged.rowcount,
                )
                touched = max(touched, flagged.rowcount)

        # 2b. Record the shot revision each flagged take is unverifiable at.
        #     Without it "unverified" never expires, and a take nothing can
        #     vouch for keeps passing as deliverable however far the shot moves
        #     afterwards. Runs over rows this backfill has just flagged and
        #     over rows an earlier build flagged without a baseline, which is
        #     why it matches on the absence of the key rather than on NULL.
        if "lineage" in columns and "shots" in tables:
            touched = max(touched, _record_legacy_baselines(conn))

        # 3. A take is at least as old as the job that made it; failing that,
        #    it is as old as the migration. Either beats a NULL the response
        #    schema cannot represent.
        if "created_at" in columns:
            if "generation_jobs" in tables:
                conn.execute(text(
                    "UPDATE takes SET created_at = ("
                    "  SELECT j.created_at FROM generation_jobs j "
                    "  WHERE j.id = takes.job_id"
                    ") "
                    "WHERE created_at IS NULL AND job_id IS NOT NULL AND EXISTS ("
                    "  SELECT 1 FROM generation_jobs j "
                    "  WHERE j.id = takes.job_id AND j.created_at IS NOT NULL"
                    ")"
                ))
            result = conn.execute(text(
                "UPDATE takes SET created_at = CURRENT_TIMESTAMP "
                "WHERE created_at IS NULL"
            ))
            touched = max(touched, result.rowcount or 0)

        # 4. Fill the rest so every response field has a value.
        for name, value in _TAKE_LINEAGE_DEFAULTS.items():
            if name not in columns:
                continue
            stored = json.dumps(value) if isinstance(value, (dict, list)) else value
            result = conn.execute(
                text(f'UPDATE takes SET "{name}" = :value WHERE "{name}" IS NULL'),
                {"value": stored},
            )
            touched = max(touched, result.rowcount or 0)

    if touched:
        logger.info("Backfilled lineage on %d legacy take(s)", touched)
    return touched


def backfill_timeline_lineage(engine) -> int:
    """Fill the revision columns a migrated timeline row has as NULL.

    The take's own recorded revision, and the current revision of the shot the
    item points at, are the only honest values available - and they are the two
    the manifest compares.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "timeline_items" not in tables:
        return 0
    columns = {column["name"] for column in inspector.get_columns("timeline_items")}
    if not set(_TIMELINE_LINEAGE_COLUMNS) & columns:
        return 0

    touched = 0
    with engine.begin() as conn:
        if "take_prompt_revision" in columns and "takes" in tables:
            result = conn.execute(text(
                "UPDATE timeline_items SET take_prompt_revision = COALESCE(("
                "  SELECT t.prompt_revision FROM takes t WHERE t.id = timeline_items.take_id"
                "), 0) "
                "WHERE take_prompt_revision IS NULL"
            ))
            touched = max(touched, result.rowcount or 0)
        if "shot_prompt_revision" in columns and "shots" in tables:
            result = conn.execute(text(
                "UPDATE timeline_items SET shot_prompt_revision = COALESCE(("
                "  SELECT s.prompt_revision FROM shots s WHERE s.id = timeline_items.shot_id"
                "), 0) "
                "WHERE shot_prompt_revision IS NULL"
            ))
            touched = max(touched, result.rowcount or 0)
        for name in _TIMELINE_LINEAGE_COLUMNS:
            if name not in columns:
                continue
            result = conn.execute(text(
                f'UPDATE timeline_items SET "{name}" = 0 WHERE "{name}" IS NULL'
            ))
            touched = max(touched, result.rowcount or 0)

    if touched:
        logger.info("Backfilled lineage on %d legacy timeline item(s)", touched)
    return touched
