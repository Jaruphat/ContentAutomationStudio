import os
import uuid

import pytest
from pydantic import ValidationError

from app.models import TimelineItem
from app.services import revisions, subtitle_service
from app.services.subtitle_service import (
    DEFAULT_SUBTITLE_SETTINGS,
    SubtitleSidecarError,
    SubtitleSettings,
    _graphemes,
    build_subtitle_cues,
    render_ass,
    render_srt,
    write_ass_sidecar,
)


def _stub_render_environment(monkeypatch, tmp_path):
    from app.services import render_service

    commands = []

    def fake_run(command, timeout=300):
        commands.append(command)
        output = command[-1]
        if isinstance(output, str) and output.endswith(".mp4"):
            os.makedirs(os.path.dirname(output), exist_ok=True)
            with open(output, "wb") as handle:
                handle.write(b"mp4")
        return True, ""

    monkeypatch.setattr(render_service, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(render_service, "_run", fake_run)
    monkeypatch.setattr(render_service, "_source_has_audio", lambda _path: False)
    monkeypatch.setattr(render_service, "probe_media", lambda _path: {})
    monkeypatch.setattr(render_service, "probe_media_file", lambda _path: {})
    monkeypatch.setattr(render_service, "embedded_metadata_keys", lambda _path: [])
    monkeypatch.setattr(
        render_service,
        "read_container_tags",
        lambda _path: {"format": {"major_brand": "isom"}, "streams": []},
    )
    monkeypatch.setattr(render_service.paths, "exports_dir", lambda _id: str(tmp_path))
    monkeypatch.setattr(
        "app.services.subtitle_service.paths.exports_dir", lambda _id: str(tmp_path)
    )
    return commands


def _put_current_take_on_timeline(db, project, shot, *, start=1.25, end=4.75):
    from app.models import Take

    revisions.refresh_project(db, project.id)
    db.refresh(shot)
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=shot.id,
        file_path="unused.mp4",
        review_status="Approved",
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
    )
    db.add(take)
    db.add(TimelineItem(
        id=str(uuid.uuid4()), project_id=project.id, shot_id=shot.id,
        take_id=take.id, order=0, in_point_sec=start, out_point_sec=end,
        duration_sec=end - start, take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()


def test_defaults_are_off_and_sanitized():
    settings = SubtitleSettings.model_validate({})
    assert settings.model_dump() == DEFAULT_SUBTITLE_SETTINGS
    assert settings.mode == "off"
    assert settings.font_family in {"Segoe UI", "Leelawadee UI"}


@pytest.mark.parametrize("field,value", [
    ("font_family", "C:/Windows/Fonts/evil.ttf"),
    ("font_family", "Comic Sans MS"),
    ("text_color", "white"),
    ("outline_color", "#fff"),
    ("position", "bottom,enable='hack'"),
    ("preset", "../../custom"),
    ("font_size", 0),
    ("outline_width", 99),
    ("max_chars_per_line", 3),
])
def test_settings_reject_unsafe_or_out_of_range_values(field, value):
    with pytest.raises(ValidationError):
        SubtitleSettings.model_validate({field: value})


def test_cues_use_strict_manifest_timing_and_shot_dialogue(db_session, sample_project, sample_shot):
    sample_shot.dialogue = "  Hello {world}\\N\nsecond line  "
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot)

    cues = build_subtitle_cues(db_session, sample_project.id, max_chars_per_line=20)

    assert cues == [{
        "index": 1,
        "start_sec": 0.0,
        "end_sec": 3.5,
        "text": "Hello {world}\\N\nsecond line",
    }]


def test_cues_follow_sequential_cut_timing_not_each_sources_trim_points(
    db_session, sample_project, sample_shot, monkeypatch
):
    sample_shot.dialogue = "Story beat"
    db_session.commit()
    monkeypatch.setattr(
        "app.services.subtitle_service.get_timeline_manifest",
        lambda *_args, **_kwargs: {
            "items": [
                {
                    "shot_id": sample_shot.id,
                    "order": 0,
                    "in_point_sec": 0.0,
                    "out_point_sec": 5.0,
                    "duration_sec": 5.0,
                },
                {
                    "shot_id": sample_shot.id,
                    "order": 1,
                    "in_point_sec": 0.0,
                    "out_point_sec": 5.0,
                    "duration_sec": 5.0,
                },
            ]
        },
    )

    cues = build_subtitle_cues(db_session, sample_project.id)

    assert [(cue["start_sec"], cue["end_sec"]) for cue in cues] == [
        (0.0, 5.0),
        (5.0, 10.0),
    ]


def test_blank_dialogue_is_omitted(db_session, sample_project, sample_shot):
    sample_shot.dialogue = " \n\t "
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot)
    assert build_subtitle_cues(db_session, sample_project.id) == []


def test_long_dialogue_splits_into_timed_cues_without_losing_thai_graphemes(
    db_session, sample_project, sample_shot
):
    dialogue = (
        "ภาษาไทยกำลังทดสอบการตัดบรรทัด "
        "และ this deliberately long sentence must survive in full"
    )
    sample_shot.dialogue = dialogue
    db_session.commit()
    _put_current_take_on_timeline(
        db_session, sample_project, sample_shot, start=10.0, end=18.0
    )

    cues = build_subtitle_cues(
        db_session, sample_project.id, max_chars_per_line=12
    )

    assert len(cues) > 1
    assert "".join(cue["text"] for cue in cues) == dialogue
    assert cues[0]["start_sec"] == 0.0
    assert cues[-1]["end_sec"] == 8.0
    assert all(
        0.0 <= cue["start_sec"] < cue["end_sec"] <= 8.0 for cue in cues
    )
    assert all(
        len(render_srt([cue], 12).splitlines()[2:]) <= 2 for cue in cues
    )
    # Thai combining marks must stay attached to their base character.
    assert all(not cue["text"].startswith(("ำ", "่", "้", "๊", "๋")) for cue in cues)


def test_ass_is_deterministic_utf8_safe_escaped_and_wrapped():
    settings = SubtitleSettings(
        mode="burn_in", font_family="Leelawadee UI", text_color="#AABBCC",
        outline_color="#010203", shadow_color="#040506",
        background_color="#070809", background_box=True, position="top",
        max_chars_per_line=12,
    )
    cues = [{"index": 1, "start_sec": 0.0, "end_sec": 2.345,
             "text": "Thai ไทย \\ {x}"}]
    first = render_ass(cues, settings, 1920, 1080)
    second = render_ass(cues, settings, 1920, 1080)
    assert first == second
    assert "Leelawadee UI" in first
    assert "0:00:00.00,0:00:02.35" in first
    assert r"\{x\}" in first
    assert r"\\" in first
    assert first.split("Dialogue:", 1)[1].count(r"\N") <= 1
    assert "&H00CCBBAA" in first
    assert "Alignment=8" not in first
    first.encode("utf-8")


def test_srt_preserves_millisecond_timing_and_plain_text():
    output = render_srt([{
        "index": 1, "start_sec": 1.25, "end_sec": 4.75,
        "text": "Hello\nworld",
    }], max_chars_per_line=40)
    assert output == "1\n00:00:01,250 --> 00:00:04,750\nHello\nworld\n"


def test_whitespace_wrapping_never_exceeds_the_configured_grapheme_width():
    output = render_srt([{
        "index": 1,
        "start_sec": 0.0,
        "end_sec": 2.0,
        "text": "aaaa " + ("b" * 19),
    }], max_chars_per_line=12)

    text_lines = output.splitlines()[2:]
    assert text_lines
    assert all(len(_graphemes(line)) <= 12 for line in text_lines)


@pytest.mark.parametrize(
    "start,end", [(float("nan"), 1.0), (0.0, float("inf")), (-0.1, 1.0), (1.0, 1.0), (2.0, 1.0)]
)
@pytest.mark.parametrize("renderer", ["srt", "ass"])
def test_renderers_reject_invalid_cue_intervals(start, end, renderer):
    cue = {"index": 1, "start_sec": start, "end_sec": end, "text": "unsafe"}
    with pytest.raises(ValueError, match="finite.*non-negative.*end"):
        if renderer == "srt":
            render_srt([cue])
        else:
            render_ass([cue], SubtitleSettings(), 1920, 1080)


@pytest.mark.parametrize("renderer", ["srt", "ass"])
def test_overflow_rejects_cues_that_collapse_at_output_time_precision(renderer):
    cue = {
        "index": 1,
        "start_sec": 0.0,
        "end_sec": 0.001,
        "text": "This dialogue is much too long for such a tiny interval",
    }
    with pytest.raises(ValueError, match="time precision"):
        if renderer == "srt":
            render_srt([cue], max_chars_per_line=12)
        else:
            render_ass([cue], SubtitleSettings(max_chars_per_line=12), 1920, 1080)


def test_thai_and_indic_graphemes_are_never_split_from_their_base():
    assert _graphemes("กิ") == ["กิ"]
    assert _graphemes("कि") == ["कि"]
    output = render_srt([{
        "index": 1,
        "start_sec": 0.0,
        "end_sec": 2.0,
        "text": "กิ" * 14 + " कि" * 8,
    }], max_chars_per_line=12)

    assert "ก\nิ" not in output
    assert "क\nि" not in output


def test_srt_neutralizes_markup_controls_and_bidi_overrides():
    output = render_srt([{
        "index": 1,
        "start_sec": 0.0,
        "end_sec": 1.0,
        "text": "<font color='red'>safe</font>\x00\x1b\u202eevil",
    }], max_chars_per_line=80)

    assert "<font" not in output
    assert "</font>" not in output
    assert "\x00" not in output
    assert "\x1b" not in output
    assert "\u202e" not in output
    assert "safe" in output
    assert "evil" in output


def test_ass_uses_shadow_color_without_a_background_box():
    settings = SubtitleSettings(
        shadow_color="#123456", background_color="#ABCDEF", background_box=False
    )
    output = render_ass([], settings, 1920, 1080)
    assert "&H80563412" in output


@pytest.mark.parametrize(
    "resolution,expected", [((960, 540), ",48,48,32,1"), ((3840, 2160), ",192,192,128,1")]
)
def test_ass_safe_margins_scale_with_resolution(resolution, expected):
    output = render_ass(
        [], SubtitleSettings(vertical_margin=64), resolution[0], resolution[1]
    )
    assert expected in output


def test_ass_sidecar_is_written_under_project_export_dir(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    sample_shot.dialogue = "Hello"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot)
    monkeypatch.setattr("app.services.subtitle_service.paths.exports_dir", lambda _id: str(tmp_path))
    result = write_ass_sidecar(db_session, sample_project)
    assert result["cue_count"] == 1
    assert result["path"] == str(tmp_path / "subtitles.ass")
    assert len(result["sha256"]) == 64
    assert os.path.isfile(result["path"])


def test_sidecar_replace_failure_preserves_prior_file_and_removes_temp(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    sample_shot.dialogue = "new dialogue"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot)
    destination = tmp_path / "subtitles.ass"
    destination.write_text("prior", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.subtitle_service.paths.exports_dir", lambda _id: str(tmp_path)
    )
    monkeypatch.setattr("app.services.subtitle_service.os.replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(SubtitleSidecarError, match="subtitles.ass"):
        write_ass_sidecar(db_session, sample_project)

    assert destination.read_text(encoding="utf-8") == "prior"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["subtitles.ass"]


def test_sidecar_directory_creation_failure_uses_structured_error(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    sample_shot.dialogue = "Hello"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot)
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("file", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.subtitle_service.paths.exports_dir",
        lambda _id: str(blocked_parent / "child"),
    )

    with pytest.raises(SubtitleSidecarError, match="export directory"):
        write_ass_sidecar(db_session, sample_project)


def test_off_mode_removes_stale_subtitle_sidecars(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    (tmp_path / "subtitles.ass").write_text("stale", encoding="utf-8")
    (tmp_path / "subtitles.srt").write_text("stale", encoding="utf-8")
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    _stub_render_environment(monkeypatch, tmp_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True
    assert not (tmp_path / "subtitles.ass").exists()
    assert not (tmp_path / "subtitles.srt").exists()


def test_api_get_put_settings_and_export(client, sample_project, sample_shot, db_session):
    got = client.get(f"/api/projects/{sample_project.id}/subtitles")
    assert got.status_code == 200
    assert got.json()["mode"] == "off"

    saved = client.put(f"/api/projects/{sample_project.id}/subtitles", json={
        "mode": "soft", "preset": "cinematic", "font_family": "Leelawadee UI",
        "font_size": 56, "text_color": "#FFFFFF", "outline_color": "#000000",
        "shadow_color": "#000000", "background_color": "#000000",
        "bold": True, "italic": False, "outline_width": 3, "shadow_depth": 2,
        "background_box": False, "position": "bottom", "vertical_margin": 64,
        "max_chars_per_line": 36,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["font_family"] == "Leelawadee UI"

    rejected = client.put(f"/api/projects/{sample_project.id}/subtitles", json={
        **saved.json(), "font_family": "C:/secret/font.ttf",
    })
    assert rejected.status_code == 422

    sample_shot.dialogue = "Dialogue from shot"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    exported = client.get(f"/api/projects/{sample_project.id}/export/subtitles?format=srt")
    assert exported.status_code == 200, exported.text
    assert "Dialogue from shot" in exported.text
    assert exported.headers["content-type"].startswith("application/x-subrip")

    styled = client.get(f"/api/projects/{sample_project.id}/export/subtitles?format=ass")
    assert styled.status_code == 200
    assert "Leelawadee UI" in styled.text
    assert "Dialogue from shot" in styled.text


def test_off_mode_does_not_create_or_burn_subtitles(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    sample_shot.dialogue = "Visible dialogue"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    commands = _stub_render_environment(monkeypatch, tmp_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True
    assert result["metadata_status"] == "clean"
    assert not (tmp_path / "subtitles.ass").exists()
    assert all("subtitles=" not in " ".join(command) for command in commands)


def test_unknown_source_audio_blocks_instead_of_rendering_silent(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    commands = _stub_render_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(render_service, "_source_has_audio", lambda _path: None)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is False
    assert "audio" in result["reason"].lower()
    assert "could not be detected" in result["reason"].lower()
    assert commands == []
    assert not (tmp_path / "review.mp4").exists()


@pytest.mark.parametrize(
    "tags,expected",
    [({}, "unverified"), ({"format": {"prompt": "hidden"}, "streams": []}, "leaked")],
)
def test_unverified_or_leaked_metadata_blocks_and_deletes_delivery(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path,
    tags, expected,
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    _stub_render_environment(monkeypatch, tmp_path)
    monkeypatch.setattr(render_service, "read_container_tags", lambda _path: tags)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is False
    assert result["metadata_status"] == expected
    assert result["delivery_validation"]["delivery_spec_pass"] is False
    assert not (tmp_path / "review.mp4").exists()


def test_soft_mode_writes_ass_and_srt_without_burning(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    sample_project.subtitle_settings = {**DEFAULT_SUBTITLE_SETTINGS, "mode": "soft"}
    sample_shot.dialogue = "สวัสดีจากบทสนทนา"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    commands = _stub_render_environment(monkeypatch, tmp_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True
    assert (tmp_path / "subtitles.ass").exists()
    assert (tmp_path / "subtitles.srt").exists()
    assert all("subtitles=" not in " ".join(command) for command in commands)


def test_render_blocks_on_subtitle_precision_validation_before_ffmpeg(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    sample_project.subtitle_settings = {
        **DEFAULT_SUBTITLE_SETTINGS,
        "mode": "soft",
        "max_chars_per_line": 12,
    }
    sample_shot.dialogue = "This dialogue must overflow into several subtitle cues"
    db_session.commit()
    _put_current_take_on_timeline(
        db_session, sample_project, sample_shot, start=0, end=0.001
    )
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    commands = _stub_render_environment(monkeypatch, tmp_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is False
    assert "subtitle timing" in result["reason"].lower()
    assert commands == []


def test_burn_in_mode_uses_generated_ass_and_blocks_on_filter_failure(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    sample_project.subtitle_settings = {**DEFAULT_SUBTITLE_SETTINGS, "mode": "burn_in"}
    sample_shot.dialogue = "Burn this"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    commands = _stub_render_environment(monkeypatch, tmp_path)

    rendered = render_service.render_review_video(db_session, sample_project.id)
    assert rendered["rendered"] is True
    assert any("subtitles=" in " ".join(command) for command in commands)

    real_run = render_service._run

    def fail_filter(command, timeout=300):
        if "subtitles=" in " ".join(command):
            return False, "No such filter: subtitles"
        return real_run(command, timeout)

    monkeypatch.setattr(render_service, "_run", fail_filter)
    blocked = render_service.render_review_video(db_session, sample_project.id)
    assert blocked["rendered"] is False
    assert "subtitle burn-in failed" in blocked["reason"].lower()


def test_burn_in_with_blank_dialogue_renders_with_truthful_warning(
    db_session, sample_project, sample_shot, monkeypatch, tmp_path
):
    from app.models import Take
    from app.services import render_service

    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    sample_project.subtitle_settings = {**DEFAULT_SUBTITLE_SETTINGS, "mode": "burn_in"}
    sample_shot.dialogue = "   "
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=2)
    db_session.query(Take).first().file_path = str(source)
    db_session.commit()
    commands = _stub_render_environment(monkeypatch, tmp_path)

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True
    assert any("no non-blank Shot dialogue" in warning for warning in result["warnings"])
    assert all("subtitles=" not in " ".join(command) for command in commands)


@pytest.mark.skipif(
    __import__("app.services.render_service", fromlist=["ffmpeg_path"]).ffmpeg_path() is None,
    reason="FFmpeg is not installed",
)
def test_real_ffmpeg_burns_same_ass_and_records_provenance(
    db_session, sample_project, sample_shot, tmp_path, monkeypatch
):
    from app.models import Take
    from app.services import render_service
    from app.services.mock_provider import _create_placeholder_png

    source = str(tmp_path / "source.png")
    _create_placeholder_png(source, 320, 180)
    sample_project.target_resolution = "320x180"
    sample_project.subtitle_settings = {
        **DEFAULT_SUBTITLE_SETTINGS,
        "mode": "burn_in",
        "font_family": "Leelawadee UI",
        "font_size": 24,
        "vertical_margin": 12,
    }
    sample_shot.dialogue = "สวัสดี Thai {safe}"
    db_session.commit()
    _put_current_take_on_timeline(db_session, sample_project, sample_shot, start=0, end=1)
    db_session.query(Take).first().file_path = source
    db_session.commit()
    monkeypatch.setattr(render_service.paths, "exports_dir", lambda _id: str(tmp_path))
    monkeypatch.setattr(
        "app.services.subtitle_service.paths.exports_dir", lambda _id: str(tmp_path)
    )

    result = render_service.render_review_video(db_session, sample_project.id)

    assert result["rendered"] is True, result["reason"]
    with open(result["provenance_path"], encoding="utf-8") as handle:
        subtitles = __import__("json").load(handle)["render_settings"]["subtitles"]
    assert subtitles["burned_in"] is True
    assert subtitles["cue_count"] == 1
    assert subtitles["ass_sidecar"]["sha256"]
    assert os.path.isfile(subtitles["ass_sidecar"]["path"])


# ---------------------------------------------------------------------------
# Fitting the canvas
# ---------------------------------------------------------------------------

class TestSubtitlesFitTheFrame:
    """A line of subtitle has to fit the width it is drawn on.

    The ASS header sets PlayResX to the real video width, so the font size is
    in the frame's own units. The vertical margin was already scaled to the
    canvas; the font size was not, so a setting that reads well on 1920x1080
    drew text three times too wide on a 576-wide vertical cut and ran off both
    edges. Clipped words are worse than small ones.
    """

    def _font_size_of(self, ass: str) -> int:
        for line in ass.splitlines():
            if line.startswith("Style: Default,"):
                return int(line.split(",")[2])
        raise AssertionError("no Default style in the rendered ASS")

    def _cue(self):
        return [{
            "start_sec": 0.0, "end_sec": 2.0,
            "text": "Every morning before the city woke, Pim swept the square.",
        }]

    def test_a_wide_canvas_keeps_the_configured_size(self):
        settings = subtitle_service.SubtitleSettings(
            font_size=52, max_chars_per_line=36,
        )
        ass = subtitle_service.render_ass(self._cue(), settings, 1920, 1080)
        assert self._font_size_of(ass) == 52

    def test_a_narrow_canvas_shrinks_the_font_to_fit(self):
        settings = subtitle_service.SubtitleSettings(
            font_size=52, max_chars_per_line=36,
        )
        ass = subtitle_service.render_ass(self._cue(), settings, 576, 1024)
        size = self._font_size_of(ass)
        assert size < 52, "52 units on a 576-wide frame runs off both edges"
        # A full line has to sit inside the frame minus its side margins.
        usable = 576 - 2 * round(576 * 0.05)
        assert size * 0.5 * settings.max_chars_per_line <= usable

    def test_fewer_characters_per_line_buys_back_the_size(self):
        """The two settings trade against each other, so wrapping harder is
        the way to keep large text on a narrow frame."""
        wide_wrap = subtitle_service.SubtitleSettings(
            font_size=52, max_chars_per_line=36,
        )
        tight_wrap = subtitle_service.SubtitleSettings(
            font_size=52, max_chars_per_line=18,
        )
        loose = self._font_size_of(
            subtitle_service.render_ass(self._cue(), wide_wrap, 576, 1024))
        tight = self._font_size_of(
            subtitle_service.render_ass(self._cue(), tight_wrap, 576, 1024))
        assert tight > loose

    def test_the_font_never_shrinks_below_legibility(self):
        """A subtitle nobody can read is not a subtitle."""
        settings = subtitle_service.SubtitleSettings(
            font_size=52, max_chars_per_line=80,
        )
        ass = subtitle_service.render_ass(self._cue(), settings, 288, 512)
        assert self._font_size_of(ass) >= subtitle_service.MIN_RENDERED_FONT_SIZE
