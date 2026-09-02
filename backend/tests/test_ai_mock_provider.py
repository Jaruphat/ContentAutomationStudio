"""
Tests for the deterministic offline AI provider.

Two properties matter and are both asserted here. It must be **usable with no
key, no network and no bill**, because the whole product is exercised through
it. And it must be **honest**: labelled as mock everywhere, with zero token
usage, never imitating a model's judgement.
"""

import json

import pytest

from app.services.ai.base import AIProviderError, StructuredRequest
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.prompts import (
    PROMPT_VERSIONS,
    SCENE_DECOMPOSITION_SYSTEM,
    build_scene_decomposition_prompt,
    build_shot_prompts_prompt,
)
from app.services.ai.task_schemas import SCHEMA_VERSIONS, TASK_SCHEMAS
from app.services.ai.validation import validate_against_schema

PROJECT = {
    "title": "Test Piece",
    "objective": "Show the product",
    "audience": "Creators",
    "content_type": "video",
    "aspect_ratio": "16:9",
    "target_resolution": "1920x1080",
    "target_duration_sec": 60,
    "frame_rate": 24,
    "language": "en",
}

PLOT = (
    "A courier leaves the depot at dawn. "
    "She crosses the flooded bridge. "
    "She arrives as the lights come on."
)


def decomposition_request(
    scene_count=3, min_shots=9, max_shots=15, plot=PLOT,
) -> StructuredRequest:
    return StructuredRequest(
        task="scene_decomposition",
        system_prompt=SCENE_DECOMPOSITION_SYSTEM,
        user_prompt=build_scene_decomposition_prompt(
            PROJECT, "A brief.", plot, [], [], [],
            scene_count, min_shots, max_shots,
        ),
        schema_name="scene_decomposition",
        json_schema=TASK_SCHEMAS["scene_decomposition"],
        prompt_version=PROMPT_VERSIONS["scene_decomposition"],
        schema_version=SCHEMA_VERSIONS["scene_decomposition"],
    )


# ---------------------------------------------------------------------------
# Usable without configuration
# ---------------------------------------------------------------------------

def test_the_mock_needs_no_key():
    provider = MockAIProvider()
    assert provider.api_key_env == ""
    assert provider.is_configured() is True
    # Must not raise: this is what makes the product usable out of the box.
    provider.require_configured()


def test_the_mock_needs_no_network():
    assert MockAIProvider.requires_network is False


@pytest.mark.asyncio
async def test_health_is_online_and_labelled_mock():
    health = await MockAIProvider().check_health()
    assert health.configured is True
    assert health.online is True
    assert health.mock is True
    assert health.models == ["cas-mock-1"]


# ---------------------------------------------------------------------------
# Honesty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_token_usage_is_reported():
    """A plausible token count in a provenance record would be a small lie."""
    result = await MockAIProvider().complete_structured(decomposition_request())
    assert result.usage.as_dict() == {
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    }


@pytest.mark.asyncio
async def test_the_output_says_it_was_not_authored():
    result = await MockAIProvider().complete_structured(decomposition_request())
    assert "deterministic mock" in result.data["notes"].lower()


@pytest.mark.asyncio
async def test_characters_and_locations_are_left_empty_not_invented():
    request = StructuredRequest(
        task="story_bible",
        system_prompt="s",
        user_prompt="CREATIVE BRIEF\nA courier story.\n\nPLOT\n" + PLOT,
        schema_name="story_bible",
        json_schema=TASK_SCHEMAS["story_bible"],
        prompt_version="1.0",
        schema_version="1.0",
    )
    result = await MockAIProvider().complete_structured(request)

    assert result.data["characters"] == []
    assert result.data["locations"] == []
    assert "not invented" in result.data["notes"] or "rather than invented" in result.data["notes"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_same_input_gives_the_same_output():
    """No clock, no randomness, no counters."""
    first = await MockAIProvider().complete_structured(decomposition_request())
    second = await MockAIProvider().complete_structured(decomposition_request())
    assert first.data == second.data


@pytest.mark.asyncio
async def test_a_different_plot_gives_a_different_result():
    """Output is derived from the input, not a fixed canned blob."""
    base = await MockAIProvider().complete_structured(decomposition_request())
    other = await MockAIProvider().complete_structured(
        decomposition_request(plot="A lighthouse keeper repaints the lantern.")
    )
    assert base.data != other.data


# ---------------------------------------------------------------------------
# Schema conformance and requested structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_decomposition_validates_against_its_schema():
    result = await MockAIProvider().complete_structured(decomposition_request())
    # complete_structured already validated; re-check to pin the contract.
    validate_against_schema(
        json.dumps(result.data), TASK_SCHEMAS["scene_decomposition"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scene_count,min_shots,max_shots", [
    (1, 1, 3),
    (3, 9, 15),
    (5, 10, 20),
    (2, 6, 6),
])
async def test_the_requested_structure_is_honoured(
    scene_count, min_shots, max_shots
):
    """The mock reads the structure back out of the rendered prompt, exactly
    as a real provider would - it gets no privileged access to the request."""
    result = await MockAIProvider().complete_structured(
        decomposition_request(scene_count, min_shots, max_shots)
    )
    scenes = result.data["scenes"]

    assert len(scenes) == scene_count
    total_shots = sum(len(s["shots"]) for s in scenes)
    assert min_shots <= total_shots <= max_shots


@pytest.mark.asyncio
async def test_scenes_and_shots_are_numbered_from_zero():
    result = await MockAIProvider().complete_structured(decomposition_request())
    scenes = result.data["scenes"]

    assert [s["order"] for s in scenes] == list(range(len(scenes)))
    for scene in scenes:
        assert [s["order"] for s in scene["shots"]] == list(
            range(len(scene["shots"]))
        )


@pytest.mark.asyncio
async def test_still_shots_carry_no_motion_prompt():
    result = await MockAIProvider().complete_structured(decomposition_request())
    for scene in result.data["scenes"]:
        for shot in scene["shots"]:
            if shot["generation_mode"] == "image":
                assert shot["video_prompt"] == ""


@pytest.mark.asyncio
async def test_the_plot_reaches_the_generated_shots():
    result = await MockAIProvider().complete_structured(decomposition_request())
    text = json.dumps(result.data)
    assert "courier" in text or "depot" in text


# ---------------------------------------------------------------------------
# Prompt compilation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_compilation_echoes_the_requested_shot_ids():
    shots = [
        {
            "id": f"shot-{index}", "order": index, "shot_type": "wide",
            "camera_angle": "eye level", "camera_movement": "static",
            "lens_framing": "35mm", "subject": f"Subject {index}",
            "action": "walks", "environment": "street", "dialogue": "",
            "planned_duration_sec": 4.0, "generation_mode": "image",
            "scene_title": "One", "scene_summary": "Summary",
            "scene_time_of_day": "dawn", "scene_emotional_beat": "calm",
        }
        for index in range(3)
    ]
    request = StructuredRequest(
        task="shot_prompts",
        system_prompt="s",
        user_prompt=build_shot_prompts_prompt(PROJECT, shots, [], [], []),
        schema_name="shot_prompts",
        json_schema=TASK_SCHEMAS["shot_prompts"],
        prompt_version="1.0",
        schema_version="1.0",
    )

    result = await MockAIProvider().complete_structured(request)

    assert [p["shot_id"] for p in result.data["prompts"]] == [
        "shot-0", "shot-1", "shot-2",
    ]
    assert all(p["image_prompt"] for p in result.data["prompts"])


# ---------------------------------------------------------------------------
# Unsupported tasks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_unknown_task_is_refused_rather_than_faked():
    request = StructuredRequest(
        task="invent_a_soundtrack",
        system_prompt="s",
        user_prompt="u",
        schema_name="unknown",
        json_schema={"type": "object", "properties": {},
                     "required": [], "additionalProperties": False},
        prompt_version="1.0",
        schema_version="1.0",
    )
    with pytest.raises(AIProviderError) as excinfo:
        await MockAIProvider().complete_structured(request)
    assert excinfo.value.category == "bad_request"
