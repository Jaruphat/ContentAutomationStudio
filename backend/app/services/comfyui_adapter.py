"""
ComfyUI Adapter - Abstract base class.

Defines the interface that any ComfyUI provider (real or mock) must implement.
Business logic depends only on this interface, never on ComfyUI specifics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatusEnum(str, Enum):
    QUEUED = "Queued"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class JobStatus:
    """Status report for a single generation job."""

    status: JobStatusEnum
    progress: float = 0.0  # 0.0 to 1.0
    error_code: str | None = None
    error_message: str | None = None
    outputs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OutputFile:
    """Descriptor for a generated output file."""

    file_path: str
    file_type: str  # "image" or "video"
    width: int = 0
    height: int = 0
    duration_sec: float = 0.0
    frame_rate: float = 0.0
    codec: str = ""


@dataclass
class HealthStatus:
    """Health check result from a ComfyUI instance."""

    online: bool
    mock: bool = False
    comfyui_version: str = ""
    queue_remaining: int = 0
    gpu_info: str = ""
    error: str | None = None


class ComfyUIProvider(ABC):
    """
    Abstract interface for ComfyUI integration.

    Implementations must handle:
      - Submitting a workflow payload and receiving a prompt_id.
      - Polling for job status.
      - Retrieving output files once a job is complete.
      - Checking the health of the ComfyUI instance.
    """

    @abstractmethod
    async def submit_job(self, workflow_payload: dict[str, Any], job_id: str) -> str:
        """
        Submit a generation job to ComfyUI.

        Parameters
        ----------
        workflow_payload : dict
            Complete ComfyUI API-format workflow with parameters injected.
        job_id : str
            Internal job ID for correlation.

        Returns
        -------
        str
            The ComfyUI prompt_id assigned to the submitted job.
        """
        ...

    @abstractmethod
    async def get_job_status(self, prompt_id: str) -> JobStatus:
        """
        Query the current status of a submitted job.

        Parameters
        ----------
        prompt_id : str
            The ComfyUI prompt_id returned from submit_job.

        Returns
        -------
        JobStatus
            Current status with progress, errors, and any available outputs.
        """
        ...

    @abstractmethod
    async def get_job_outputs(self, prompt_id: str) -> list[OutputFile]:
        """
        Retrieve output files for a completed job.

        Parameters
        ----------
        prompt_id : str
            The ComfyUI prompt_id.

        Returns
        -------
        list[OutputFile]
            Descriptors for each generated file.
        """
        ...

    @abstractmethod
    async def check_health(self) -> HealthStatus:
        """
        Check whether the ComfyUI instance is reachable and healthy.

        Returns
        -------
        HealthStatus
            Health report including online flag and queue status.
        """
        ...
