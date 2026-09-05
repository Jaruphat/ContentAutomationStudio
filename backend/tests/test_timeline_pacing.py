"""How long a shot is held, as opposed to how long its clip happens to be.

The video model returns whatever length its graph is baked at. Until now the
timeline used that length whenever it was known, and only fell back to the
shot's planned duration when the take had none - so every film was N clips of
one length, and a shot plan that says 4, 2, 4, 3, 4, 3, 4, 3, 5 seconds could
not be produced at all. A thirty-two second short came out at forty-seven.

The planned duration is an edit decision and the clip length is a property of
the generator, so the edit wins where it can:

* Planned shorter than the clip - hold it for the planned time. This is the
  ordinary case and the only way pacing exists.
* Planned longer than the clip - use the clip and say so. Stretching would
  mean freezing or looping the tail, and inventing footage to fill a gap is
  worse than reporting the gap.
* No planned duration - the clip, as before.
"""

import uuid

from app.models import Shot, Take
from app.services import revisions, timeline_service


def _shot(db, scene, order, planned):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode="image-to-video", video_prompt="a train arrives",
        planned_duration_sec=planned,
    )
    db.add(shot)
    db.commit()
    return shot


def _take(db, project_id, shot, clip_seconds):
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path="clip.mp4",
        review_status="Approved", width=576, height=1024,
        duration_sec=clip_seconds,
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
    )
    db.add(take)
    db.commit()
    return take


def _build(db, project_id):
    items = timeline_service.build_timeline_from_approved_takes(db, project_id)
    timeline_service.save_timeline_items(db, project_id, items)
    return timeline_service.get_timeline_manifest(db, project_id)


def test_a_shot_is_held_for_the_time_the_edit_asked_for(
    db_session, sample_project, sample_scene,
):
    """Without this there is no pacing: every shot lasts as long as whatever
    the model happened to produce."""
    shot = _shot(db_session, sample_scene, 1, planned=2.0)
    _take(db_session, sample_project.id, shot, clip_seconds=5.2)

    manifest = _build(db_session, sample_project.id)

    assert manifest["items"][0]["duration_sec"] == 2.0
    assert manifest["total_duration_sec"] == 2.0


def test_shots_of_different_lengths_run_back_to_back_without_gaps(
    db_session, sample_project, sample_scene,
):
    """The failure this guards is silent: an in-point computed from clip
    length while the cut uses planned length leaves every later subtitle and
    narration cue out of step."""
    first = _shot(db_session, sample_scene, 1, planned=4.0)
    second = _shot(db_session, sample_scene, 2, planned=2.0)
    third = _shot(db_session, sample_scene, 3, planned=4.0)
    for shot in (first, second, third):
        _take(db_session, sample_project.id, shot, clip_seconds=5.2)

    manifest = _build(db_session, sample_project.id)

    spans = [(i["in_point_sec"], i["out_point_sec"]) for i in manifest["items"]]
    assert spans == [(0.0, 4.0), (4.0, 6.0), (6.0, 10.0)]
    assert manifest["total_duration_sec"] == 10.0


def test_a_clip_shorter_than_the_plan_is_used_as_it_is(
    db_session, sample_project, sample_scene,
):
    """Filling the gap would mean freezing or looping the tail. Inventing
    footage to meet a number is worse than missing the number."""
    shot = _shot(db_session, sample_scene, 1, planned=8.0)
    _take(db_session, sample_project.id, shot, clip_seconds=5.2)

    manifest = _build(db_session, sample_project.id)

    assert manifest["items"][0]["duration_sec"] == 5.2


def test_a_clip_shorter_than_the_plan_says_so(
    db_session, sample_project, sample_scene,
):
    """A film that runs short needs to name the shot that came up short, or
    the next edit is a guess."""
    shot = _shot(db_session, sample_scene, 1, planned=8.0)
    _take(db_session, sample_project.id, shot, clip_seconds=5.2)

    manifest = _build(db_session, sample_project.id)

    assert any(
        "shorter" in warning["message"].lower()
        for warning in manifest["warnings"]
    ), manifest["warnings"]


def test_a_shot_with_no_plan_still_uses_its_clip(
    db_session, sample_project, sample_scene,
):
    """Every project written before pacing existed must assemble as it did."""
    shot = _shot(db_session, sample_scene, 1, planned=0.0)
    _take(db_session, sample_project.id, shot, clip_seconds=5.2)

    manifest = _build(db_session, sample_project.id)

    assert manifest["items"][0]["duration_sec"] == 5.2
