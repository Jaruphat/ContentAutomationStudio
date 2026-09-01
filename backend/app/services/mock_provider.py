"""
Deterministic Mock ComfyUI Provider.

Implements ComfyUIProvider for development and testing while the real H3
workflow JSON files are unavailable.

Behaviour:
  - prompt_ids are a pure function of the job_id, so a resubmitted job lands
    on the same id and the same output file.
  - Jobs cycle Queued -> Running -> Completed on a wall-clock schedule.
  - Outputs are real media files at the dimensions the shot actually asked
    for: a PNG for image shots, and an MP4 for video shots when FFmpeg is
    available. They are placeholders, not renders - nothing here pretends to
    be ComfyUI output.
  - Submission records are persisted to disk, so a job that was in flight when
    the app stopped can still be reconciled after a restart.
"""

import hashlib
import json
import logging
import os
import struct
import subprocess
import shutil
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

logger = logging.getLogger("cas.mock_provider")

# How long a mock job spends queued and running before completing. Kept short
# and overridable so the end-to-end script does not take minutes.
QUEUED_SEC = float(os.environ.get("CAS_MOCK_QUEUED_SEC", "1.0"))
RUNNING_SEC = float(os.environ.get("CAS_MOCK_RUNNING_SEC", "2.0"))

# Placeholder media is generated at a bounded size; a 1920x1080 raw PNG per
# take would make the mock flow needlessly slow and large on disk.
MAX_PLACEHOLDER_EDGE = 640


def _create_placeholder_png(path: str, width: int = 1, height: int = 1) -> None:
    """
    Write a minimal valid grayscale PNG of the requested size.

    Hand-rolled so the mock has no Pillow dependency.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    width = max(1, int(width))
    height = max(1, int(height))

    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_len = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return chunk_len + chunk_type + data + crc

    # IHDR: bit_depth=8, color_type=0 (grayscale), no interlace.
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))

    # A vertical gradient so different sizes are visually distinguishable.
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type: None
        value = 32 + int(180 * (y / max(1, height - 1))) if height > 1 else 128
        raw.extend(bytes([value]) * width)
    idat = _chunk(b"IDAT", zlib.compress(bytes(raw), 6))

    iend = _chunk(b"IEND", b"")

    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(signature + ihdr + idat + iend)
    os.replace(tmp, path)


def _scaled_dimensions(width: int, height: int) -> tuple[int, int]:
    """Clamp placeholder dimensions, preserving aspect ratio and evenness."""
    width = max(1, int(width or 1))
    height = max(1, int(height or 1))
    longest = max(width, height)
    if longest > MAX_PLACEHOLDER_EDGE:
        scale = MAX_PLACEHOLDER_EDGE / longest
        width = max(2, int(width * scale))
        height = max(2, int(height * scale))
    # H.264 needs even dimensions.
    return width - (width % 2), height - (height % 2)


def _create_placeholder_mp4(
    path: str, width: int, height: int, duration_sec: float, frame_rate: float
) -> bool:
    """
    Render a short placeholder MP4 with FFmpeg. Returns False if unavailable.

    Uses FFmpeg's own synthetic source, so no real media is required.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    width, height = _scaled_dimensions(width, height)
    duration_sec = max(0.1, float(duration_sec or 1.0))
    frame_rate = max(1.0, float(frame_rate or 24.0))
    tmp = path + ".tmp.mp4"

    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c=gray:s={width}x{height}:r={frame_rate:g}:d={duration_sec:g}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        tmp,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Placeholder MP4 generation failed: %s", exc)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False

    os.replace(tmp, path)
    return True


class MockComfyUIProvider(ComfyUIProvider):
    """
    Deterministic mock provider for exercising the full generation pipeline
    without a real ComfyUI instance.
    """

    # The mock never executes a graph, so it accepts either a mapped workflow
    # payload or bare logical values.
    requires_workflow_payload = False

    def __init__(self, output_base_dir: str | None = None):
        """
        Parameters
        ----------
        output_base_dir : str or None
            Base directory for writing placeholder output files.
            Defaults to the shared generated-media directory.
        """
        self._output_dir = output_base_dir or paths.generated_dir()
        os.makedirs(self._output_dir, exist_ok=True)
        self._index_path = os.path.join(self._output_dir, "mock_submissions.json")
        self._submissions: dict[str, dict[str, Any]] = self._load_index()

    # -- submission index -------------------------------------------------

    def _load_index(self) -> dict[str, dict[str, Any]]:
        """Load persisted submissions so in-flight jobs survive a restart."""
        if not os.path.isfile(self._index_path):
            return {}
        try:
            with open(self._index_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read mock submission index: %s", exc)
            return {}

    def _save_index(self) -> None:
        tmp = self._index_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._submissions, f, indent=2)
            os.replace(tmp, self._index_path)
        except OSError as exc:
            logger.warning("Could not persist mock submission index: %s", exc)

    def _deterministic_prompt_id(self, job_id: str) -> str:
        """Generate a reproducible prompt_id from a job_id."""
        return "mock-" + hashlib.sha256(job_id.encode()).hexdigest()[:16]

    # -- output description -----------------------------------------------

    @staticmethod
    def _describe_output(context: dict[str, Any] | None) -> dict[str, Any]:
        """Derive the shape of the placeholder media from the job context."""
        context = context or {}
        mode = str(context.get("generation_mode", "image"))
        width = int(context.get("width") or 1920)
        height = int(context.get("height") or 1080)
        frame_rate = float(context.get("frame_rate") or 24.0)
        duration = float(context.get("duration_sec") or 0.0)
        frames = context.get("frames")
        if duration <= 0 and frames:
            duration = float(frames) / frame_rate
        if duration <= 0:
            duration = 2.0
        return {
            "mode": mode,
            "width": width,
            "height": height,
            "frame_rate": frame_rate,
            "duration_sec": duration,
        }

    def _materialise(self, prompt_id: str) -> OutputFile:
        """Create (if needed) and describe the output file for a submission.

        The stored record is already normalised by ``_describe_output`` at
        submit time, so it is read directly here. Re-normalising it would look
        for a ``generation_mode`` key that normalisation has already renamed to
        ``mode``, quietly turning every video shot back into a still.
        """
        spec = self._submissions.get(prompt_id) or self._describe_output(None)
        width, height = _scaled_dimensions(
            spec.get("width", 1920), spec.get("height", 1080)
        )

        if spec.get("mode") in ("video", "image-to-video"):
            video_path = os.path.join(self._output_dir, f"{prompt_id}_output.mp4")
            if os.path.isfile(video_path) or _create_placeholder_mp4(
                video_path, width, height,
                spec.get("duration_sec", 2.0), spec.get("frame_rate", 24.0),
            ):
                return OutputFile(
                    file_path=video_path,
                    file_type="video",
                    width=width,
                    height=height,
                    duration_sec=spec.get("duration_sec", 2.0),
                    frame_rate=spec.get("frame_rate", 24.0),
                    codec="h264",
                )
            # FFmpeg unavailable: fall back to a still so the flow still runs.
            logger.info(
                "FFmpeg unavailable; emitting a still placeholder for video "
                "prompt %s", prompt_id,
            )

        image_path = os.path.join(self._output_dir, f"{prompt_id}_output.png")
        if not os.path.isfile(image_path):
            _create_placeholder_png(image_path, width, height)
        return OutputFile(
            file_path=image_path,
            file_type="image",
            width=width,
            height=height,
            duration_sec=0.0,
            frame_rate=0.0,
            codec="png",
        )

    # -- ComfyUIProvider --------------------------------------------------

    async def submit_job(
        self,
        workflow_payload: dict[str, Any],
        job_id: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        prompt_id = self._deterministic_prompt_id(job_id)
        record = self._describe_output(context)
        record["submitted_at"] = time.time()
        self._submissions[prompt_id] = record
        self._save_index()
        return prompt_id

    async def get_job_status(self, prompt_id: str) -> JobStatus:
        record = self._submissions.get(prompt_id)
        if record is None:
            return JobStatus(
                status=JobStatusEnum.FAILED,
                error_code="UNKNOWN_JOB",
                error_message=f"No submission record for prompt_id={prompt_id}",
            )

        elapsed = time.time() - float(record.get("submitted_at", 0.0))

        if elapsed < QUEUED_SEC:
            return JobStatus(status=JobStatusEnum.QUEUED, progress=0.0)

        if elapsed < QUEUED_SEC + RUNNING_SEC:
            progress = min((elapsed - QUEUED_SEC) / max(RUNNING_SEC, 0.001), 0.99)
            return JobStatus(status=JobStatusEnum.RUNNING, progress=progress)

        output = self._materialise(prompt_id)
        return JobStatus(
            status=JobStatusEnum.COMPLETED,
            progress=1.0,
            outputs=[{"file_path": output.file_path, "type": output.file_type}],
        )

    async def get_job_outputs(self, prompt_id: str) -> list[OutputFile]:
        return [self._materialise(prompt_id)]

    async def check_health(self) -> HealthStatus:
        return HealthStatus(
            online=True,
            mock=True,
            comfyui_version="mock-1.0.0",
            queue_remaining=0,
            gpu_info="Mock provider (no real hardware, no real generation)",
        )
