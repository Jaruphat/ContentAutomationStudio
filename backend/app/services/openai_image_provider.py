"""OpenAI Images adapter: one paid still per job, downloaded locally.

Implements the same :class:`~app.services.comfyui_adapter.MediaProvider`
interface as the ComfyUI adapters, so review, approval, the timeline manifest
and the FFmpeg render treat an OpenAI still exactly like a locally generated
one.

Two rules shape this file:

* **The key is configuration, never data.** It is read from the environment at
  construction time. No job payload, request body or workflow can carry one,
  and no error message, log line or return value contains one - vendor errors
  are replaced with a sanitised sentence describing the class of failure and
  what to do about it.
* **Nothing is reported as generated until the bytes are on disk.** The image
  is written to the project-local generated directory through a temp-and-rename
  so an interrupted download cannot leave a truncated file that later reads as
  a valid take.
"""

import base64
from contextlib import ExitStack
import logging
import os
from typing import Any

import httpx

from app import paths
from app.services import media_providers
from app.services.comfyui_adapter import (
    HealthStatus,
    JobStatus,
    JobStatusEnum,
    MediaProvider,
    OutputFile,
)
from app.services.job_payload import HEIGHT, NEGATIVE_PROMPT, POSITIVE_PROMPT, WIDTH

logger = logging.getLogger("cas.openai_image")

DEFAULT_MODEL = media_providers.DEFAULT_IMAGE_MODEL
DEFAULT_BASE_URL = "https://api.openai.com/v1"

#: How many characters of a vendor error body may be surfaced. The body can
#: echo request content, so only the status class is used for the message and
#: this cap exists for the debug log alone.
_LOG_EXCERPT = 200


class OpenAIImageProvider(MediaProvider):
    """Generate one still per job through OpenAI's Images API."""

    #: No ComfyUI graph is involved, so the queue passes the job's logical
    #: values straight through instead of building a node-mapped payload.
    requires_workflow_payload = False
    max_reference_images = None

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        output_base_dir: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._api_key = (
            api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        ).strip()
        self._model = model or media_providers.default_image_model()
        self._base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self._output_dir = output_base_dir or paths.generated_dir()
        self._transport = transport
        self._jobs: dict[str, dict[str, Any]] = {}
        os.makedirs(self._output_dir, exist_ok=True)

    # -- helpers ---------------------------------------------------------

    @property
    def configured(self) -> bool:
        """Whether a key was supplied. Never exposes the key itself."""
        return bool(self._api_key)

    def _client(self, timeout: float = 120.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=timeout,
            transport=self._transport,
        )

    @staticmethod
    def _prompt_from(payload: dict[str, Any]) -> str:
        """The positive prompt, under either the logical or a plain key."""
        for key in (POSITIVE_PROMPT, "positive_prompt", "prompt"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _sanitised_http_error(status: int) -> str:
        if status == 401:
            return (
                "OpenAI Images rejected the credential. Check OPENAI_API_KEY in "
                "your local .env and restart the backend."
            )
        if status == 403:
            return (
                "OpenAI Images refused this request for the configured account "
                "(permission or region). Nothing was generated."
            )
        if status == 429:
            return (
                "OpenAI Images rate limit or quota was reached. Wait and retry, "
                "or check the billing limits on the account."
            )
        if status == 400:
            return (
                "OpenAI Images rejected the request as invalid - most often a "
                "prompt blocked by the content filter, or an unsupported size."
            )
        if status >= 500:
            return "OpenAI Images is temporarily unavailable. Retry shortly."
        return f"OpenAI Images rejected the request (HTTP {status})."

    # -- MediaProvider ---------------------------------------------------

    async def submit_job(
        self,
        workflow_payload: dict[str, Any],
        job_id: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate and download one image; return its correlation id.

        The Images API is synchronous, so the image already exists by the time
        this returns and :meth:`get_job_status` only reports what happened.
        """
        context = context or {}
        if context.get("generation_mode", "image") != "image":
            raise ValueError(
                "OpenAI Images can only generate image shots; video and "
                "image-to-video stay on ComfyUI H3."
            )
        if not self._api_key:
            raise RuntimeError(
                "OpenAI Images is not configured. Set OPENAI_API_KEY in your "
                "local .env and restart the backend."
            )

        prompt = self._prompt_from(workflow_payload)
        if not prompt:
            raise ValueError(
                "OpenAI Images requires a non-empty image prompt. Compile the "
                "shot's prompt before generating."
            )

        model = str(context.get("model") or self._model)
        size = str(
            context.get("size")
            or media_providers.normalise_size(
                workflow_payload.get(WIDTH) or context.get("width"),
                workflow_payload.get(HEIGHT) or context.get("height"),
            )
        )
        quality = str(context.get("quality") or media_providers.DEFAULT_IMAGE_QUALITY)

        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
        }
        negative = str(workflow_payload.get(NEGATIVE_PROMPT) or "").strip()
        if negative:
            # The Images API has no negative-prompt field, so the constraint is
            # folded into the prompt rather than silently dropped.
            payload["prompt"] = f"{prompt}\n\nAvoid: {negative}"

        reference_inputs = [
            dict(item)
            for item in (context.get("reference_inputs") or [])
            if isinstance(item, dict)
        ]
        for item in reference_inputs:
            path = str(item.get("file_path") or "")
            if not path or not os.path.isfile(path):
                raise ValueError(
                    "A reference image selected for this job is missing from disk."
                )

        try:
            async with self._client() as client:
                if reference_inputs:
                    with ExitStack() as stack:
                        files = [
                            (
                                "image[]",
                                (
                                    os.path.basename(str(item["file_path"])),
                                    stack.enter_context(open(str(item["file_path"]), "rb")),
                                    str(item.get("mime_type") or "image/png"),
                                ),
                            )
                            for item in reference_inputs
                        ]
                        response = await client.post(
                            "/images/edits",
                            data={key: str(value) for key, value in payload.items()},
                            files=files,
                        )
                else:
                    response = await client.post("/images/generations", json=payload)
                response.raise_for_status()
                data = response.json()
                items = data.get("data") or []
                if not items:
                    raise RuntimeError("OpenAI Images returned no image data.")
                item = items[0]
                if item.get("b64_json"):
                    content = base64.b64decode(item["b64_json"], validate=True)
                elif item.get("url"):
                    download = await client.get(item["url"])
                    download.raise_for_status()
                    content = download.content
                else:
                    raise RuntimeError(
                        "OpenAI Images returned no downloadable image."
                    )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning(
                "OpenAI Images HTTP %s for job %s: %s",
                status, job_id, exc.response.text[:_LOG_EXCERPT],
            )
            raise RuntimeError(self._sanitised_http_error(status)) from exc
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise RuntimeError(
                "Could not reach OpenAI Images; no image was created."
            ) from exc

        response_id = str(data.get("id") or f"openai-{job_id}")
        # Used as a filename, so it is reduced to characters that are safe on
        # Windows and POSIX alike before it touches the filesystem.
        safe_id = "".join(c for c in response_id if c.isalnum() or c in "-_")[:80]
        local_path = os.path.join(self._output_dir, f"{safe_id or job_id}.png")
        tmp = local_path + ".tmp"
        with open(tmp, "wb") as file:
            file.write(content)
        os.replace(tmp, local_path)

        width, height = (int(part) for part in size.split("x"))
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        estimate = media_providers.estimate_image_cost(
            media_providers.OPENAI, model, size, quality, count=1
        )

        self._jobs[response_id] = {
            "output": OutputFile(
                file_path=local_path,
                file_type="image",
                width=width,
                height=height,
                codec="png",
            ),
            "provenance": {
                "provider_id": media_providers.OPENAI,
                "model": model,
                "response_id": response_id,
                "request_params": {
                    "size": size,
                    "quality": quality,
                    "n": 1,
                    "negative_prompt_folded_in": bool(negative),
                    "reference_image_ids": [
                        str(item.get("image_id") or "") for item in reference_inputs
                    ],
                },
                "usage": usage,
                "estimated_cost_usd": estimate.amount_usd,
                "cost_basis": estimate.basis,
                "downloaded_to": local_path,
            },
        }
        logger.info(
            "OpenAI image for job %s stored locally (%s, %s)", job_id, size, quality
        )
        return response_id

    async def get_job_status(self, prompt_id: str) -> JobStatus:
        if prompt_id not in self._jobs:
            return JobStatus(
                status=JobStatusEnum.FAILED,
                error_code="UNKNOWN_JOB",
                error_message=(
                    "This OpenAI image job is not held in memory any more - the "
                    "backend restarted after it was submitted. Retry the job."
                ),
            )
        return JobStatus(status=JobStatusEnum.COMPLETED, progress=1.0)

    async def submission_exists(self, prompt_id: str) -> bool | None:
        """``True`` while held in memory; never ``False``.

        The Images API bills on the request, and a submitted job that this
        process no longer remembers may well have produced - and charged for -
        an image. Reporting that as "the provider does not have it" would let
        the queue generate and pay for it a second time, so an id this process
        has forgotten is unknown, not absent.
        """
        return True if prompt_id in self._jobs else None

    async def get_job_outputs(self, prompt_id: str) -> list[OutputFile]:
        record = self._jobs.get(prompt_id)
        return [record["output"]] if record else []

    def get_provenance(self, prompt_id: str) -> dict[str, Any]:
        record = self._jobs.get(prompt_id)
        return dict(record["provenance"]) if record else {}

    async def check_health(self) -> HealthStatus:
        """Ask whether the configured model is reachable for this account.

        Retrieving a model description is a free metadata call - it never
        generates an image, so a health check cannot produce a charge.
        """
        if not self._api_key:
            return HealthStatus(
                online=False,
                error=(
                    "OPENAI_API_KEY is not configured, so OpenAI Images cannot "
                    "be used. Add it to your local .env and restart."
                ),
            )
        try:
            async with self._client(timeout=10.0) as client:
                response = await client.get(f"/models/{self._model}")
                response.raise_for_status()
            return HealthStatus(online=True, comfyui_version=self._model)
        except httpx.HTTPStatusError as exc:
            return HealthStatus(
                online=False,
                error=(
                    "OpenAI Images health check failed: "
                    + self._sanitised_http_error(exc.response.status_code)
                ),
            )
        except Exception:
            return HealthStatus(
                online=False,
                error=(
                    "OpenAI Images health check could not reach the service. "
                    "Check this machine's network access."
                ),
            )
