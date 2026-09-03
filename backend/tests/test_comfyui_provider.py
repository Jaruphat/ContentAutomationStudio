"""Tests for the real ComfyUI provider."""

import os
import pytest
import httpx

from app.services.comfyui_provider import RealComfyUIProvider
from app.services.comfyui_adapter import HealthStatus


class TestRealComfyUIProviderHealth:
    """Test the real ComfyUI provider's health check."""

    @pytest.mark.asyncio
    async def test_health_check_against_real_instance(self):
        """
        Test connectivity against the real ComfyUI instance at :8001.

        This test connects to the actual ComfyUI server. It will pass if
        ComfyUI is running, and gracefully report offline if it's not.
        """
        provider = RealComfyUIProvider(base_url="http://127.0.0.1:8001")
        health = await provider.check_health()

        # The health check should always return a valid HealthStatus
        assert isinstance(health, HealthStatus)
        assert health.mock is False

        if health.online:
            # If online, we should have version info
            assert health.comfyui_version != ""
            assert health.error is None
            print("\nComfyUI ONLINE:")
            print(f"  Version: {health.comfyui_version}")
            print(f"  GPU: {health.gpu_info}")
            print(f"  Queue: {health.queue_remaining}")
        else:
            # If offline, that's OK - just verify we got a clean error
            assert health.error is not None
            print(f"\nComfyUI OFFLINE: {health.error}")

    @pytest.mark.asyncio
    async def test_health_check_unreachable_host(self):
        """Test health check against an unreachable host returns offline."""
        provider = RealComfyUIProvider(base_url="http://127.0.0.1:59999")
        health = await provider.check_health()

        assert isinstance(health, HealthStatus)
        assert health.online is False
        assert health.mock is False
        assert health.error is not None


class TestRealComfyUIProviderUnit:
    """Unit tests for RealComfyUIProvider methods."""

    def test_output_dir_creation(self, tmp_path):
        """Test that the provider creates its output directory."""
        out_dir = str(tmp_path / "test_output")
        RealComfyUIProvider(
            base_url="http://127.0.0.1:59999",
            output_base_dir=out_dir,
        )
        assert os.path.isdir(out_dir)

    def test_parse_history_outputs(self):
        """Test parsing ComfyUI history output format."""
        provider = RealComfyUIProvider(base_url="http://127.0.0.1:59999")
        outputs = {
            "18": {
                "images": [
                    {
                        "filename": "output_00001.png",
                        "subfolder": "",
                        "type": "output",
                    }
                ]
            }
        }
        result = provider._parse_history_outputs(outputs)
        assert len(result) == 1
        assert result[0]["filename"] == "output_00001.png"

    def test_parse_history_outputs_with_video(self):
        """Test parsing history outputs that include video/gif."""
        provider = RealComfyUIProvider(base_url="http://127.0.0.1:59999")
        outputs = {
            "20": {
                "gifs": [
                    {
                        "filename": "animation_00001.mp4",
                        "subfolder": "",
                        "type": "output",
                    }
                ]
            }
        }
        result = provider._parse_history_outputs(outputs)
        assert len(result) == 1
        assert result[0]["type"] == "video"

    def test_parse_history_outputs_empty(self):
        """Test parsing empty history outputs."""
        provider = RealComfyUIProvider(base_url="http://127.0.0.1:59999")
        result = provider._parse_history_outputs({})
        assert result == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("history_status,queue_status", [(500, 200), (200, 503)])
    async def test_submission_existence_is_unknown_when_either_query_is_non_200(
        self, monkeypatch, history_status, queue_status
    ):
        """An empty queue cannot turn an ambiguous history response into absence."""
        def handler(request: httpx.Request) -> httpx.Response:
            if "/history/" in str(request.url):
                return httpx.Response(history_status, json={})
            return httpx.Response(
                queue_status, json={"queue_running": [], "queue_pending": []}
            )

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            "app.services.comfyui_provider.httpx.AsyncClient",
            lambda *args, **kwargs: real_client(transport=transport),
        )
        provider = RealComfyUIProvider(base_url="http://comfy.test")

        assert await provider.submission_exists("unknown-prompt") is None

    @pytest.mark.asyncio
    async def test_submission_is_absent_only_after_two_successful_negative_queries(
        self, monkeypatch
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            if "/history/" in str(request.url):
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            "app.services.comfyui_provider.httpx.AsyncClient",
            lambda *args, **kwargs: real_client(transport=transport),
        )
        provider = RealComfyUIProvider(base_url="http://comfy.test")

        assert await provider.submission_exists("definitely-absent") is False
