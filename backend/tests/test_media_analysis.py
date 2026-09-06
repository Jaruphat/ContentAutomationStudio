"""Measured output, error disclosure, and preservation of review decisions."""

import shutil
import subprocess
from pathlib import Path

import pytest

from app import paths
from app.models import Take
from app.services import media_analysis


@pytest.fixture
def clips(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg not installed")
    outputs = []
    for name, source in [("still", "color=black:size=160x96:rate=24:duration=2"),
                         ("moving", "testsrc2=size=160x96:rate=24:duration=2")]:
        target = tmp_path / f"{name}.mp4"
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", source,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)],
                       check=True, capture_output=True, timeout=30)
        outputs.append(target)
    return outputs


def test_real_static_and_moving_video_are_distinguished(clips):
    still, moving = [media_analysis.analyze_video(str(path)) for path in clips]
    assert still["status"] == moving["status"] == "measured"
    assert still["mean_luma_change"] == 0
    assert still["near_static_fraction"] == 1
    assert still["warnings"]
    assert moving["mean_luma_change"] > still["mean_luma_change"]
    assert moving["near_static_fraction"] < still["near_static_fraction"]
    assert len(moving["file_sha256"]) == 64


def test_missing_decoder_is_unavailable_not_zero_motion(monkeypatch, tmp_path):
    monkeypatch.setattr(media_analysis.shutil, "which", lambda _: None)
    result = media_analysis.analyze_video(str(tmp_path / "clip.mp4"))
    assert result["status"] == "unavailable"
    assert "FFmpeg" in result["reason"]
    assert "mean_luma_change" not in result


def test_corrupt_video_cannot_be_reported_as_a_static_success(tmp_path):
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"not a movie")
    report = media_analysis.analyze_video(str(source))
    assert report["status"] == "unavailable"


def test_insufficient_samples_do_not_produce_a_quality_claim():
    assert media_analysis.summarize([0])["status"] == "unavailable"
    result = media_analysis.summarize([0, 0, 0, 0])
    assert "not a quality score" in result["interpretation"]
    assert "below" in result["interpretation"]


def test_analysis_does_not_approve_or_revise_the_shot(client, db_session, sample_shot, monkeypatch):
    target = Path(paths.generated_dir()) / "analyze-test.mp4"
    target.write_bytes(b"fixture")
    take = Take(shot_id=sample_shot.id, file_path=str(target), duration_sec=2,
                review_status="Pending", provenance={"original": "retained"})
    db_session.add(take)
    db_session.commit()
    revision = sample_shot.prompt_revision
    monkeypatch.setattr(media_analysis, "analyze_video", lambda _: media_analysis.summarize([0, 0, 0]))
    response = client.post(f"/api/takes/{take.id}/analyze")
    assert response.status_code == 200
    assert response.json()["review_status"] == "Pending"
    assert response.json()["provenance"]["original"] == "retained"
    assert response.json()["provenance"]["media_analysis"]["near_static_fraction"] == 1
    db_session.refresh(sample_shot)
    assert sample_shot.prompt_revision == revision


def test_analysis_refuses_paths_outside_app_data(client, db_session, sample_shot, tmp_path):
    take = Take(shot_id=sample_shot.id, file_path=str(tmp_path / "outside.mp4"), duration_sec=2)
    db_session.add(take)
    db_session.commit()
    assert client.post(f"/api/takes/{take.id}/analyze").status_code == 422
    assert client.post("/api/takes/absent/analyze").status_code == 404
