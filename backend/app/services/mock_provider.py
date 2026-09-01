"""
Deterministic Mock ComfyUI Provider.

Implements ComfyUIProvider for development and testing.
- Generates deterministic prompt_ids based on job_id.
- Cycles through Queued -> Running -> Completed states.
- Creates actual 1x1 PNG placeholder files for outputs.
- Always reports healthy with mock=True.
"""

import hashlib
import os
import struct
import time
import zlib
from typing import Any

from app import paths
from app.services.comfyui_adapter import (
    ComfyUIProvider,
    HealthStatus,
    JobStatus,
    JobStatusEnum,
    OutputFile,
)


def _create_placeholder_png(path: str, width: int = 1, height: int = 1) -> None:
    """
    Create a minimal valid PNG file at the given path.

    Produces a 1x1 pixel gray PNG (~67 bytes) without any external
    dependency like PIL/Pillow.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_len = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return chunk_len + chunk_type + data + crc

    # IHDR: width, height, bit_depth=8, color_type=0 (grayscale),
    # compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT: one row of pixels. Filter byte 0 + pixel bytes.
    raw_row = b"\x00" + (b"\x80" * width)  # filter=None, mid-gray pixels
    raw_data = b""
    for _ in range(height):
        raw_data += raw_row
    compressed = zlib.compress(raw_data)
    idat = _chunk(b"IDAT", compressed)

    # IEND
    iend = _chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(signature + ihdr + idat + iend)


class MockComfyUIProvider(ComfyUIProvider):
    """
    Deterministic mock provider for testing the full generation pipeline
    without a real ComfyUI instance.
    """

    def __init__(self, output_base_dir: str | None = None):
        """
        Parameters
        ----------
        output_base_dir : str or None
            Base directory for writing placeholder output files.
            If None, uses ``<backend>/data/generated``.
        """
        if output_base_dir is None:
            output_base_dir = paths.generated_dir()
        self._output_dir = output_base_dir
        os.makedirs(self._output_dir, exist_ok=True)

        # Track submission times for status cycling.
        self._submissions: dict[str, float] = {}

    def _deterministic_prompt_id(self, job_id: str) -> str:
        """Generate a reproducible prompt_id from a job_id."""
        return "mock-" + hashlib.sha256(job_id.encode()).hexdigest()[:16]

    async def submit_job(self, workflow_payload: dict[str, Any], job_id: str) -> str:
        prompt_id = self._deterministic_prompt_id(job_id)
        self._submissions[prompt_id] = time.time()
        return prompt_id

    async def get_job_status(self, prompt_id: str) -> JobStatus:
        submit_time = self._submissions.get(prompt_id)
        if submit_time is None:
            return JobStatus(
                status=JobStatusEnum.FAILED,
                error_code="UNKNOWN_JOB",
                error_message=f"No submission record for prompt_id={prompt_id}",
            )

        elapsed = time.time() - submit_time

        # Deterministic state progression:
        #   0-1s  -> Queued
        #   1-3s  -> Running (progress ramps)
        #   3s+   -> Completed
        if elapsed < 1.0:
            return JobStatus(status=JobStatusEnum.QUEUED, progress=0.0)
        elif elapsed < 3.0:
            progress = min((elapsed - 1.0) / 2.0, 0.99)
            return JobStatus(status=JobStatusEnum.RUNNING, progress=progress)
        else:
            # Build output file paths
            output_path = os.path.join(self._output_dir, f"{prompt_id}_output.png")
            if not os.path.isfile(output_path):
                _create_placeholder_png(output_path)
            return JobStatus(
                status=JobStatusEnum.COMPLETED,
                progress=1.0,
                outputs=[{"file_path": output_path, "type": "image"}],
            )

    async def get_job_outputs(self, prompt_id: str) -> list[OutputFile]:
        output_path = os.path.join(self._output_dir, f"{prompt_id}_output.png")
        if not os.path.isfile(output_path):
            _create_placeholder_png(output_path)

        return [
            OutputFile(
                file_path=output_path,
                file_type="image",
                width=1,
                height=1,
                duration_sec=0.0,
                frame_rate=0.0,
                codec="png",
            )
        ]

    async def check_health(self) -> HealthStatus:
        return HealthStatus(
            online=True,
            mock=True,
            comfyui_version="mock-1.0.0",
            queue_remaining=0,
            gpu_info="Mock GPU (no real hardware)",
        )
