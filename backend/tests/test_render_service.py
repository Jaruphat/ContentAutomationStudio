"""
Tests for the review render service.

The render tests that actually invoke FFmpeg are skipped when it is not
installed, so the suite stays green on a machine without it - but when FFmpeg
is present they assert against a real probed MP4, never a claimed one.
"""

import os
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
