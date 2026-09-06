"""
Deterministic offline AI provider.

Exists for the same reason the mock ComfyUI provider does: the rest of the
product must be exercisable end to end without a key, a network or a bill, and
the test suite must not depend on a vendor's mood. It is honest about what it
is - ``mock: true`` in every health report and every provenance record - and it
never imitates a model's judgement.

What it returns is mechanically derived from the input: scenes get their beats
from the plot's sentences, shots cycle through a fixed grammar of framings, and
prompts are the same layered concatenation the deterministic prompt compiler
already performs. The output is schema-valid and structurally sane, which is
what the pipeline downstream needs, and obviously not authored, which is what
a reviewer needs.

Same input, same output, always: no clock, no randomness, no counters.
"""

import re
from typing import Any

from app.services.ai.base import (
    AIModelInfo,
    AIProvider,
    AIProviderError,
    AIProviderHealth,
    StructuredRequest,
    TokenUsage,
)

import json

#: Cycled through so a storyboard has visual variety without inventing intent.
_FRAMINGS = [
    ("wide establishing shot", "eye level", "slow push in", "24mm, deep focus"),
    ("medium shot", "eye level", "static", "50mm, moderate depth of field"),
    ("close-up", "slight low angle", "slow handheld drift", "85mm, shallow depth of field"),
    ("over-the-shoulder shot", "eye level", "static", "50mm, shallow depth of field"),
    ("wide shot", "high angle", "slow pan right", "35mm, deep focus"),
]


def _sentences(text: str) -> list[str]:
    """Split prose into sentences, dropping empties."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p.strip()]


class MockAIProvider(AIProvider):
    """Offline stand-in with no vendor behind it."""

    id = "mock"
    label = "Deterministic mock (offline)"
    api_key_env = ""
    default_model = "cas-mock-1"
    requires_network = False
    catalogue = (
        AIModelInfo(
            "cas-mock-1", "Deterministic mock",
            note="No model runs. Output is derived mechanically from the input.",
        ),
    )

    async def _complete_once(
        self, request: StructuredRequest
    ) -> tuple[str, str, TokenUsage, str]:
        builders = {
            "scene_decomposition": self._scenes,
            "story_bible": self._bible,
            "shot_prompts": self._prompts,
        }
        builder = builders.get(request.task)
        if builder is None:
            raise AIProviderError(
                "bad_request",
                f"The mock AI provider has no deterministic output for task "
                f"'{request.task}'.",
            )
        payload = builder(request)
        text = json.dumps(payload, ensure_ascii=False)
        # Reported as 0: nothing was metered, and a plausible-looking token
        # count in a provenance record would be a small lie.
        return text, self.default_model, TokenUsage(), ""

    # -- task builders ------------------------------------------------------

    def _scenes(self, request: StructuredRequest) -> dict[str, Any]:
        scene_count, min_shots, max_shots = _structure_from_prompt(request.user_prompt)
        beats = _sentences(_section(request.user_prompt, "PLOT")) or [
            "The story unfolds."
        ]
        shots_per_scene = max(1, round(((min_shots + max_shots) / 2) / scene_count))

        scenes = []
        shot_total = 0
        for scene_index in range(scene_count):
            beat = beats[scene_index % len(beats)]
            count = shots_per_scene
            # Keep the total inside the requested band even when it does not
            # divide evenly.
            if scene_index == scene_count - 1:
                count = max(1, min(max_shots - shot_total, max(count, min_shots - shot_total)))
            shots = []
            for shot_index in range(count):
                shot_type, angle, movement, lens = _FRAMINGS[
                    (scene_index + shot_index) % len(_FRAMINGS)
                ]
                shots.append({
                    "order": shot_index,
                    "shot_type": shot_type,
                    "camera_angle": angle,
                    "camera_movement": movement,
                    "lens_framing": lens,
                    "subject": f"Scene {scene_index + 1} subject",
                    "action": beat,
                    "environment": "The setting described in the brief",
                    "dialogue": "",
                    "planned_duration_sec": 5.0,
                    "generation_mode": "video" if shot_index % 2 else "image",
                    "image_prompt": f"{shot_type}, {lens}, {beat}",
                    # Left empty on purpose: the motion pair replaces it, and a
                    # mock that still filled it would let a regression in the
                    # real path pass unnoticed.
                    "video_prompt": "",
                    # What happens leads, the camera qualifies, the sound comes
                    # last. A mock that omits a required property is a schema
                    # nobody is checking.
                    "subject_motion": (
                        f"{beat} The subject moves through frame."
                        if shot_index % 2 else ""
                    ),
                    "camera_motion": movement if shot_index % 2 else "",
                    "audio_direction": (
                        "room tone and distant traffic" if shot_index % 2 else ""
                    ),
                    "emphasis_text": "",
                    "negative_prompt": "text overlays, watermarks",
                })
            shot_total += len(shots)
            scenes.append({
                "order": scene_index,
                "title": f"Scene {scene_index + 1}",
                "purpose": "Deterministic placeholder scene.",
                "summary": beat,
                "time_of_day": "day",
                "emotional_beat": "steady",
                "planned_duration_sec": float(len(shots) * 5),
                "character_names": [],
                "location_name": "",
                "shots": shots,
            })

        return {
            "scenes": scenes,
            "notes": (
                "Generated by the deterministic mock provider. No language "
                "model was called; these scenes restate the plot's sentences "
                "against a fixed shot grammar."
            ),
        }

    def _bible(self, request: StructuredRequest) -> dict[str, Any]:
        return {
            "characters": [],
            "locations": [],
            "style": {
                "medium": "live-action cinematography",
                "genre": "",
                "visual_keywords": "natural light, grounded, filmic",
                "camera_language": "steady framing, minimal movement",
                "palette": "",
                "lighting_rules": "motivated practical light",
                "negative_constraints": "text overlays, watermarks, distorted hands",
            },
            "notes": (
                "Generated by the deterministic mock provider. Characters and "
                "locations are left empty rather than invented offline."
            ),
        }

    def _prompts(self, request: StructuredRequest) -> dict[str, Any]:
        prompts = []
        for shot_id, line in _shot_lines(request.user_prompt):
            prompts.append({
                "shot_id": shot_id,
                "image_prompt": line,
                "video_prompt": "",
                "negative_prompt": "text overlays, watermarks",
                "rationale": "Deterministic mock: the shot's own fields, joined.",
            })
        return {
            "prompts": prompts,
            "notes": "Generated by the deterministic mock provider.",
        }

    async def check_health(self) -> AIProviderHealth:
        return AIProviderHealth(
            provider_id=self.id,
            configured=True,
            online=True,
            models=[self.default_model],
            mock=True,
        )


# ---------------------------------------------------------------------------
# Reading the request back out of the rendered prompt
# ---------------------------------------------------------------------------
# The mock sees only what a real provider sees - two strings - so it parses the
# structure back out rather than reaching around the abstraction for the
# original objects. That keeps the provider contract honest: if the mock could
# see more than a vendor can, it would not be testing the same path.

_SCENE_COUNT = re.compile(r"exactly (\d+) scenes")
_SHOT_RANGE = re.compile(r"between (\d+) and (\d+) shots")
_SHOT_ID = re.compile(r"^- shot_id=(\S+)")


def _structure_from_prompt(prompt: str) -> tuple[int, int, int]:
    scene_match = _SCENE_COUNT.search(prompt)
    shot_match = _SHOT_RANGE.search(prompt)
    scenes = int(scene_match.group(1)) if scene_match else 3
    min_shots = int(shot_match.group(1)) if shot_match else 9
    max_shots = int(shot_match.group(2)) if shot_match else 15
    return max(1, scenes), max(1, min_shots), max(min_shots, max_shots)


def _section(prompt: str, heading: str) -> str:
    """Text under an ALL-CAPS heading, up to the next one."""
    lines = prompt.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if line.isupper() and line.strip() and not line.startswith(" "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def _shot_lines(prompt: str) -> list[tuple[str, str]]:
    """(shot_id, summary) for every shot listed in a compile request."""
    found: list[tuple[str, str]] = []
    lines = prompt.splitlines()
    for index, line in enumerate(lines):
        match = _SHOT_ID.match(line)
        if not match:
            continue
        detail = " ".join(
            part.strip() for part in lines[index + 1:index + 6]
            if part.startswith("    ")
        )
        found.append((match.group(1), detail or line.strip()))
    return found
