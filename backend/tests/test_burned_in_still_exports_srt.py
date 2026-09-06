"""Burning captions into the picture does not give a platform a caption file.

The publish package lists a subtitle file, and an upload form asks for one:
YouTube indexes a caption track, offers it as a setting, and translates it.
Pixels do none of that, and a viewer who needs captions larger, or in another
language, cannot get either from a burned-in line.

The renderer wrote the SRT only in "soft" mode - the mode where the captions
are *not* in the picture. In burn-in, which is what a vertical short uses, no
SRT was written at all, so the package reported no subtitle file for every
episode this application has ever delivered.

Both are written now. The ASS is what gets burned in; the SRT is what gets
uploaded beside the video.
"""

import os

from app import paths


def _one_shot_film(db_session, tmp_path, sample_project, sample_shot,
                   synthesise_clip, client):
    """One approved clip with a line of dialogue, on the timeline."""
    from app.models import Take, TimelineItem
    import uuid

    clip = synthesise_clip(
        str(tmp_path / "clip.mp4"), with_audio=True, duration=1.0
    )
    sample_shot.dialogue = "There are seven rooms in this house."
    db_session.add(Take(
        id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=clip,
        review_status="Approved", duration_sec=1.0, width=320, height=180,
        prompt_revision=sample_shot.prompt_revision,
        content_sha256=sample_shot.content_sha256,
    ))
    db_session.add(TimelineItem(project_id=sample_project.id, shot_id=sample_shot.id))
    db_session.commit()
    client.post(f"/api/projects/{sample_project.id}/timeline/build")


def _render(client, project_id: str, mode: str):
    client.put(f"/api/projects/{project_id}/subtitles", json={"mode": mode})
    return client.post(f"/api/projects/{project_id}/render", json={})


def test_burned_in_captions_still_leave_an_srt_to_upload(
    client, db_session, tmp_path, sample_project, sample_shot, synthesise_clip,
):
    _one_shot_film(db_session, tmp_path, sample_project, sample_shot,
                   synthesise_clip, client)

    result = _render(client, sample_project.id, "burn_in")

    assert result.status_code == 200, result.text
    body = result.json()
    assert body["rendered"], body.get("reason")
    directory = paths.exports_dir(sample_project.id)
    assert os.path.isfile(os.path.join(directory, "subtitles.ass"))
    assert os.path.isfile(os.path.join(directory, "subtitles.srt"))


def test_captions_turned_off_leave_no_sidecar(
    client, db_session, tmp_path, sample_project, sample_shot, synthesise_clip,
):
    """Off means off. A file nobody asked for is a file somebody uploads."""
    _one_shot_film(db_session, tmp_path, sample_project, sample_shot,
                   synthesise_clip, client)

    result = _render(client, sample_project.id, "off")

    assert result.status_code == 200, result.text
    directory = paths.exports_dir(sample_project.id)
    assert not os.path.isfile(os.path.join(directory, "subtitles.srt"))
    assert not os.path.isfile(os.path.join(directory, "subtitles.ass"))
