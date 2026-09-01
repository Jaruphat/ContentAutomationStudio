"""
Timeline Service.

Handles:
  - Building a timeline from approved takes ordered by shot/scene order.
  - Generating a Timeline Manifest JSON.
  - Generating an FFmpeg render plan (commands list).
  - Validating timeline completeness.
"""

import os
import shutil
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import paths
from app.models import Project, Scene, Shot, Take, TimelineItem


def build_timeline_from_approved_takes(
    db: Session, project_id: str
) -> list[dict[str, Any]]:
    """
    Auto-build timeline items from approved takes in shot order.

    For each shot that has an approved take, creates a timeline entry.
    Shots are ordered by scene.order, then shot.order.

    Returns a list of dicts representing new TimelineItem fields.
    """
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
            # Find an approved take for this shot (prefer the latest one)
            approved_take = (
                db.query(Take)
                .filter(Take.shot_id == shot.id, Take.review_status == "Approved")
                .order_by(Take.created_at.desc())
                .first()
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
            }
            items.append(item)
            running_time += duration
            order_counter += 1

    return items


def save_timeline_items(
    db: Session, project_id: str, items: list[dict[str, Any]]
) -> list[TimelineItem]:
    """
    Replace existing timeline items for a project with the given list.

    Returns the newly created ORM objects.
    """
    # Delete existing items
    db.query(TimelineItem).filter(TimelineItem.project_id == project_id).delete()
    db.flush()

    created: list[TimelineItem] = []
    for item_data in items:
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
        )
        db.add(ti)
        created.append(ti)

    db.commit()
    for c in created:
        db.refresh(c)
    return created


def get_timeline_manifest(db: Session, project_id: str) -> dict[str, Any]:
    """
    Build a Timeline Manifest JSON structure from stored timeline items.
    """
    items = (
        db.query(TimelineItem)
        .filter(TimelineItem.project_id == project_id)
        .order_by(TimelineItem.order)
        .all()
    )

    total_duration = sum(i.duration_sec for i in items)

    return {
        "project_id": project_id,
        "item_count": len(items),
        "total_duration_sec": total_duration,
        "items": [
            {
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

    manifest = get_timeline_manifest(db, project_id)
    items = manifest.get("items", [])
    commands: list[str] = []
    warnings: list[str] = []
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
        "note": (
            "This render plan is informational. Actual rendering requires "
            "FFmpeg installed, real media files (not placeholders), and "
            "approved takes for all timeline items."
        ),
    }
