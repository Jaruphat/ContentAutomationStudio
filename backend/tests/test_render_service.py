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
from sqlalchemy.orm import Session

from app.models import Take, TimelineItem
from app.services import render_service
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
) -> Take:
    take = Take(
        id=str(uuid.uuid4()),
        shot_id=shot_id,
        file_path=media_path,
        review_status=review_status,
        width=320,
        height=180,
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
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is False
        assert "Only approved takes" in result["reason"]

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
        result = render_service.render_review_video(db_session, sample_project.id)
        assert result["rendered"] is False
        assert "no longer exists" in result["reason"]


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
        assert output_loudness["input_tp"] <= -1.0

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
class TestProvenanceSidecar:
    """Stripping the file must not lose the provenance - it moves beside it."""

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
