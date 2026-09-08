"""
Tests for the review render service.

The render tests that actually invoke FFmpeg are skipped when it is not
installed, so the suite stays green on a machine without it - but when FFmpeg
is present they assert against a real probed MP4, never a claimed one.
"""

import json
import os
import re
import uuid

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.models import Shot, Take, TimelineItem
from app.services import render_service, revisions, timeline_service
from app.services.mock_provider import _create_placeholder_png

ffmpeg_required = pytest.mark.skipif(
    render_service.ffmpeg_path() is None,
    reason="FFmpeg is not installed on this machine",
)
ffprobe_required = pytest.mark.skipif(
    render_service.ffprobe_path() is None,
    reason="ffprobe is not installed on this machine",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def add_approved_take_on_timeline(
    db: Session,
    project_id: str,
    shot_id: str,
    media_path: str,
    order: int = 0,
    duration: float = 1.0,
    review_status: str = "Approved",
    lineage: dict | None = None,
    width: int = 320,
    height: int = 180,
) -> Take:
    revisions.refresh_project(db, project_id)
    shot = db.query(Shot).filter(Shot.id == shot_id).one()
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        file_path=media_path,
        review_status=review_status,
        width=width,
        height=height,
        lineage=lineage or {},
        prompt_revision=shot.prompt_revision,
        prompt_sha256=shot.prompt_sha256,
        content_sha256=shot.content_sha256,
        reference_image_ids=list(shot.reference_asset_ids or []),
        reference_sha256s=list(shot.reference_sha256s or []),
    )
    db.add(take)
    db.add(TimelineItem(
        id=str(uuid.uuid4()),
        project_id=project_id,
        shot_id=shot_id,
        take_id=take.id,
        order=order,
        in_point_sec=order * duration,
        out_point_sec=(order + 1) * duration,
        duration_sec=duration,
        take_prompt_revision=shot.prompt_revision,
        shot_prompt_revision=shot.prompt_revision,
    ))
    db.commit()
    db.refresh(take)
    return take


# ---------------------------------------------------------------------------
# parse_resolution
# ---------------------------------------------------------------------------

class TestParseResolution:
    def test_parses_standard_resolution(self):
        assert render_service.parse_resolution("1920x1080") == (1920, 1080)

    def test_parses_vertical_resolution(self):
        assert render_service.parse_resolution("1080x1920") == (1080, 1920)

    def test_rounds_odd_dimensions_down_for_h264(self):
        assert render_service.parse_resolution("1921x1081") == (1920, 1080)

    @pytest.mark.parametrize("value", ["-10x-20", "0x0", "1x2", "2x1", "1x1"])
    def test_falls_back_on_non_positive_dimensions(self, value):
        assert render_service.parse_resolution(value) == (1920, 1080)

    @pytest.mark.parametrize("value", ["", "not-a-resolution", "1920", None])
    def test_falls_back_on_bad_input(self, value):
        assert render_service.parse_resolution(value) == (1920, 1080)


# ---------------------------------------------------------------------------
# Guard rails - the render must refuse rather than fabricate
# ---------------------------------------------------------------------------

class TestRenderRefusals:
    def test_unknown_project_raises(self, db_session):
        with pytest.raises(ValueError, match="Project not found"):
            render_service.render_review_video(db_session, "no-such-project")

    def test_empty_timeline_does_not_render(self, db_session, sample_project):
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is False
        assert "Timeline is empty" in result["reason"]
        assert result["output_path"] == ""

    def test_stale_timeline_cannot_be_labeled_as_a_pipeline_pass(
        self, db_session, sample_project, sample_shot, monkeypatch
    ):
        revisions.refresh_project(db_session, sample_project.id)
        take = Take(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            file_path="C:/missing/source.png",
            review_status="Approved",
            prompt_revision=sample_shot.prompt_revision,
            prompt_sha256=sample_shot.prompt_sha256,
            content_sha256=sample_shot.content_sha256,
            reference_image_ids=list(sample_shot.reference_asset_ids or []),
            reference_sha256s=list(sample_shot.reference_sha256s or []),
        )
        db_session.add(take)
        db_session.commit()
        built = timeline_service.build_timeline_from_approved_takes(
            db_session, sample_project.id
        )
        timeline_service.save_timeline_items(db_session, sample_project.id, built)
        sample_shot.action = "changed after timeline build"
        db_session.commit()
        monkeypatch.setattr(render_service, "ffmpeg_path", lambda: "ffmpeg")

        with pytest.raises(timeline_service.StaleTimelineError):
            render_service.render_review_video(db_session, sample_project.id)

    def test_missing_media_file_does_not_render(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id,
            str(tmp_path / "does_not_exist.png"),
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is False
        assert "media file is missing" in result["reason"]

    def test_unapproved_take_does_not_render(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media,
            review_status="Pending",
        )
        with pytest.raises(timeline_service.StaleTimelineError):
            render_service.render_review_video(db_session, sample_project.id)

    def test_deleted_take_does_not_render(
        self, db_session, sample_project, sample_shot
    ):
        db_session.add(TimelineItem(
            id=str(uuid.uuid4()),
            project_id=sample_project.id,
            shot_id=sample_shot.id,
            take_id="ghost-take-id",
            order=0,
            duration_sec=1.0,
        ))
        db_session.commit()
        with pytest.raises(timeline_service.StaleTimelineError):
            render_service.render_review_video(db_session, sample_project.id)


# ---------------------------------------------------------------------------
# Real FFmpeg render
# ---------------------------------------------------------------------------

@ffmpeg_required
class TestRenderExecution:
    def test_renders_single_still_to_mp4(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert os.path.isfile(result["output_path"])
        assert result["output_path"].endswith("review.mp4")
        assert result["segment_count"] == 1
        assert result["size_bytes"] > 0

    def test_renders_multiple_shots_in_timeline_order(
        self, db_session, sample_project, sample_scene, tmp_path
    ):
        from app.models import Shot

        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)

        for order in range(3):
            shot = Shot(
                id=str(uuid.uuid4()),
                scene_id=sample_scene.id,
                order=order,
                generation_mode="image",
                planned_duration_sec=1.0,
            )
            db_session.add(shot)
            db_session.commit()
            add_approved_take_on_timeline(
                db_session, sample_project.id, shot.id, media,
                order=order, duration=1.0,
            )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["segment_count"] == 3

    @ffprobe_required
    def test_rendered_video_matches_project_format(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """The output must really be at the project's resolution - probed, not
        assumed. The source still is 320x180, so this also proves the scale and
        pad normalisation ran."""
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=2.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        probe = render_service.probe_media(result["output_path"])
        assert (probe["width"], probe["height"]) == (1920, 1080)
        assert probe["codec"] == "h264"
        assert probe["duration_sec"] == pytest.approx(2.0, abs=0.35)

    @ffprobe_required
    def test_vertical_project_renders_vertical(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        sample_project.target_resolution = "1080x1920"
        db_session.commit()

        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]
        probe = render_service.probe_media(result["output_path"])
        assert (probe["width"], probe["height"]) == (1080, 1920)

    @ffprobe_required
    def test_mismatched_still_fills_vertical_frame_without_black_letterbox(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """A 2:3 provider image must fill 9:16 instead of gaining black bars."""
        sample_project.target_resolution = "108x192"
        db_session.commit()

        media = str(tmp_path / "solid-red.png")
        Image.new("RGB", (100, 150), (220, 30, 30)).save(media)
        add_approved_take_on_timeline(
            db_session,
            sample_project.id,
            sample_shot.id,
            media,
            duration=0.5,
            width=100,
            height=150,
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        frame = str(tmp_path / "rendered-frame.png")
        returncode, _stdout, stderr = render_service.run_captured([
            render_service.ffmpeg_path(), "-y", "-loglevel", "error",
            "-i", result["output_path"], "-frames:v", "1", frame,
        ], timeout=30)
        assert returncode == 0, stderr
        with Image.open(frame) as rendered:
            top_center = rendered.convert("RGB").getpixel((rendered.width // 2, 2))
        assert top_center[0] > 150 and top_center[1] < 80 and top_center[2] < 80

    def test_rerender_overwrites_same_output(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """Re-rendering after a timing change must not require regenerating
        takes (PRD DoD item 12)."""
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        take = add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        first = render_service.render_review_video(db_session, sample_project.id)
        assert first["rendered"] is True, first["reason"]

        item = db_session.query(TimelineItem).filter(
            TimelineItem.project_id == sample_project.id
        ).first()
        item.duration_sec = 2.0
        db_session.commit()

        second = render_service.render_review_video(db_session, sample_project.id)
        assert second["rendered"] is True, second["reason"]
        assert second["output_path"] == first["output_path"]
        # The approved take is untouched by re-rendering.
        db_session.refresh(take)
        assert take.review_status == "Approved"
        assert os.path.isfile(take.file_path)


# ---------------------------------------------------------------------------
# Audio preservation
# ---------------------------------------------------------------------------

@ffmpeg_required
@ffprobe_required
class TestAudioPreservation:
    """MiniMax H3 takes carry native stereo audio (verified: h264 864x480 +
    aac 32 kHz stereo). The review render used to normalise every segment with
    `-an`, so that audio never reached `review.mp4`. Segments must share one
    audio layout for the concat demuxer's stream copy, so a timeline that
    carries audio anywhere gets a silent track synthesised for the segments
    that have none."""

    def test_video_take_audio_reaches_the_review_render(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        media = synthesise_clip(str(tmp_path / "with_audio.mp4"), with_audio=True)
        assert render_service.probe_media(media)["has_audio"] is True

        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        probe = render_service.probe_media(result["output_path"])
        assert probe["has_audio"] is True
        assert probe["audio_codec"] == "aac"
        assert probe["codec"] == "h264"
        assert result["has_audio"] is True
        assert result["audio_codec"] == "aac"

    def test_near_silent_audio_is_normalized_to_delivery_loudness(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        """A quiet generated track must be made audible without unsafe peaks."""
        source = synthesise_clip(
            str(tmp_path / "source.mp4"), with_audio=True, duration=3.0
        )
        media = str(tmp_path / "near_silent.mp4")
        returncode, _stdout, stderr = render_service.run_captured([
            render_service.ffmpeg_path(), "-y", "-loglevel", "error",
            "-i", source, "-c:v", "copy", "-af", "volume=0.03",
            "-c:a", "aac", media,
        ], timeout=30)
        assert returncode == 0, stderr
        source_loudness = _audio_loudness(media)
        assert -65.0 < source_loudness["input_i"] < -40.0

        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=3.0
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        output_loudness = _audio_loudness(result["output_path"])
        assert output_loudness["input_i"] == pytest.approx(-16.0, abs=1.0)
        assert output_loudness["input_tp"] <= -1.5
        with open(result["provenance_path"], encoding="utf-8") as f:
            audio_report = json.load(f)["render_settings"]["audio"]
        assert audio_report["target_achieved"] is True

    def test_unattainable_high_crest_loudness_is_reported(
        self, db_session, sample_project, sample_scene, tmp_path
    ):
        """Sparse generated ambience needs gain staging before loudnorm.

        A single-pass loudnorm filter cannot raise very quiet high-crest audio
        to -16 LUFS without violating its true-peak ceiling.  This fixture
        reproduces the shape of the real H3 output surrounded by silent stills.
        """
        from app.models import Shot

        media = str(tmp_path / "sparse_audio.mp4")
        returncode, _stdout, stderr = render_service.run_captured([
            render_service.ffmpeg_path(), "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=24:d=3",
            "-f", "lavfi", "-i",
            "aevalsrc=if(lt(mod(t\\,0.5)\\,0.015)\\,0.03*sin(2*PI*440*t)\\,0):s=48000:d=3",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", media,
        ], timeout=30)
        assert returncode == 0, stderr
        source_loudness = _audio_loudness(media)
        assert source_loudness["input_i"] < -35.0
        assert source_loudness["input_tp"] > source_loudness["input_i"] + 15.0

        still = str(tmp_path / "frame.png")
        _create_placeholder_png(still, 320, 180)
        for order, (source, duration) in enumerate([
            (still, 3.0), (media, 3.0), (still, 3.0),
        ]):
            shot = Shot(
                id=str(uuid.uuid4()),
                scene_id=sample_scene.id,
                order=order,
                generation_mode="video" if source == media else "image",
                planned_duration_sec=duration,
            )
            db_session.add(shot)
            db_session.commit()
            add_approved_take_on_timeline(
                db_session, sample_project.id, shot.id, source,
                order=order, duration=duration,
            )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        output_loudness = _audio_loudness(result["output_path"])
        assert output_loudness["input_tp"] <= -1.5
        assert output_loudness["input_i"] < -17.0
        assert any("could not reach -16 LUFS" in item for item in result["warnings"])
        with open(result["provenance_path"], encoding="utf-8") as f:
            audio_report = json.load(f)["render_settings"]["audio"]
        assert audio_report["target_achieved"] is False
        assert audio_report["measured_output_lufs"] == pytest.approx(
            output_loudness["input_i"], abs=0.05
        )
        assert audio_report["measured_output_true_peak_dbtp"] == pytest.approx(
            output_loudness["input_tp"], abs=0.05
        )

    def test_still_only_timeline_stays_silent(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """Nothing on the timeline carries audio, so nothing is invented."""
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]
        assert render_service.probe_media(result["output_path"])["has_audio"] is False
        assert result["has_audio"] is False

    def test_silent_video_take_renders_without_audio(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        """A silent source video must still render - the audio handling may not
        assume every video has a track."""
        media = synthesise_clip(str(tmp_path / "silent.mp4"), with_audio=False)
        assert render_service.probe_media(media)["has_audio"] is False

        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]
        assert render_service.probe_media(result["output_path"])["has_audio"] is False

    def test_mixed_timeline_keeps_audio_and_full_duration(
        self, db_session, sample_project, sample_scene, tmp_path, synthesise_clip
    ):
        """A still, then a silent clip, then a clip with audio. The concat
        stream copy only carries audio through if every segment has one, and
        the silent fillers must not shorten the result."""
        from app.models import Shot

        still = str(tmp_path / "frame.png")
        _create_placeholder_png(still, 320, 180)
        silent = synthesise_clip(str(tmp_path / "silent.mp4"), with_audio=False)
        voiced = synthesise_clip(str(tmp_path / "voiced.mp4"), with_audio=True)

        for order, media in enumerate([still, silent, voiced]):
            shot = Shot(
                id=str(uuid.uuid4()),
                scene_id=sample_scene.id,
                order=order,
                generation_mode="video",
                planned_duration_sec=1.0,
            )
            db_session.add(shot)
            db_session.commit()
            add_approved_take_on_timeline(
                db_session, sample_project.id, shot.id, media,
                order=order, duration=1.0,
            )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]
        assert result["segment_count"] == 3

        probe = render_service.probe_media(result["output_path"])
        assert probe["has_audio"] is True
        assert probe["audio_codec"] == "aac"
        assert probe["duration_sec"] == pytest.approx(3.0, abs=0.35)
        assert result["warnings"] == []

    def test_every_segment_gets_the_same_audio_layout(
        self, db_session, sample_project, sample_scene, tmp_path, synthesise_clip
    ):
        """Uniform channel count and sample rate across segments is what makes
        the concat stream copy legal; assert it on the intermediates."""
        from app.models import Shot

        still = str(tmp_path / "frame.png")
        _create_placeholder_png(still, 320, 180)
        voiced = synthesise_clip(str(tmp_path / "voiced.mp4"), with_audio=True)

        for order, media in enumerate([still, voiced]):
            shot = Shot(
                id=str(uuid.uuid4()),
                scene_id=sample_scene.id,
                order=order,
                generation_mode="video",
                planned_duration_sec=1.0,
            )
            db_session.add(shot)
            db_session.commit()
            add_approved_take_on_timeline(
                db_session, sample_project.id, shot.id, media,
                order=order, duration=1.0,
            )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        segments_dir = os.path.join(
            os.path.dirname(result["output_path"]), "segments"
        )
        layouts = {
            _audio_layout(os.path.join(segments_dir, name))
            for name in sorted(os.listdir(segments_dir))
            if name.startswith("seg_")
        }
        assert len(layouts) == 1, layouts
        codec, channels, sample_rate = layouts.pop()
        assert codec == "aac"
        assert channels == 2
        assert sample_rate == render_service.AUDIO_SAMPLE_RATE


# ---------------------------------------------------------------------------
# Delivery hygiene: metadata out of the MP4, provenance into a sidecar
# ---------------------------------------------------------------------------

#: What ComfyUI's SaveVideo actually embeds - the full prompt graph, including
#: local model filenames and the creative prompt text.
COMFY_EMBEDDED_TAGS = {
    "prompt": (
        '{"140:131": {"inputs": {"prompt": "a calm blue sky", '
        '"class_type": "MiniMaxH3ImageToVideo"}}}'
    ),
    "comment": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "title": "internal working title",
}


@ffmpeg_required
@ffprobe_required
class TestDeliveryMetadata:
    """The delivered review.mp4 must not ship the generator's embedded
    workflow. A real H3 output carries a `prompt` tag holding the whole graph;
    FFmpeg copies input metadata to the output unless told not to."""

    def test_source_fixture_really_carries_metadata(self, tmp_path, synthesise_clip):
        """Guards the test itself: if the fixture stopped embedding tags, the
        stripping tests below would pass for the wrong reason."""
        media = synthesise_clip(
            str(tmp_path / "tagged.mp4"), with_audio=True,
            metadata=COMFY_EMBEDDED_TAGS,
        )
        keys = render_service.embedded_metadata_keys(media)
        assert "prompt" in keys
        assert "comment" in keys

    def test_render_strips_embedded_workflow_metadata(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        media = synthesise_clip(
            str(tmp_path / "tagged.mp4"), with_audio=True,
            metadata=COMFY_EMBEDDED_TAGS,
        )
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        assert render_service.embedded_metadata_keys(result["output_path"]) == []
        assert result["embedded_metadata_keys"] == []

    def test_no_prompt_text_survives_anywhere_in_the_container(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        """Not just the known keys: the prompt string must not appear in any
        format or stream tag of the delivered file."""
        media = synthesise_clip(
            str(tmp_path / "tagged.mp4"), with_audio=True,
            metadata=COMFY_EMBEDDED_TAGS,
        )
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        tags = render_service.read_container_tags(result["output_path"])
        blob = str(tags)
        assert "a calm blue sky" not in blob
        assert "safetensors" not in blob
        assert "internal working title" not in blob

    def test_intermediate_segments_are_stripped_too(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        """The concat stream-copies the segments, so a leak there reaches the
        delivery."""
        media = synthesise_clip(
            str(tmp_path / "tagged.mp4"), with_audio=True,
            metadata=COMFY_EMBEDDED_TAGS,
        )
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        segments_dir = os.path.join(
            os.path.dirname(result["output_path"]), "segments"
        )
        for name in os.listdir(segments_dir):
            if name.startswith("seg_"):
                path = os.path.join(segments_dir, name)
                assert render_service.embedded_metadata_keys(path) == [], name


@ffmpeg_required
class TestRenderResultDeliveryValidation:
    """The render result is what the Timeline page shows after a render.

    A waiver that only reaches the sidecar leaves the person looking at the
    screen believing the delivery passed.
    """

    def test_render_result_repeats_the_scoped_override_warning(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        # A real prior take for this shot - what the waiver below claims to
        # have replaced. Not placed on the timeline itself.
        revisions.refresh_project(db_session, sample_project.id)
        original = Take(
            id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=media,
            review_status="Rejected",
        )
        db_session.add(original)
        db_session.commit()
        take = add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0,
            # sample_project targets 1920x1080 (16:9); this take is
            # portrait, so the mismatch the waiver excuses is real.
            width=1080, height=1920,
            lineage={
                "waived_from_take_id": original.id,
                "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
            },
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert timeline_service.E2E_ASPECT_OVERRIDE_WARNING in result["warnings"]
        assert result["warning_metadata"][0]["take_ids"] == [take.id]
        assert result["delivery_validation"] == {
            "pipeline_pass": True,
            "delivery_spec_pass": False,
        }

    def test_an_unwaived_render_reports_a_clean_delivery(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert result["warning_metadata"] == []
        assert result["delivery_validation"] == {
            "pipeline_pass": True,
            "delivery_spec_pass": True,
        }
        assert timeline_service.E2E_ASPECT_OVERRIDE_WARNING not in result["warnings"]

    def test_duration_deviation_fails_the_delivery_spec(
        self, db_session, sample_project, sample_shot, tmp_path, monkeypatch
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        real_probe = render_service.probe_media

        def fake_probe(path):
            probe = real_probe(path)
            if path.endswith("review.mp4") and probe:
                probe = dict(probe)
                probe["duration_sec"] = (probe.get("duration_sec") or 0.0) + 5.0
            return probe

        monkeypatch.setattr(render_service, "probe_media", fake_probe)

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert any(
            "differs from the manifest total" in w for w in result["warnings"]
        )
        assert result["delivery_validation"] == {
            "pipeline_pass": True,
            "delivery_spec_pass": False,
        }

    @ffprobe_required
    def test_missing_required_audio_fails_the_delivery_spec(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip,
        monkeypatch,
    ):
        media = synthesise_clip(str(tmp_path / "voiced.mp4"), with_audio=True)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        real_probe = render_service.probe_media

        def fake_probe(path):
            probe = real_probe(path)
            if path.endswith("review.mp4") and probe:
                probe = dict(probe)
                probe["has_audio"] = False
            return probe

        monkeypatch.setattr(render_service, "probe_media", fake_probe)

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True, result["reason"]
        assert any("no audio stream" in w for w in result["warnings"])
        assert result["delivery_validation"] == {
            "pipeline_pass": True,
            "delivery_spec_pass": False,
        }

    def test_leaked_container_metadata_blocks_and_removes_the_delivery(
        self, db_session, sample_project, sample_shot, tmp_path, monkeypatch
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        monkeypatch.setattr(
            render_service,
            "read_container_tags",
            lambda _path: {"format": {"prompt": "hidden"}, "streams": []},
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is False
        assert "disallowed container metadata" in result["reason"]
        assert result["embedded_metadata_keys"] == ["prompt"]
        assert result["output_path"] == ""
        assert result["delivery_validation"] == {
            "pipeline_pass": False,
            "delivery_spec_pass": False,
        }

    def test_metadata_classification_uses_the_single_verified_snapshot(
        self, db_session, sample_project, sample_shot, tmp_path, monkeypatch
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        calls = 0

        def verified_tags(_path):
            nonlocal calls
            calls += 1
            return {"format": {"prompt": "not returned"}, "streams": []}

        monkeypatch.setattr(render_service, "read_container_tags", verified_tags)
        monkeypatch.setattr(render_service, "embedded_metadata_keys", lambda _path: [])

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is False
        assert result["metadata_status"] == "leaked"
        assert result["embedded_metadata_keys"] == ["prompt"]
        assert calls == 1

    def test_missing_provenance_sidecar_blocks_and_removes_delivery(
        self, db_session, sample_project, sample_shot, tmp_path, monkeypatch
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        monkeypatch.setattr(
            render_service, "write_render_provenance", lambda *a, **k: ""
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is False
        assert result["provenance_path"] == ""
        assert "provenance sidecar could not be written" in result["reason"]
        assert result["output_path"] == ""
        assert result["delivery_validation"] == {
            "pipeline_pass": False,
            "delivery_spec_pass": False,
        }

    def test_a_blocked_render_does_not_claim_a_pipeline_pass(
        self, db_session, sample_project
    ):
        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is False
        assert result["delivery_validation"] == {
            "pipeline_pass": False,
            "delivery_spec_pass": False,
        }

    def test_unwritable_render_directory_returns_structured_block(
        self, db_session, sample_project, sample_shot, tmp_path, monkeypatch
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        blocked_parent = tmp_path / "not-a-directory"
        blocked_parent.write_text("file", encoding="utf-8")
        monkeypatch.setattr(
            render_service.paths,
            "exports_dir",
            lambda _id: str(blocked_parent / "child"),
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is False
        assert "render directory" in result["reason"].lower()


@ffmpeg_required
class TestProvenanceSidecar:
    """Stripping the file must not lose the provenance - it moves beside it."""

    def test_failed_provenance_publish_preserves_previous_sidecar(
        self, db_session, sample_project, tmp_path, monkeypatch
    ):
        output = tmp_path / "review.mp4"
        output.write_bytes(b"output")
        sidecar = tmp_path / render_service.PROVENANCE_FILENAME
        sidecar.write_text("previous", encoding="utf-8")
        monkeypatch.setattr(
            render_service.json,
            "dump",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )

        result = render_service.write_render_provenance(
            db_session, sample_project, [], str(output), {}
        )

        assert result == ""
        assert sidecar.read_text(encoding="utf-8") == "previous"

    def test_sidecar_separates_pipeline_pass_from_waived_delivery_spec(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = tmp_path / "source.bin"
        media.write_bytes(b"source")
        output = tmp_path / "review.mp4"
        output.write_bytes(b"output")
        revisions.refresh_project(db_session, sample_project.id)
        original = Take(
            id=str(uuid.uuid4()), shot_id=sample_shot.id, file_path=str(media),
            review_status="Rejected",
        )
        db_session.add(original)
        db_session.commit()
        take = add_approved_take_on_timeline(
            db_session,
            sample_project.id,
            sample_shot.id,
            str(media),
            # sample_project targets 1920x1080 (16:9); this take is
            # portrait, so the mismatch the waiver excuses is real.
            width=1080, height=1920,
            lineage={
                "waived_from_take_id": original.id,
                "waiver_reason": timeline_service.TRUSTED_WAIVER_REASON,
            },
        )
        item = {
            "order": 0,
            "duration_sec": 1.0,
            "take_id": take.id,
            "shot_id": sample_shot.id,
        }

        sidecar = render_service.write_render_provenance(
            db_session,
            sample_project,
            [(item, take)],
            str(output),
            {"width": 1920, "height": 1080},
        )
        with open(sidecar, encoding="utf-8") as f:
            record = json.load(f)

        assert record["delivery_validation"] == {
            "pipeline_pass": True,
            "delivery_spec_pass": False,
        }
        # The sidecar's warnings are now everything the render had to say
        # about itself, as the strings the render collected; the structured
        # aspect overrides keep their own key rather than being mixed in.
        assert record["warnings"] == [
            "E2E Override · Aspect mismatch accepted · user-approved test override"
        ]
        assert record["warning_metadata"][0]["message"] == (
            "E2E Override · Aspect mismatch accepted · user-approved test override"
        )
        assert record["segments"][0]["take"]["lineage"] == take.lineage

    def test_sidecar_is_written_next_to_the_video(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        sidecar = result["provenance_path"]
        assert sidecar, "no provenance sidecar path returned"
        assert os.path.isfile(sidecar)
        assert os.path.dirname(sidecar) == os.path.dirname(result["output_path"])
        assert sidecar.endswith(render_service.PROVENANCE_FILENAME)

    def test_sidecar_records_take_and_prompt_for_every_segment(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        import json

        sample_shot.video_prompt = "a calm blue sky with drifting clouds"
        sample_shot.generation_mode = "video"
        db_session.commit()

        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        take = add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        with open(result["provenance_path"], encoding="utf-8") as f:
            record = json.load(f)

        assert record["project"]["id"] == sample_project.id
        assert record["render_settings"]["container_metadata_stripped"] is True
        assert len(record["segments"]) == 1

        segment = record["segments"][0]
        assert segment["take"]["id"] == take.id
        assert segment["take"]["source_path"] == media
        assert segment["take"]["source_sha256"]
        assert segment["shot"]["id"] == sample_shot.id
        assert segment["shot"]["video_prompt"] == "a calm blue sky with drifting clouds"
        assert record["output"]["sha256"]

    def test_sidecar_aspect_ratio_matches_rendered_resolution(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """A stale project declaration must not mislabel the rendered pixels."""
        sample_project.target_resolution = "864x480"
        sample_project.aspect_ratio = "16:9"
        db_session.commit()

        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]
        with open(result["provenance_path"], encoding="utf-8") as f:
            record = json.load(f)

        output_probe = record["output"]["probe"]
        assert (output_probe["width"], output_probe["height"]) == (864, 480)
        assert record["project"]["aspect_ratio"] == "9:5"

    def test_sidecar_carries_job_and_workflow_provenance(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """A take made by a real job must be traceable to the workflow snapshot
        and seed that produced it."""
        import json

        from app.models import GenerationJob, Workflow

        workflow = Workflow(
            id=str(uuid.uuid4()),
            name="H3 T2V",
            purpose="text-to-video",
            source_format="api",
            sha256_hash="abc123",
            version="1.0",
        )
        job = GenerationJob(
            id=str(uuid.uuid4()),
            shot_id=sample_shot.id,
            workflow_id=workflow.id,
            seed=42,
            status="Completed",
            comfyui_prompt_id="7bd626a7",
            workflow_snapshot_path="/snapshots/abc.json",
            workflow_sha256="abc123",
        )
        db_session.add_all([workflow, job])
        db_session.commit()

        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        take = add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        take.job_id = job.id
        db_session.commit()

        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        with open(result["provenance_path"], encoding="utf-8") as f:
            segment = json.load(f)["segments"][0]

        assert segment["job"]["seed"] == 42
        assert segment["job"]["comfyui_prompt_id"] == "7bd626a7"
        assert segment["job"]["workflow_snapshot_path"] == "/snapshots/abc.json"
        assert segment["workflow"]["name"] == "H3 T2V"
        assert segment["workflow"]["sha256_hash"] == "abc123"

    @ffprobe_required
    def test_sidecar_keeps_what_the_delivery_dropped(
        self, db_session, sample_project, sample_shot, tmp_path, synthesise_clip
    ):
        """The tags stripped from the MP4 are still recorded - as the source's
        key list, so nothing is lost, and as proof the output has none."""
        import json

        media = synthesise_clip(
            str(tmp_path / "tagged.mp4"), with_audio=True,
            metadata=COMFY_EMBEDDED_TAGS,
        )
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is True, result["reason"]

        with open(result["provenance_path"], encoding="utf-8") as f:
            record = json.load(f)

        assert "prompt" in record["segments"][0]["take"]["embedded_metadata_keys"]
        output_tags = record["output"]["container_tags"]["format"]
        assert "prompt" not in output_tags
        assert "comment" not in output_tags

    def test_blocked_render_writes_no_sidecar(self, db_session, sample_project):
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is False
        assert result["provenance_path"] == ""
        assert result["embedded_metadata_keys"] == []


def _audio_layout(path: str) -> tuple[str, int, int]:
    """(codec, channels, sample_rate) of a file's first audio stream."""
    import json

    from app.services.media_probe import ffprobe_path, run_captured

    returncode, stdout, stderr = run_captured([
        ffprobe_path(), "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,channels,sample_rate",
        "-of", "json", path,
    ], timeout=30)
    assert returncode == 0, stderr
    streams = json.loads(stdout or "{}").get("streams") or []
    assert streams, f"{path} has no audio stream"
    stream = streams[0]
    return stream["codec_name"], int(stream["channels"]), int(stream["sample_rate"])


def _audio_loudness(path: str) -> dict[str, float]:
    """Measure integrated LUFS and true peak with FFmpeg's loudnorm filter."""
    from app.services.media_probe import ffmpeg_path, run_captured

    returncode, _stdout, stderr = run_captured([
        ffmpeg_path(), "-hide_banner", "-nostats", "-i", path,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-",
    ], timeout=30)
    assert returncode == 0, stderr
    matches = re.findall(r"\{[^{}]+\}", stderr)
    assert matches, f"no loudnorm measurement in ffmpeg output: {stderr[-500:]}"
    payload = json.loads(matches[-1])
    return {key: float(payload[key]) for key in ("input_i", "input_tp")}


# ---------------------------------------------------------------------------
# probe_media
# ---------------------------------------------------------------------------

class TestProbeMedia:
    def test_missing_file_returns_empty(self, tmp_path):
        assert render_service.probe_media(str(tmp_path / "nope.mp4")) == {}

    @ffprobe_required
    def test_probes_a_still_image(self, tmp_path):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 640, 360)
        probe = render_service.probe_media(media)
        assert (probe["width"], probe["height"]) == (640, 360)


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------

class _SilentVoice:
    """A speech engine that writes correctly-timed silence.

    The point of these tests is the mux and the reporting, not the sound of a
    platform voice, and a real one would make them slow and machine-dependent.
    """

    def __init__(self, seconds_per_word: float = 0.3):
        self.seconds_per_word = seconds_per_word
        self.spoken: list[str] = []

    def speak(self, text: str, out_path: str) -> float:
        import wave

        from app.services import narration as narration_module

        self.spoken.append(text)
        duration = max(0.2, len(text.split()) * self.seconds_per_word)
        with wave.open(out_path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(narration_module.SAMPLE_RATE)
            handle.writeframes(b"\x00\x00" * int(duration * narration_module.SAMPLE_RATE))
        return duration


@ffmpeg_required
class TestNarration:
    def test_a_render_without_narration_asked_for_stays_silent_about_it(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        sample_shot.dialogue = "They gave her the smallest desk."
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=2.0
        )

        result = render_service.render_review_video(db_session, sample_project.id)

        assert result["rendered"] is True
        assert result["narration"] == {"present": False}

    def test_narration_gives_a_silent_film_a_voice(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """A still has no audio of its own, so the voice becomes the track.

        Without this the render would stay video-only and the spoken film
        would have to be assembled outside the app.
        """
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        sample_shot.dialogue = "They gave her the smallest desk in the survey office."
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=3.0
        )
        voice = _SilentVoice()

        result = render_service.render_review_video(
            db_session, sample_project.id, narrate=True, voice=voice,
        )

        assert result["rendered"] is True, result.get("reason")
        assert result["narration"]["present"] is True
        assert result["has_audio"] is True
        assert voice.spoken == ["They gave her the smallest desk in the survey office."]

    def test_a_shot_with_nothing_to_say_produces_no_narration(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        sample_shot.dialogue = ""
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=2.0
        )
        voice = _SilentVoice()

        result = render_service.render_review_video(
            db_session, sample_project.id, narrate=True, voice=voice,
        )

        assert result["narration"] == {"present": False}
        assert voice.spoken == []

    def test_an_overrunning_line_is_reported_on_the_render(
        self, db_session, sample_project, sample_shot, tmp_path
    ):
        """The user is told which lines to rewrite, rather than finding out
        by watching a voice run over the cut."""
        media = str(tmp_path / "frame.png")
        _create_placeholder_png(media, 320, 180)
        sample_shot.dialogue = "A line with far too many words for one very short shot"
        add_approved_take_on_timeline(
            db_session, sample_project.id, sample_shot.id, media, duration=1.0
        )

        result = render_service.render_review_video(
            db_session, sample_project.id, narrate=True,
            voice=_SilentVoice(seconds_per_word=1.0),
        )

        assert result["narration"]["overruns"], result["narration"]
        assert any("run past the shot" in w for w in result["warnings"]), result["warnings"]
