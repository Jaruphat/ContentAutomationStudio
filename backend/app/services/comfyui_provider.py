"""
Real ComfyUI Provider.

Implements ComfyUIProvider for actual ComfyUI instances. Connects via HTTP
to the ComfyUI API for health checks, job submission, status polling, and
output retrieval.

Default behavior uses mock generation until real H3 workflow JSON files are
supplied. This provider handles only the transport layer; workflow parameter
injection is handled by the workflow_registry module.
"""

import logging
import os
from typing import Any

import httpx

from app import paths
from app.services.comfyui_adapter import (
    ComfyUIProvider,
    HealthStatus,
    JobStatus,
    JobStatusEnum,
    OutputFile,
)

logger = logging.getLogger("cas.comfyui_provider")

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8001"
HTTP_TIMEOUT = 10.0


class RealComfyUIProvider(ComfyUIProvider):
    """
    Real ComfyUI provider that communicates with a running ComfyUI instance.

    Supports health checks, job submission via /prompt, status polling via
    /history, and output retrieval. Uses httpx for async HTTP.
    """

    def __init__(self, base_url: str | None = None, output_base_dir: str | None = None):
        self._base_url = (base_url or os.environ.get("COMFYUI_URL", DEFAULT_COMFYUI_URL)).rstrip("/")
        if output_base_dir is None:
            output_base_dir = paths.generated_dir()
        self._output_dir = output_base_dir
        os.makedirs(self._output_dir, exist_ok=True)
        logger.info("RealComfyUIProvider initialized: %s", self._base_url)

    async def check_health(self) -> HealthStatus:
        """
        Check ComfyUI health by querying /system_stats and /object_info.

        Returns a HealthStatus with real system information when the instance
        is reachable, or an error status when it is not.
        """
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                # Query system stats
                stats_resp = await client.get(f"{self._base_url}/system_stats")
                stats_resp.raise_for_status()
                stats = stats_resp.json()

                # Extract system info
                system = stats.get("system", {})
                comfyui_version = system.get("comfyui_version", "unknown")

                # GPU info
                devices = stats.get("devices", [])
                gpu_info = ""
                if devices:
                    dev = devices[0]
                    gpu_name = dev.get("name", "unknown")
                    vram_total = dev.get("vram_total", 0)
                    vram_free = dev.get("vram_free", 0)
                    vram_total_gb = vram_total / (1024 ** 3)
                    vram_free_gb = vram_free / (1024 ** 3)
                    gpu_info = f"{gpu_name} ({vram_free_gb:.1f}/{vram_total_gb:.1f} GB VRAM free)"

                # Queue info
                queue_remaining = 0
                try:
                    queue_resp = await client.get(f"{self._base_url}/queue")
                    if queue_resp.status_code == 200:
                        queue_data = queue_resp.json()
                        running = queue_data.get("queue_running", [])
                        pending = queue_data.get("queue_pending", [])
                        queue_remaining = len(running) + len(pending)
                except Exception:
                    pass

                return HealthStatus(
                    online=True,
                    mock=False,
                    comfyui_version=comfyui_version,
                    queue_remaining=queue_remaining,
                    gpu_info=gpu_info,
                )

        except httpx.ConnectError:
            return HealthStatus(
                online=False,
                mock=False,
                error=f"Cannot connect to ComfyUI at {self._base_url}",
            )
        except httpx.TimeoutException:
            return HealthStatus(
                online=False,
                mock=False,
                error=f"Timeout connecting to ComfyUI at {self._base_url}",
            )
        except Exception as exc:
            return HealthStatus(
                online=False,
                mock=False,
                error=f"ComfyUI health check failed: {exc}",
            )

    async def submit_job(self, workflow_payload: dict[str, Any], job_id: str) -> str:
        """
        Submit a workflow to ComfyUI's /prompt endpoint.

        The workflow_payload should be a complete ComfyUI API-format workflow
        with all parameters already injected.

        Returns the prompt_id assigned by ComfyUI.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                body = {
                    "prompt": workflow_payload,
                    "client_id": f"cas-{job_id}",
                }
                resp = await client.post(f"{self._base_url}/prompt", json=body)
                resp.raise_for_status()
                data = resp.json()
                prompt_id = data.get("prompt_id")
                if not prompt_id:
                    raise ValueError(f"No prompt_id in ComfyUI response: {data}")
                logger.info("Submitted job %s -> prompt_id %s", job_id, prompt_id)
                return prompt_id

        except httpx.HTTPStatusError as exc:
            error_detail = exc.response.text[:500] if exc.response else str(exc)
            raise RuntimeError(
                f"ComfyUI rejected prompt submission: {exc.response.status_code} - {error_detail}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to submit job to ComfyUI: {exc}") from exc

    async def get_job_status(self, prompt_id: str) -> JobStatus:
        """
        Poll ComfyUI /history/{prompt_id} for job status.

        ComfyUI history returns completed jobs. If the prompt_id is not in
        history, we check /queue to determine if it's still running/pending.
        """
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                # Check history first (completed/failed jobs)
                hist_resp = await client.get(f"{self._base_url}/history/{prompt_id}")
                if hist_resp.status_code == 200:
                    hist_data = hist_resp.json()
                    if prompt_id in hist_data:
                        entry = hist_data[prompt_id]
                        status_info = entry.get("status", {})
                        status_str = status_info.get("status_str", "")
                        completed = status_info.get("completed", False)

                        if completed or status_str == "success":
                            outputs = entry.get("outputs", {})
                            return JobStatus(
                                status=JobStatusEnum.COMPLETED,
                                progress=1.0,
                                outputs=self._parse_history_outputs(outputs),
                            )
                        elif status_str == "error":
                            messages = status_info.get("messages", [])
                            error_msg = str(messages) if messages else "Unknown ComfyUI error"
                            return JobStatus(
                                status=JobStatusEnum.FAILED,
                                error_code="COMFYUI_ERROR",
                                error_message=error_msg[:1000],
                            )

                # Check queue (pending/running)
                queue_resp = await client.get(f"{self._base_url}/queue")
                if queue_resp.status_code == 200:
                    queue_data = queue_resp.json()

                    # Check running queue
                    for item in queue_data.get("queue_running", []):
                        if len(item) >= 2 and item[1] == prompt_id:
                            return JobStatus(
                                status=JobStatusEnum.RUNNING,
                                progress=0.5,
                            )

                    # Check pending queue
                    for item in queue_data.get("queue_pending", []):
                        if len(item) >= 2 and item[1] == prompt_id:
                            return JobStatus(
                                status=JobStatusEnum.QUEUED,
                                progress=0.0,
                            )

                # Not found anywhere - might still be processing
                return JobStatus(
                    status=JobStatusEnum.RUNNING,
                    progress=0.25,
                )

        except Exception as exc:
            logger.warning("Error polling job status for %s: %s", prompt_id, exc)
            return JobStatus(
                status=JobStatusEnum.FAILED,
                error_code="POLL_ERROR",
                error_message=str(exc)[:500],
            )

    def _parse_history_outputs(self, outputs: dict) -> list[dict[str, Any]]:
        """Parse ComfyUI history output format into our output list."""
        result: list[dict[str, Any]] = []
        for _node_id, node_output in outputs.items():
            images = node_output.get("images", [])
            for img in images:
                filename = img.get("filename", "")
                subfolder = img.get("subfolder", "")
                file_type = img.get("type", "output")
                result.append({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": file_type,
                })
            # Also check for video/gif outputs
            gifs = node_output.get("gifs", [])
            for gif in gifs:
                filename = gif.get("filename", "")
                subfolder = gif.get("subfolder", "")
                result.append({
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": "video",
                })
        return result

    async def get_job_outputs(self, prompt_id: str) -> list[OutputFile]:
        """
        Retrieve output files for a completed job.

        Downloads files from ComfyUI's /view endpoint and saves them locally.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get history to find output filenames
                hist_resp = await client.get(f"{self._base_url}/history/{prompt_id}")
                if hist_resp.status_code != 200:
                    return []

                hist_data = hist_resp.json()
                if prompt_id not in hist_data:
                    return []

                entry = hist_data[prompt_id]
                outputs_data = entry.get("outputs", {})
                result: list[OutputFile] = []

                for _node_id, node_output in outputs_data.items():
                    for img in node_output.get("images", []):
                        output_file = await self._download_output(
                            client, img, prompt_id, "image"
                        )
                        if output_file:
                            result.append(output_file)

                    for vid in node_output.get("gifs", []):
                        output_file = await self._download_output(
                            client, vid, prompt_id, "video"
                        )
                        if output_file:
                            result.append(output_file)

                return result

        except Exception as exc:
            logger.error("Error retrieving outputs for %s: %s", prompt_id, exc)
            return []

    async def _download_output(
        self,
        client: httpx.AsyncClient,
        file_info: dict,
        prompt_id: str,
        file_type: str,
    ) -> OutputFile | None:
        """Download a single output file from ComfyUI."""
        filename = file_info.get("filename", "")
        subfolder = file_info.get("subfolder", "")
        output_type = file_info.get("type", "output")

        if not filename:
            return None

        try:
            params = {
                "filename": filename,
                "subfolder": subfolder,
                "type": output_type,
            }
            resp = await client.get(f"{self._base_url}/view", params=params)
            resp.raise_for_status()

            # Save locally
            local_path = os.path.join(self._output_dir, f"{prompt_id}_{filename}")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(resp.content)

            # Determine dimensions from content-type or filename
            ext = os.path.splitext(filename)[1].lower()
            is_video = ext in (".mp4", ".webm", ".gif", ".avi")

            return OutputFile(
                file_path=local_path,
                file_type="video" if is_video else "image",
                width=0,
                height=0,
                duration_sec=0.0,
                frame_rate=0.0,
                codec=ext.lstrip("."),
            )

        except Exception as exc:
            logger.warning("Failed to download output %s: %s", filename, exc)
            return None
