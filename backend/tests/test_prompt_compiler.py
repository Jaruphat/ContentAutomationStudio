"""
Tests for the prompt compiler service.

Validates layered prompt compilation from Story Bible entities (characters,
locations, styles) combined with scene context and shot data.
"""

import pytest

from app.services.prompt_compiler import CompiledPrompt, compile_prompt


class TestCompilePromptFullData:
    """Test compile_prompt with complete data across all layers."""

    @pytest.fixture()
    def full_shot(self):
        return {
            "shot_type": "wide shot",
            "camera_angle": "eye level",
            "camera_movement": "slow dolly in",
            "lens_framing": "35mm",
            "subject": "Alice",
            "action": "walking into the clearing",
            "environment": "sunlit forest",
            "generation_mode": "image",
            "image_prompt": "masterpiece, best quality",
            "video_prompt": "smooth motion",
            "negative_prompt": "ugly, deformed",
        }

    @pytest.fixture()
    def full_scene(self):
        return {
            "summary": "Alice enters the forest clearing",
            "emotional_beat": "wonder and discovery",
            "time_of_day": "golden hour",
            "character_ids": ["char-1"],
            "location_id": "loc-1",
        }

    @pytest.fixture()
    def full_characters(self):
        return [
            {
                "id": "char-1",
                "name": "Alice",
                "appearance": "tall, brown hair",
                "clothing": "red dress",
                "color_palette": "warm tones",
                "prompt_tokens": "1girl, brown hair, red dress",
            }
        ]

    @pytest.fixture()
    def full_locations(self):
        return [
            {
                "id": "loc-1",
                "name": "Forest Clearing",
                "description": "A sunlit clearing",
                "geography": "temperate forest",
                "time_of_day": "golden hour",
                "palette": "greens and golds",
                "lighting": "dappled sunlight",
                "props": "fallen logs",
            }
        ]

    @pytest.fixture()
    def full_styles(self):
        return [
            {
                "medium": "digital painting",
                "genre": "fantasy",
                "visual_keywords": "ethereal, luminous",
                "camera_language": "cinematic",
                "palette": "warm sunset palette",
                "lighting_rules": "volumetric lighting",
                "negative_constraints": "blurry, low quality",
            }
        ]

    def test_returns_compiled_prompt(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert isinstance(result, CompiledPrompt)

    def test_positive_prompt_is_nonempty(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert len(result.positive_prompt) > 0

    def test_positive_prompt_contains_style(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "digital painting" in result.positive_prompt
        assert "fantasy" in result.positive_prompt

    def test_positive_prompt_contains_character(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "Alice" in result.positive_prompt
        assert "brown hair" in result.positive_prompt

    def test_positive_prompt_contains_location(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "Forest Clearing" in result.positive_prompt
        assert "temperate forest" in result.positive_prompt

    def test_positive_prompt_contains_scene_context(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "Alice enters the forest clearing" in result.positive_prompt
        assert "wonder and discovery" in result.positive_prompt

    def test_positive_prompt_contains_shot_camera(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "wide shot" in result.positive_prompt
        assert "slow dolly in" in result.positive_prompt

    def test_positive_prompt_contains_action(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "walking into the clearing" in result.positive_prompt

    def test_positive_prompt_contains_technical_tokens(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        # generation_mode is "image" so image_prompt should be used
        assert "masterpiece" in result.positive_prompt
        assert "best quality" in result.positive_prompt

    def test_negative_prompt_contains_shot_negative(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "ugly" in result.negative_prompt
        assert "deformed" in result.negative_prompt

    def test_negative_prompt_contains_style_constraints(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "blurry" in result.negative_prompt
        assert "low quality" in result.negative_prompt

    def test_layers_dict_is_populated(
        self, full_shot, full_scene, full_characters, full_locations, full_styles
    ):
        result = compile_prompt(
            shot=full_shot,
            scene=full_scene,
            characters=full_characters,
            locations=full_locations,
            styles=full_styles,
        )
        assert "global_style" in result.layers
        assert "character_constraints" in result.layers
        assert "location_constraints" in result.layers
        assert "scene_context" in result.layers
        assert "shot_camera" in result.layers
        assert "action_expression" in result.layers
        assert "technical_tokens" in result.layers
        assert "negative_prompt" in result.layers


class TestCompilePromptMinimalData:
    """Test compile_prompt with minimal / empty inputs."""

    def test_empty_inputs(self):
        result = compile_prompt(
            shot={},
            scene={},
            characters=[],
            locations=[],
            styles=[],
        )
        assert isinstance(result, CompiledPrompt)
        assert result.positive_prompt == ""
        assert result.negative_prompt == ""

    def test_shot_only(self):
        result = compile_prompt(
            shot={
                "shot_type": "close-up",
                "subject": "a flower",
                "generation_mode": "image",
                "image_prompt": "macro photography",
            },
            scene={},
            characters=[],
            locations=[],
            styles=[],
        )
        assert "close-up" in result.positive_prompt
        assert "a flower" in result.positive_prompt
        assert "macro photography" in result.positive_prompt

    def test_no_negative_prompt_when_empty(self):
        result = compile_prompt(
            shot={"shot_type": "wide"},
            scene={},
            characters=[],
            locations=[],
            styles=[],
        )
        assert result.negative_prompt == ""


class TestCompilePromptNegativePrompt:
    """Test negative prompt assembly from shot and style layers."""

    def test_only_shot_negative(self):
        result = compile_prompt(
            shot={"negative_prompt": "bad anatomy"},
            scene={},
            characters=[],
            locations=[],
            styles=[],
        )
        assert result.negative_prompt == "bad anatomy"

    def test_only_style_negative(self):
        result = compile_prompt(
            shot={},
            scene={},
            characters=[],
            locations=[],
            styles=[{"negative_constraints": "watermark, text"}],
        )
        assert result.negative_prompt == "watermark, text"

    def test_combined_negatives(self):
        result = compile_prompt(
            shot={"negative_prompt": "ugly"},
            scene={},
            characters=[],
            locations=[],
            styles=[
                {"negative_constraints": "blurry"},
                {"negative_constraints": "low quality"},
            ],
        )
        assert "ugly" in result.negative_prompt
        assert "blurry" in result.negative_prompt
        assert "low quality" in result.negative_prompt

    def test_multiple_styles_negatives_joined(self):
        result = compile_prompt(
            shot={},
            scene={},
            characters=[],
            locations=[],
            styles=[
                {"negative_constraints": "noise"},
                {"negative_constraints": "artifacts"},
            ],
        )
        assert "noise" in result.negative_prompt
        assert "artifacts" in result.negative_prompt

    def test_repeated_positive_and_negative_fragments_are_deduplicated(self):
        result = compile_prompt(
            shot={
                "subject": "white boat",
                "image_prompt": "rain, WHITE BOAT, wet street, rain",
                "negative_prompt": "text, watermark, text",
            },
            scene={},
            characters=[],
            locations=[],
            styles=[{"negative_constraints": "watermark, blur"}],
        )

        assert result.positive_prompt == "white boat, rain, wet street"
        assert result.negative_prompt == "text, watermark, blur"


class TestCompilePromptLayerIsolation:
    """Test that layers are isolated and independently populated."""

    def test_character_filter_by_scene_ids(self):
        """Characters not in scene.character_ids should be excluded."""
        result = compile_prompt(
            shot={},
            scene={"character_ids": ["char-1"]},
            characters=[
                {"id": "char-1", "name": "Alice"},
                {"id": "char-2", "name": "Bob"},
            ],
            locations=[],
            styles=[],
        )
        assert "Alice" in result.layers["character_constraints"]
        assert "Bob" not in result.layers["character_constraints"]

    def test_all_characters_included_when_no_filter(self):
        """When scene has no character_ids, all characters should be included."""
        result = compile_prompt(
            shot={},
            scene={},
            characters=[
                {"id": "char-1", "name": "Alice"},
                {"id": "char-2", "name": "Bob"},
            ],
            locations=[],
            styles=[],
        )
        assert "Alice" in result.layers["character_constraints"]
        assert "Bob" in result.layers["character_constraints"]

    def test_location_filter_by_scene_location_id(self):
        """Only the location matching scene.location_id should be included."""
        result = compile_prompt(
            shot={},
            scene={"location_id": "loc-1"},
            characters=[],
            locations=[
                {"id": "loc-1", "name": "Forest"},
                {"id": "loc-2", "name": "City"},
            ],
            styles=[],
        )
        assert "Forest" in result.layers["location_constraints"]
        assert "City" not in result.layers["location_constraints"]

    def test_all_locations_when_no_filter(self):
        """When scene has no location_id, all locations should be included."""
        result = compile_prompt(
            shot={},
            scene={},
            characters=[],
            locations=[
                {"id": "loc-1", "name": "Forest"},
                {"id": "loc-2", "name": "City"},
            ],
            styles=[],
        )
        assert "Forest" in result.layers["location_constraints"]
        assert "City" in result.layers["location_constraints"]

    def test_video_mode_uses_video_prompt(self):
        """When generation_mode is 'video', video_prompt should be used for technical tokens."""
        result = compile_prompt(
            shot={
                "generation_mode": "video",
                "image_prompt": "still image tokens",
                "video_prompt": "smooth motion tokens",
            },
            scene={},
            characters=[],
            locations=[],
            styles=[],
        )
        assert result.layers["technical_tokens"] == "smooth motion tokens"

    def test_image_mode_uses_image_prompt(self):
        """When generation_mode is 'image', image_prompt should be used."""
        result = compile_prompt(
            shot={
                "generation_mode": "image",
                "image_prompt": "still image tokens",
                "video_prompt": "smooth motion tokens",
            },
            scene={},
            characters=[],
            locations=[],
            styles=[],
        )
        assert result.layers["technical_tokens"] == "still image tokens"

    def test_multiple_styles_merged(self):
        """Multiple style records should all be merged into global_style."""
        result = compile_prompt(
            shot={},
            scene={},
            characters=[],
            locations=[],
            styles=[
                {"medium": "oil painting", "genre": "impressionism"},
                {"medium": "digital art", "genre": "sci-fi"},
            ],
        )
        assert "oil painting" in result.layers["global_style"]
        assert "digital art" in result.layers["global_style"]
