"""
Tests for media probing and the provider metadata it feeds.

Regression guard: the real ComfyUI provider used to record every downloaded
file as 0x0 at 0.0s with the container extension as its codec. That is wrong
provenance, and a zero duration makes the timeline silently fall back to the
shot's planned duration instead of the media's real length. Found during the
first real generation against a live instance.
"""

import pytest

from app.services import media_probe
from app.services.media_probe import _parse_frame_rate, probe_media_file
from app.services.mock_provider import (
    _create_placeholder_mp4,
    _create_placeholder_png,
)

ffprobe_required = pytest.mark.skipif(
    media_probe.ffprobe_path() is None,
    reason="ffprobe is not installed on this machine",
)
ffmpeg_required = pytest.mark.skipif(
    media_probe.ffmpeg_path() is None,
    reason="ffmpeg is not installed on this machine",
)


class TestParseFrameRate:
    @pytest.mark.parametrize("value,expected", [
        ("24/1", 24.0),
        ("30000/1001", pytest.approx(29.97, abs=0.01)),
        ("25", 25.0),
        ("0/0", 0.0),      # ffprobe reports this for audio streams
        ("", 0.0),
        (None, 0.0),
        ("not-a-rate", 0.0),
    ])
    def test_rational_frame_rates(self, value, expected):
        assert _parse_frame_rate(value) == expected


class TestProbeMediaFile:
    def test_missing_file_returns_empty(self, tmp_path):
        assert probe_media_file(str(tmp_path / "absent.mp4")) == {}

    def test_unreadable_file_returns_empty(self, tmp_path):
        junk = tmp_path / "junk.mp4"
        junk.write_bytes(b"not a media file")
        # Either an empty dict or zeroed fields is acceptable; what must not
        # happen is an exception escaping into the download path.
        assert isinstance(probe_media_file(str(junk)), dict)

    @ffprobe_required
    def test_probes_a_still_image(self, tmp_path):
        path = str(tmp_path / "frame.png")
        _create_placeholder_png(path, 640, 360)
        probe = probe_media_file(path)
        assert (probe["width"], probe["height"]) == (640, 360)
        assert probe["has_audio"] is False

    @ffprobe_required
    @ffmpeg_required
    def test_probes_a_video(self, tmp_path):
        path = str(tmp_path / "clip.mp4")
        assert _create_placeholder_mp4(path, 320, 180, 1.0, 24.0)
        probe = probe_media_file(path)
        assert (probe["width"], probe["height"]) == (320, 180)
        assert probe["codec"] == "h264"
        assert probe["frame_rate"] == 24.0
        assert probe["duration_sec"] == pytest.approx(1.0, abs=0.15)

    @ffprobe_required
    @ffmpeg_required
    def test_codec_is_the_stream_codec_not_the_container(self, tmp_path):
        """An .mp4 holds h264; recording 'mp4' as the codec is meaningless."""
        path = str(tmp_path / "clip.mp4")
        _create_placeholder_mp4(path, 320, 180, 0.5, 24.0)
        assert probe_media_file(path)["codec"] == "h264"

    @ffprobe_required
    @ffmpeg_required
    def test_silent_video_reports_no_audio(self, tmp_path):
        path = str(tmp_path / "silent.mp4")
        _create_placeholder_mp4(path, 320, 180, 0.5, 24.0)
        probe = probe_media_file(path)
        assert probe["has_audio"] is False
        assert probe["audio_codec"] == ""


@ffprobe_required
@ffmpeg_required
class TestAudioDetection:
    """MiniMax H3 emits video with a native stereo audio track, so a take's
    metadata has to distinguish a silent clip from one carrying audio."""

    @pytest.fixture()
    def clip_with_audio(self, tmp_path, synthesise_clip) -> str:
        return synthesise_clip(str(tmp_path / "with_audio.mp4"), with_audio=True)

    def test_audio_track_is_detected(self, clip_with_audio):
        probe = probe_media_file(clip_with_audio)
        assert probe["has_audio"] is True
        assert probe["audio_codec"] == "aac"

    def test_video_metadata_still_read_alongside_audio(self, clip_with_audio):
        """The video stream must be picked out, not whichever stream is first."""
        probe = probe_media_file(clip_with_audio)
        assert probe["codec"] == "h264"
        assert probe["width"] == 320
        assert probe["frame_rate"] == 24.0


class TestProviderMetadata:
    """The provider must persist what it probed, not what it guessed."""

    @ffprobe_required
    @ffmpeg_required
    def test_downloaded_video_carries_real_metadata(self, tmp_path, monkeypatch):
        import asyncio

        from app.services.comfyui_provider import RealComfyUIProvider

        # Stand in for a download: the file is already on disk, so only the
        # probing half of _download_output is under test.
        media = tmp_path / "out.mp4"
        assert _create_placeholder_mp4(str(media), 640, 360, 1.0, 24.0)

        provider = RealComfyUIProvider(
            base_url="http://127.0.0.1:1", output_base_dir=str(tmp_path)
        )

        class FakeResponse:
            content = media.read_bytes()

            def raise_for_status(self):
                return None

        class FakeClient:
            async def get(self, _url, params=None):
                return FakeResponse()

        result = asyncio.run(provider._download_output(
            FakeClient(), {"filename": "out.mp4", "subfolder": "", "type": "output"},
            "prompt-1", "video",
        ))

        assert result is not None
        assert result.file_type == "video"
        assert (result.width, result.height) == (640, 360)
        assert result.codec == "h264"          # not "mp4"
        assert result.frame_rate == 24.0
        assert result.duration_sec == pytest.approx(1.0, abs=0.15)

    def test_extension_fallback_when_probe_unavailable(self, tmp_path, monkeypatch):
        """Without ffprobe the codec falls back to the extension rather than
        the download failing outright."""
        import asyncio

        from app.services import comfyui_provider
        from app.services.comfyui_provider import RealComfyUIProvider

        monkeypatch.setattr(comfyui_provider, "probe_media_file", lambda _p: {})

        provider = RealComfyUIProvider(
            base_url="http://127.0.0.1:1", output_base_dir=str(tmp_path)
        )

        class FakeResponse:
            content = b"\x00\x01"

            def raise_for_status(self):
                return None

        class FakeClient:
            async def get(self, _url, params=None):
                return FakeResponse()

        result = asyncio.run(provider._download_output(
            FakeClient(), {"filename": "out.mp4", "subfolder": "", "type": "output"},
            "prompt-2", "video",
        ))
        assert result is not None
        assert result.codec == "mp4"
        assert result.width == 0
