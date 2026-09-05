"""Shots that are made but not shown.

The route that composes well is: generate a key image for the beat, look at it,
approve it, and animate that. The key image is a real shot - it has a prompt, a
seed, a take, a review, and a place in the lineage of the clip that comes from
it - but it is not a piece of the film. It is the thing the piece was made
from.

Until now every shot with an approved take went into the cut, so using that
route put a three-second still between every clip. The two workarounds were
both worse than a flag: leave the key image unapproved, which breaks the
continuity binding that needs an approved source, or keep production
intermediates in a second project, which severs the lineage that makes any of
this traceable.

So a shot says whether it belongs in the cut. Default true, because the
ordinary shot is one you are going to see.
"""

import uuid

from app.models import Shot, Take
from app.services import revisions, timeline_service


def _shot(db, scene, order, **kwargs):
    shot = Shot(
        id=str(uuid.uuid4()), scene_id=scene.id, order=order,
        generation_mode=kwargs.pop("generation_mode", "video"),
        planned_duration_sec=kwargs.pop("planned_duration_sec", 4.0),
        video_prompt="something happens", **kwargs,
    )
    db.add(shot)
    db.commit()
    return shot


def _approved_take(db, project_id, shot, path="frame.png"):
    revisions.refresh_project(db, project_id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()), shot_id=shot.id, file_path=path,
        review_status="Approved", width=576, height=1024,
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
    )
    db.add(take)
    db.commit()
    return take


def test_a_shot_kept_out_of_the_cut_is_not_assembled(
    db_session, sample_project, sample_scene,
):
    """The whole point: a key image is production, not programme."""
    key_image = _shot(
        db_session, sample_scene, 1,
        generation_mode="image", include_in_cut=False,
    )
    clip = _shot(db_session, sample_scene, 2)
    _approved_take(db_session, sample_project.id, key_image, "key.png")
    _approved_take(db_session, sample_project.id, clip, "clip.mp4")

    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)
    manifest = timeline_service.get_timeline_manifest(db_session, sample_project.id)

    assert [item["shot_id"] for item in manifest["items"]] == [clip.id]


def test_shots_are_in_the_cut_unless_they_say_otherwise(
    db_session, sample_project, sample_scene,
):
    """Every project written before this flag existed must assemble exactly as
    it did, and the ordinary shot is one you are going to see."""
    first = _shot(db_session, sample_scene, 1)
    second = _shot(db_session, sample_scene, 2)
    _approved_take(db_session, sample_project.id, first, "a.mp4")
    _approved_take(db_session, sample_project.id, second, "b.mp4")

    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)
    manifest = timeline_service.get_timeline_manifest(db_session, sample_project.id)

    assert len(manifest["items"]) == 2


def test_the_running_time_does_not_count_what_is_not_shown(
    db_session, sample_project, sample_scene,
):
    """A cut whose clips start late is worse than one missing a shot: every
    subtitle and narration cue after it is out of step."""
    key_image = _shot(
        db_session, sample_scene, 1, generation_mode="image",
        include_in_cut=False, planned_duration_sec=3.0,
    )
    clip = _shot(db_session, sample_scene, 2, planned_duration_sec=4.0)
    _approved_take(db_session, sample_project.id, key_image, "key.png")
    _approved_take(db_session, sample_project.id, clip, "clip.mp4")

    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)
    manifest = timeline_service.get_timeline_manifest(db_session, sample_project.id)

    assert manifest["items"][0]["in_point_sec"] == 0.0
    assert manifest["total_duration_sec"] == 4.0


def test_coverage_does_not_report_a_hidden_shot_as_missing(
    db_session, sample_project, sample_scene,
):
    """Coverage answers "is the film complete?". A shot that was never meant
    to be in it is not a hole in it."""
    _shot(
        db_session, sample_scene, 1, generation_mode="image",
        include_in_cut=False,
    )
    clip = _shot(db_session, sample_scene, 2)
    _approved_take(db_session, sample_project.id, clip, "clip.mp4")

    built = timeline_service.build_timeline_from_approved_takes(
        db_session, sample_project.id
    )
    timeline_service.save_timeline_items(db_session, sample_project.id, built)
    manifest = timeline_service.get_timeline_manifest(db_session, sample_project.id)

    assert manifest["coverage"]["missing"] == []
    assert manifest["coverage"]["total_shots"] == 1


def test_the_flag_survives_the_api(client, db_session, sample_project, sample_scene):
    """It has to be settable by whatever is driving production, not only by
    reaching into the database."""
    created = client.post(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots",
        json={"order": 1, "generation_mode": "image", "include_in_cut": False},
    )
    assert created.status_code == 201, created.text
    assert created.json()["include_in_cut"] is False

    fetched = client.get(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots"
    ).json()
    assert fetched[0]["include_in_cut"] is False
