"""Tests for the real ComfyUI provider."""

import os
import pytest

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
