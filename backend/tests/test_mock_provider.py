"""
Tests for the MockComfyUIProvider.

Validates deterministic job submission, status progression, output generation,
and health checks.
"""

import os
import time

import pytest

from app.services.comfyui_adapter import JobStatusEnum
from app.services.mock_provider import MockComfyUIProvider, _create_placeholder_png


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def output_dir(tmp_path):
    """Provide a temporary directory for mock outputs."""
    return str(tmp_path / "mock_outputs")


@pytest.fixture()
def provider(output_dir):
    """Create a MockComfyUIProvider with a temp output dir."""
    return MockComfyUIProvider(output_base_dir=output_dir)


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------

class TestSubmitJob:
    """Tests for MockComfyUIProvider.submit_job."""

    @pytest.mark.asyncio
    async def test_submit_returns_prompt_id(self, provider):
        prompt_id = await provider.submit_job({"some": "payload"}, "job-001")
        assert isinstance(prompt_id, str)
        assert prompt_id.startswith("mock-")

    @pytest.mark.asyncio
    async def test_submit_deterministic_prompt_id(self, provider):
        """Same job_id should produce the same prompt_id."""
        id1 = await provider.submit_job({}, "job-abc")
        # Create a new provider to verify determinism is based on job_id, not state
        provider2 = MockComfyUIProvider(output_base_dir=provider._output_dir)
        id2 = await provider2.submit_job({}, "job-abc")
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_submit_different_jobs_different_ids(self, provider):
        id1 = await provider.submit_job({}, "job-001")
        id2 = await provider.submit_job({}, "job-002")
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_submit_tracks_submission(self, provider):
        prompt_id = await provider.submit_job({}, "job-001")
        assert prompt_id in provider._submissions


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------

class TestGetJobStatus:
    """Tests for MockComfyUIProvider.get_job_status state progression."""

    @pytest.mark.asyncio
    async def test_unknown_prompt_id_returns_failed(self, provider):
        status = await provider.get_job_status("nonexistent-id")
        assert status.status == JobStatusEnum.FAILED
        assert status.error_code == "UNKNOWN_JOB"

    @pytest.mark.asyncio
    async def test_immediate_status_is_queued(self, provider):
        prompt_id = await provider.submit_job({}, "job-queued")
        status = await provider.get_job_status(prompt_id)
        assert status.status == JobStatusEnum.QUEUED
        assert status.progress == 0.0

    @pytest.mark.asyncio
    async def test_status_after_1s_is_running(self, provider):
        prompt_id = await provider.submit_job({}, "job-running")
        # Artificially age the submission by 1.5 seconds
        provider._submissions[prompt_id] = time.time() - 1.5
        status = await provider.get_job_status(prompt_id)
        assert status.status == JobStatusEnum.RUNNING
        assert 0.0 < status.progress < 1.0

    @pytest.mark.asyncio
    async def test_status_after_3s_is_completed(self, provider):
        prompt_id = await provider.submit_job({}, "job-completed")
        # Artificially age the submission by 4 seconds
        provider._submissions[prompt_id] = time.time() - 4.0
        status = await provider.get_job_status(prompt_id)
        assert status.status == JobStatusEnum.COMPLETED
        assert status.progress == 1.0

    @pytest.mark.asyncio
    async def test_completed_status_has_outputs(self, provider):
        prompt_id = await provider.submit_job({}, "job-with-output")
        provider._submissions[prompt_id] = time.time() - 5.0
        status = await provider.get_job_status(prompt_id)
        assert status.status == JobStatusEnum.COMPLETED
        assert len(status.outputs) > 0
        assert status.outputs[0]["type"] == "image"

    @pytest.mark.asyncio
    async def test_completed_creates_output_file(self, provider, output_dir):
        prompt_id = await provider.submit_job({}, "job-file")
        provider._submissions[prompt_id] = time.time() - 5.0
        status = await provider.get_job_status(prompt_id)
        file_path = status.outputs[0]["file_path"]
        assert os.path.isfile(file_path)

    @pytest.mark.asyncio
    async def test_running_progress_ramps(self, provider):
        """Progress should increase over the Running window (1-3s)."""
        prompt_id = await provider.submit_job({}, "job-ramp")

        # At 1.5s elapsed -> progress should be ~0.25
        provider._submissions[prompt_id] = time.time() - 1.5
        status_early = await provider.get_job_status(prompt_id)

        # At 2.5s elapsed -> progress should be ~0.75
        provider._submissions[prompt_id] = time.time() - 2.5
        status_late = await provider.get_job_status(prompt_id)

        assert status_early.progress < status_late.progress


# ---------------------------------------------------------------------------
# get_job_outputs
# ---------------------------------------------------------------------------

class TestGetJobOutputs:
    """Tests for MockComfyUIProvider.get_job_outputs."""

    @pytest.mark.asyncio
    async def test_returns_output_files(self, provider):
        prompt_id = await provider.submit_job({}, "job-outputs")
        outputs = await provider.get_job_outputs(prompt_id)
        assert len(outputs) == 1
        assert outputs[0].file_type == "image"
        assert outputs[0].width == 1
        assert outputs[0].height == 1
        assert outputs[0].codec == "png"

    @pytest.mark.asyncio
    async def test_output_file_created(self, provider, output_dir):
        prompt_id = await provider.submit_job({}, "job-file-created")
        outputs = await provider.get_job_outputs(prompt_id)
        assert os.path.isfile(outputs[0].file_path)

    @pytest.mark.asyncio
    async def test_output_file_is_valid_png(self, provider):
        prompt_id = await provider.submit_job({}, "job-valid-png")
        outputs = await provider.get_job_outputs(prompt_id)
        with open(outputs[0].file_path, "rb") as f:
            header = f.read(8)
        # PNG signature
        assert header == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------

class TestCheckHealth:
    """Tests for MockComfyUIProvider.check_health."""

    @pytest.mark.asyncio
    async def test_health_online(self, provider):
        health = await provider.check_health()
        assert health.online is True

    @pytest.mark.asyncio
    async def test_health_is_mock(self, provider):
        health = await provider.check_health()
        assert health.mock is True

    @pytest.mark.asyncio
    async def test_health_version(self, provider):
        health = await provider.check_health()
        assert health.comfyui_version == "mock-1.0.0"

    @pytest.mark.asyncio
    async def test_health_queue_remaining(self, provider):
        health = await provider.check_health()
        assert health.queue_remaining == 0

    @pytest.mark.asyncio
    async def test_health_gpu_info(self, provider):
        health = await provider.check_health()
        assert "Mock GPU" in health.gpu_info


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Test that same inputs produce the same outputs."""

    @pytest.mark.asyncio
    async def test_same_job_id_same_prompt_id(self, output_dir):
        p1 = MockComfyUIProvider(output_base_dir=output_dir)
        p2 = MockComfyUIProvider(output_base_dir=output_dir)

        id1 = await p1.submit_job({"workflow": "data"}, "deterministic-job")
        id2 = await p2.submit_job({"workflow": "data"}, "deterministic-job")
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_output_file_path_deterministic(self, output_dir):
        p1 = MockComfyUIProvider(output_base_dir=output_dir)
        p2 = MockComfyUIProvider(output_base_dir=output_dir)

        prompt_id = await p1.submit_job({}, "det-job")
        outputs1 = await p1.get_job_outputs(prompt_id)

        prompt_id2 = await p2.submit_job({}, "det-job")
        outputs2 = await p2.get_job_outputs(prompt_id2)

        assert outputs1[0].file_path == outputs2[0].file_path


# ---------------------------------------------------------------------------
# Placeholder PNG helper
# ---------------------------------------------------------------------------

class TestCreatePlaceholderPng:
    """Tests for the _create_placeholder_png helper."""

    def test_creates_file(self, tmp_path):
        path = str(tmp_path / "test.png")
        _create_placeholder_png(path)
        assert os.path.isfile(path)

    def test_file_has_png_signature(self, tmp_path):
        path = str(tmp_path / "test.png")
        _create_placeholder_png(path)
        with open(path, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n"

    def test_creates_parent_directories(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "dir" / "test.png")
        _create_placeholder_png(path)
        assert os.path.isfile(path)

    def test_custom_dimensions(self, tmp_path):
        path = str(tmp_path / "big.png")
        _create_placeholder_png(path, width=4, height=4)
        assert os.path.isfile(path)
        # File should be larger than 1x1
        size_1x1_path = str(tmp_path / "small.png")
        _create_placeholder_png(size_1x1_path, width=1, height=1)
        assert os.path.getsize(path) >= os.path.getsize(size_1x1_path)
