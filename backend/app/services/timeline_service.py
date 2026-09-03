"""
Timeline Service.

Handles:
  - Building a timeline from approved takes ordered by shot/scene order.
  - Generating a Timeline Manifest JSON.
  - Generating an FFmpeg render plan (commands list).
  - Validating timeline completeness.
"""

import math
import os
import shutil
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import Project, Scene, Shot, Take, TimelineItem
from app.services import revisions
from app.services.generation_runs import (
    scene_display_name,
    shot_display_name,
    take_media_url,
)


E2E_ASPECT_OVERRIDE_WARNING = (
    "E2E Override · Aspect mismatch accepted · user-approved test override"
)

#: The only waiver reason this project trusts. A waiver is a human having
#: looked at a real aspect mismatch and accepted it for one E2E take - not a
#: string a caller can invent, so free text here is not a waiver at all.
TRUSTED_WAIVER_REASON = "User-approved E2E dimension exception"

#: Why a shot is not on the cut. Ordered from "one click away" to "nothing to
#: place yet", because the first true reason is the next thing to do.
COVERAGE_REASON_REBUILD = (
    "An approved take is ready. Rebuild the timeline to place this shot."
)
COVERAGE_REASON_PENDING = (
    "Takes are waiting in Review; approve one to place this shot."
)
COVERAGE_REASON_STALE = (
    "The approved take is out of date: the shot changed after it was "
    "generated. Regenerate it, then approve the new take."
)
COVERAGE_REASON_REJECTED = (
    "Every take for this shot was rejected. Regenerate it, then approve a take."
)
COVERAGE_REASON_UNGENERATED = (
    "No take has been generated for this shot yet."
)


#: A cut that predates lineage tracking is placed, but never silently: the
#: manifest has to say that its takes could not be proven current.
LEGACY_LINEAGE_WARNING = (
    "Some placed takes predate content-revision tracking, so this cut cannot "
    "be proven to match the current brief. Regenerate those shots to confirm."
)


class StaleTimelineError(Exception):
    """A timeline item no longer matches the current approved shot lineage."""


class EmptyTimelineReplacementError(Exception):
    """An auto-build would have replaced a real cut with nothing.

    Raised instead of deleting, because a build that can place no take is
    almost always a lineage or migration problem - and the existing timeline is
    the only copy of the user's edit order.
    """


def _resolution_aspect(resolution: str) -> tuple[int, int] | None:
    """Reduce a 'WIDTHxHEIGHT' string to its lowest-terms ratio, or None."""
    try:
        width, height = (int(part) for part in str(resolution).lower().split("x", 1))
    except (ValueError, AttributeError):
        return None
    if width <= 0 or height <= 0:
        return None
    divisor = math.gcd(width, height)
    return width // divisor, height // divisor


def _dimensions_mismatch_target(take: Take, project: Project) -> bool:
    """Whether the take's own pixels are actually off the project's aspect.

    A waiver excuses a real mismatch; a take with no recorded dimensions, or
    one that happens to already match, has nothing to excuse.
    """
    if not take.width or not take.height:
        return False
    take_aspect = _resolution_aspect(f"{take.width}x{take.height}")
    target_aspect = _resolution_aspect(project.target_resolution)
    if take_aspect is None or target_aspect is None:
        return False
    return take_aspect != target_aspect


def is_waived(db: Session, project: Project, take: Take | None) -> bool:
    """Whether this one take was accepted under an explicit aspect waiver.

    Every part must hold, not just a lineage blob shaped like a waiver:
    the reason must be this project's exact trusted wording, the take it
    claims to have replaced must really exist and belong to the same shot,
    and the take actually placed must really carry a mismatched aspect - a
    waiver cannot excuse a mismatch that never existed.
    """
    if take is None or project is None:
        return False
    lineage = take.lineage if isinstance(take.lineage, dict) else {}
    reason = lineage.get("waiver_reason")
    source_id = lineage.get("waived_from_take_id")
    if reason != TRUSTED_WAIVER_REASON or not source_id or source_id == take.id:
        return False
    original = db.query(Take).filter(Take.id == source_id).first()
    if original is None or original.shot_id != take.shot_id:
        return False
    shot_in_project = (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Shot.id == take.shot_id, Scene.project_id == project.id)
        .first()
    )
    if shot_in_project is None:
        return False
    if (
        original.created_at is None
        or take.created_at is None
        or original.created_at >= take.created_at
    ):
        return False
    return _dimensions_mismatch_target(take, project)


def aspect_override_warnings(
    db: Session, project: Project | None, takes: list[Take]
) -> list[dict[str, Any]]:
    """Describe explicit E2E aspect waivers on supplied timeline takes only."""
    if project is None:
        return []
    waived = [take for take in takes if is_waived(db, project, take)]
    if not waived:
        return []
    return [{
        "code": "e2e_aspect_override",
        "message": E2E_ASPECT_OVERRIDE_WARNING,
        "take_ids": [take.id for take in waived],
        "waived_from_take_ids": [
            take.lineage["waived_from_take_id"] for take in waived
        ],
        "waiver_reasons": [take.lineage["waiver_reason"] for take in waived],
    }]


def _take_matches_shot(take: Take, shot: Shot) -> bool:
    """Require equality across every persisted generation dependency."""
    return bool(
        take.review_status == "Approved"
        and revisions.take_lineage_state(take, shot) == revisions.LINEAGE_CURRENT
    )


def _take_is_legacy(take: Take, shot: Shot) -> bool:
    """An approved take whose lineage was never recorded, so cannot be judged."""
    return bool(
        take.review_status == "Approved"
        and revisions.take_lineage_state(take, shot) == revisions.LINEAGE_UNVERIFIED
    )


def _take_is_placeable(take: Take, shot: Shot) -> bool:
    """Whether this approved take may sit on the cut.

    Current takes always may. A take from before lineage tracking may too:
    refusing it would quietly delete approved work that a database upgrade,
    not the user, invalidated. What it may not do is pass as verified - see
    :data:`LEGACY_LINEAGE_WARNING`.
    """
    return _take_matches_shot(take, shot) or _take_is_legacy(take, shot)


def build_timeline_from_approved_takes(
    db: Session, project_id: str
) -> list[dict[str, Any]]:
    """
    Auto-build timeline items from approved takes in shot order.

    For each shot that has an approved take, creates a timeline entry.
    Shots are ordered by scene.order, then shot.order.

    Returns a list of dicts representing new TimelineItem fields.
    """
    revisions.refresh_project(db, project_id)
    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )

    items: list[dict[str, Any]] = []
    running_time = 0.0
    order_counter = 0

    for scene in scenes:
        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        for shot in shots:
            approved_takes = (
                db.query(Take)
                .filter(Take.shot_id == shot.id, Take.review_status == "Approved")
                .order_by(Take.created_at.desc())
                .all()
            )
            # A verified current take always wins; a legacy one is only used
            # when there is nothing better, so an upgrade never demotes a cut.
            approved_take = next(
                (take for take in approved_takes if _take_matches_shot(take, shot)),
                None,
            ) or next(
                (take for take in approved_takes if _take_is_legacy(take, shot)),
                None,
            )
            if approved_take is None:
                continue

            duration = shot.planned_duration_sec if shot.planned_duration_sec > 0 else 3.0
            if approved_take.duration_sec > 0:
                duration = approved_take.duration_sec

            item = {
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "shot_id": shot.id,
                "take_id": approved_take.id,
                "order": order_counter,
                "in_point_sec": running_time,
                "out_point_sec": running_time + duration,
                "duration_sec": duration,
                "transition_in": "cut",
                "transition_out": "cut",
                "take_prompt_revision": approved_take.prompt_revision,
                "shot_prompt_revision": shot.prompt_revision,
            }
            items.append(item)
            running_time += duration
            order_counter += 1

    return items


def save_timeline_items(
    db: Session,
    project_id: str,
    items: list[dict[str, Any]],
    *,
    allow_empty_replacement: bool = True,
) -> list[TimelineItem]:
    """Atomically replace a timeline after validating every take lineage.

    ``allow_empty_replacement`` guards the one case that cannot be undone: a
    derived build that resolved to nothing is refused rather than allowed to
    wipe an existing cut. An explicit edit that clears the timeline is a
    different act and passes the default.
    """
    revisions.refresh_project(db, project_id)
    prepared: list[tuple[dict[str, Any], Take | None, Shot | None]] = []

    if not items and not allow_empty_replacement:
        existing = (
            db.query(TimelineItem)
            .filter(TimelineItem.project_id == project_id)
            .count()
        )
        if existing:
            raise EmptyTimelineReplacementError(
                f"This build placed no takes, but the project already has "
                f"{existing} timeline item(s). Refusing to replace the current "
                f"cut with an empty one. Check the Timeline coverage report "
                f"for why each shot could not be placed, or clear the timeline "
                f"explicitly if that is what you meant."
            )

    # Validate the complete replacement before deleting the current cut. A
    # refused stale edit must not destroy a valid timeline as a side effect.
    for item_data in items:
        take_id = item_data.get("take_id")
        shot_id = item_data.get("shot_id")
        # A placed clip always names both; an item naming only one - or
        # neither - is not a partial placement, it is not a placement, and
        # must be refused before anything is deleted.
        if not take_id or not shot_id:
            raise StaleTimelineError(
                f"Timeline item requires both take_id and shot_id; got "
                f"take_id={take_id!r}, shot_id={shot_id!r}."
            )
        take = db.query(Take).filter(Take.id == take_id).first()
        shot = db.query(Shot).filter(Shot.id == shot_id).first()
        valid = bool(
            take is not None
            and shot is not None
            and take.shot_id == shot.id
            and shot.scene is not None
            and shot.scene.project_id == project_id
            and _take_is_placeable(take, shot)
        )
        if not valid:
            raise StaleTimelineError(
                f"Timeline take {take_id!r} and shot {shot_id!r} do not "
                "form a current approved lineage."
            )
        prepared.append((item_data, take, shot))

    db.query(TimelineItem).filter(TimelineItem.project_id == project_id).delete()
    db.flush()

    created: list[TimelineItem] = []
    for item_data, take, shot in prepared:
        ti = TimelineItem(
            id=item_data.get("id", str(uuid.uuid4())),
            project_id=project_id,
            shot_id=item_data.get("shot_id"),
            take_id=item_data.get("take_id"),
            order=item_data.get("order", 0),
            in_point_sec=item_data.get("in_point_sec", 0.0),
            out_point_sec=item_data.get("out_point_sec", 0.0),
            duration_sec=item_data.get("duration_sec", 0.0),
            transition_in=item_data.get("transition_in", "cut"),
            transition_out=item_data.get("transition_out", "cut"),
            take_prompt_revision=(
                take.prompt_revision
                if take is not None
                else item_data.get("take_prompt_revision", 0)
            ),
            shot_prompt_revision=(
                shot.prompt_revision
                if shot is not None
                else item_data.get("shot_prompt_revision", 0)
            ),
        )
        db.add(ti)
        created.append(ti)

    db.commit()
    for timeline_item in created:
        db.refresh(timeline_item)
    return created


def timeline_coverage(db: Session, project_id: str) -> dict[str, Any]:
    """Which shots are on the cut, and the reason each of the rest is not.

    A build that quietly skips a third of the project looks identical to one
    that had nothing to skip. This is what turns that silence into a list the
    user can act on, so every entry names a next step rather than a state.
    """
    covered_shot_ids = {
        row[0]
        for row in db.query(TimelineItem.shot_id)
        .filter(TimelineItem.project_id == project_id)
        .all()
        if row[0]
    }

    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.order)
        .all()
    )

    total_shots = 0
    covered = 0
    missing: list[dict[str, Any]] = []

    for scene in scenes:
        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == scene.id)
            .order_by(Shot.order)
            .all()
        )
        for shot in shots:
            total_shots += 1
            if shot.id in covered_shot_ids:
                covered += 1
                continue

            takes = db.query(Take).filter(Take.shot_id == shot.id).all()
            approved = [t for t in takes if t.review_status == "Approved"]
            if any(_take_is_placeable(take, shot) for take in approved):
                reason = COVERAGE_REASON_REBUILD
            elif any(t.review_status == "Pending" for t in takes):
                reason = COVERAGE_REASON_PENDING
            elif approved:
                reason = COVERAGE_REASON_STALE
            elif takes:
                reason = COVERAGE_REASON_REJECTED
            else:
                reason = COVERAGE_REASON_UNGENERATED

            missing.append({
                "shot_id": shot.id,
                "scene_id": scene.id,
                "scene_title": scene_display_name(scene),
                "shot_name": shot_display_name(shot),
                "shot_order": shot.order,
                "reason": reason,
            })

    return {
        "total_shots": total_shots,
        "covered_shots": covered,
        "missing": missing,
    }


def get_timeline_manifest(
    db: Session, project_id: str, *, strict_lineage: bool = False
) -> dict[str, Any]:
    """
    Build a Timeline Manifest JSON structure from stored timeline items.
    """
    revisions.refresh_project(db, project_id)
    project = db.query(Project).filter(Project.id == project_id).first()
    items = (
        db.query(TimelineItem)
        .filter(TimelineItem.project_id == project_id)
        .order_by(TimelineItem.order)
        .all()
    )

    total_duration = sum(i.duration_sec for i in items)

    # One lookup for every referenced take, so each clip can carry the
    # provider, model and cost that produced it. A manifest that only named a
    # file path would leave a delivered cut with no record of what generated
    # it - which is exactly the question asked after delivery.
    take_ids = [item.take_id for item in items if item.take_id]
    takes = (
        {t.id: t for t in db.query(Take).filter(Take.id.in_(take_ids)).all()}
        if take_ids
        else {}
    )
    shot_ids = [item.shot_id for item in items if item.shot_id]
    shots = (
        {s.id: s for s in db.query(Shot).filter(Shot.id.in_(shot_ids)).all()}
        if shot_ids
        else {}
    )
    scene_ids = {shot.scene_id for shot in shots.values() if shot.scene_id}
    scenes = (
        {s.id: s for s in db.query(Scene).filter(Scene.id.in_(scene_ids)).all()}
        if scene_ids
        else {}
    )
    stale_items: list[str] = []
    legacy_items: list[str] = []
    for item in items:
        take = takes.get(item.take_id) if item.take_id else None
        shot = shots.get(item.shot_id) if item.shot_id else None
        if take is None or shot is None or take.shot_id != shot.id:
            stale_items.append(item.id)
            continue
        if _take_is_legacy(take, shot):
            # Nothing to compare a pre-lineage take against, so the recorded
            # revisions on the row are not evidence either way.
            legacy_items.append(item.id)
            continue
        if (
            not _take_matches_shot(take, shot)
            or item.take_prompt_revision != take.prompt_revision
            or item.shot_prompt_revision != shot.prompt_revision
        ):
            stale_items.append(item.id)
    if strict_lineage and stale_items:
        raise StaleTimelineError(
            "Timeline contains stale or mismatched take lineage in item(s): "
            + ", ".join(stale_items)
        )

    def _source(item: TimelineItem) -> dict[str, Any]:
        take = takes.get(item.take_id) if item.take_id else None
        if take is None:
            return {}
        return {
            "file_path": take.file_path,
            "media_provider_id": take.media_provider_id or "comfyui",
            "media_model": take.media_model or "workflow",
            "estimated_cost_usd": take.estimated_cost_usd,
            "review_status": take.review_status,
            "provenance": take.provenance or {},
            "prompt_revision": take.prompt_revision,
            "prompt_sha256": take.prompt_sha256,
            "content_sha256": take.content_sha256,
            "reference_image_ids": list(take.reference_image_ids or []),
            "reference_sha256s": list(take.reference_sha256s or []),
            "lineage": take.lineage or {},
        }

    def _display(item: TimelineItem) -> dict[str, Any]:
        """What a person needs to recognise this row: names, not identifiers."""
        shot = shots.get(item.shot_id) if item.shot_id else None
        scene = scenes.get(shot.scene_id) if shot is not None else None
        take = takes.get(item.take_id) if item.take_id else None
        return {
            "scene_id": shot.scene_id if shot is not None else None,
            # An item with no shot reference at all is a gap in the cut, not a
            # deleted shot, so it is left unnamed rather than mislabelled.
            "scene_title": scene_display_name(scene) if item.shot_id else "",
            "shot_name": shot_display_name(shot) if item.shot_id else "",
            "thumbnail_url": take_media_url(take),
            "waived": is_waived(db, project, take),
        }

    timeline_takes = [takes[item.take_id] for item in items if item.take_id in takes]
    warnings = aspect_override_warnings(db, project, timeline_takes)
    if legacy_items:
        warnings.append({
            "code": "legacy_take_lineage",
            "message": LEGACY_LINEAGE_WARNING,
            "item_ids": legacy_items,
            "take_ids": [
                item.take_id for item in items if item.id in set(legacy_items)
            ],
        })

    return {
        "project_id": project_id,
        "item_count": len(items),
        "total_duration_sec": total_duration,
        "warnings": warnings,
        "delivery_validation": {
            "pipeline_pass": not stale_items,
            "delivery_spec_pass": not stale_items and not warnings,
        },
        "coverage": timeline_coverage(db, project_id),
        "items": [
            {
                "display": _display(item),
                "id": item.id,
                "project_id": item.project_id,
                "shot_id": item.shot_id,
                "take_id": item.take_id,
                "order": item.order,
                "in_point_sec": item.in_point_sec,
                "out_point_sec": item.out_point_sec,
                "duration_sec": item.duration_sec,
                "transition_in": item.transition_in,
                "transition_out": item.transition_out,
                "take_prompt_revision": item.take_prompt_revision,
                "shot_prompt_revision": item.shot_prompt_revision,
                "source": _source(item),
            }
            for item in items
        ],
    }


def validate_timeline_completeness(
    db: Session, project_id: str
) -> dict[str, Any]:
    """
    Check that every shot in the project has a corresponding timeline entry
    with an approved take.

    Returns a report dict with missing shots and warnings.
    """
    scenes = db.query(Scene).filter(Scene.project_id == project_id).all()
    all_shot_ids: set[str] = set()
    for scene in scenes:
        shots = db.query(Shot).filter(Shot.scene_id == scene.id).all()
        for shot in shots:
            all_shot_ids.add(shot.id)

    timeline_items = (
        db.query(TimelineItem)
        .filter(TimelineItem.project_id == project_id)
        .all()
    )
    covered_shot_ids = {ti.shot_id for ti in timeline_items if ti.shot_id}

    missing = all_shot_ids - covered_shot_ids
    warnings: list[str] = []

    # Check that each timeline entry has a valid take
    for ti in timeline_items:
        if ti.take_id:
            take = db.query(Take).filter(Take.id == ti.take_id).first()
            if take is None:
                warnings.append(f"Timeline item {ti.id} references missing take {ti.take_id}")
            elif take.review_status != "Approved":
                warnings.append(
                    f"Timeline item {ti.id} uses take {ti.take_id} "
                    f"with status '{take.review_status}' (not Approved)"
                )

    return {
        "complete": len(missing) == 0 and len(warnings) == 0,
        "total_shots": len(all_shot_ids),
        "covered_shots": len(covered_shot_ids),
        "missing_shot_ids": sorted(missing),
        "warnings": warnings,
    }


def generate_render_plan(
    db: Session, project_id: str
) -> dict[str, Any]:
    """
    Generate an FFmpeg render plan from the timeline manifest.

    This produces the list of FFmpeg commands that would be needed to
    assemble the final video. Actual execution requires:
      - FFmpeg installed and on PATH
      - Real media files at the referenced paths

    The plan is returned as data; it does NOT execute anything.
    """
    ffmpeg_available = shutil.which("ffmpeg") is not None

    manifest = get_timeline_manifest(db, project_id, strict_lineage=True)
    items = manifest.get("items", [])
    commands: list[str] = []
    warnings: list[str] = []
    warning_metadata = manifest["warnings"]
    warnings.extend(warning["message"] for warning in warning_metadata)
    timeline_data: list[dict[str, Any]] = []

    if not ffmpeg_available:
        warnings.append(
            "FFmpeg is not installed or not on PATH. "
            "Render plan is generated but cannot be executed."
        )

    # Build per-item render instructions
    concat_inputs: list[str] = []

    for item in items:
        take_id = item.get("take_id")
        if not take_id:
            warnings.append(f"Timeline order {item['order']}: no take assigned")
            continue

        take = db.query(Take).filter(Take.id == take_id).first()
        if take is None:
            warnings.append(f"Timeline order {item['order']}: take {take_id} not found in DB")
            continue

        if not take.file_path or not os.path.isfile(take.file_path):
            warnings.append(
                f"Timeline order {item['order']}: media file missing or placeholder "
                f"({take.file_path}). Real media required for FFmpeg render."
            )

        duration = item.get("duration_sec", 3.0)
        file_path = take.file_path.replace("\\", "/")

        timeline_data.append({
            "order": item["order"],
            "shot_id": item.get("shot_id"),
            "take_id": take_id,
            "file_path": file_path,
            "duration_sec": duration,
            "transition_in": item.get("transition_in", "cut"),
            "transition_out": item.get("transition_out", "cut"),
        })
        concat_inputs.append(file_path)

    # Generate FFmpeg concat command
    if concat_inputs:
        # Build a concat demuxer file content
        concat_list_lines = [f"file '{p}'" for p in concat_inputs]
        concat_list_content = "\n".join(concat_list_lines)

        output_dir = paths.exports_dir(project_id)
        concat_file = os.path.join(output_dir, "concat_list.txt").replace("\\", "/")
        output_file = os.path.join(output_dir, "output.mp4").replace("\\", "/")

        commands.append(f"# Write concat list to: {concat_file}")
        commands.append(f"# Content:\n# {concat_list_content.replace(chr(10), chr(10) + '# ')}")
        commands.append(
            f'ffmpeg -y -f concat -safe 0 -i "{concat_file}" '
            f'-c:v libx264 -preset medium -crf 23 '
            f'-c:a aac -b:a 128k '
            f'"{output_file}"'
        )

    project = db.query(Project).filter(Project.id == project_id).first()
    project_title = project.title if project else project_id

    return {
        "project_id": project_id,
        "project_title": project_title,
        "timeline_items": timeline_data,
        "ffmpeg_available": ffmpeg_available,
        "commands": commands,
        "warnings": warnings,
        "warning_metadata": warning_metadata,
        "delivery_validation": manifest["delivery_validation"],
        "note": (
            "This render plan is informational. Actual rendering requires "
            "FFmpeg installed, real media files (not placeholders), and "
            "approved takes for all timeline items."
        ),
    }
