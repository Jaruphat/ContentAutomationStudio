import base64
import os

import httpx
import pytest

from app.services.comfyui_adapter import JobStatusEnum
from app.services.openai_image_provider import OpenAIImageProvider


@pytest.mark.asyncio
async def test_openai_image_provider_downloads_b64_output_and_records_usage(tmp_path):
    png = b"\x89PNG\r\n\x1a\nmock"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/generations"
        body = __import__("json").loads(request.content)
        assert body["model"] == "gpt-image-1-mini"
        assert body["n"] == 1
        assert body["prompt"] == "a safe test image"
        return httpx.Response(
            200,
            json={
                "id": "img_test",
                "data": [{"b64_json": base64.b64encode(png).decode()}],
                "usage": {"input_tokens": 7, "output_tokens": 11},
            },
        )

    provider = OpenAIImageProvider(
        api_key="test-only",
        model="gpt-image-1-mini",
        output_base_dir=str(tmp_path),
        transport=httpx.MockTransport(handler),
    )
    prompt_id = await provider.submit_job(
        {"positive_prompt": "a safe test image", "width": 1024, "height": 1024},
        "job-1",
        context={"generation_mode": "image", "model": "gpt-image-1-mini"},
    )
    status = await provider.get_job_status(prompt_id)
    outputs = await provider.get_job_outputs(prompt_id)

    assert status.status == JobStatusEnum.COMPLETED
    assert len(outputs) == 1
    assert os.path.isfile(outputs[0].file_path)
    assert open(outputs[0].file_path, "rb").read() == png
    assert provider.get_provenance(prompt_id)["usage"] == {
        "input_tokens": 7,
        "output_tokens": 11,
    }


@pytest.mark.asyncio
async def test_openai_image_provider_requires_a_key(tmp_path):
    provider = OpenAIImageProvider(api_key="", output_base_dir=str(tmp_path))
    health = await provider.check_health()
    assert health.online is False
    assert "OPENAI_API_KEY" in (health.error or "")


@pytest.mark.asyncio
async def test_openai_image_provider_rejects_video_without_network(tmp_path):
    provider = OpenAIImageProvider(api_key="test-only", output_base_dir=str(tmp_path))
    with pytest.raises(ValueError, match="image shots"):
        await provider.submit_job({}, "job-1", context={"generation_mode": "video"})
