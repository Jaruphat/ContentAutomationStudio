"""
Tests for the AI story tasks: project state in, persisted rows out.

Two kinds of test here. The happy paths run through the real
:class:`MockAIProvider`, so they exercise the same code a live vendor would
reach. The apply-logic edge cases run through a scripted provider returning
hand-written JSON, because the point is what the service does with a response
the mock would never produce - an invented shot id, an unknown character name,
a duration that does not add up.
"""

import json
import uuid

import pytest

from app.models import Character, Location, Scene, Shot, Style
from app.services.ai.base import AIProvider, TokenUsage
from app.services.ai.mock_provider import MockAIProvider
from app.services.ai.tasks import (
    AITaskError,
    compile_shot_prompts,
    generate_storyboard,
    generate_story_bible,
)

PLOT = (
    "A courier leaves the depot at dawn. "
    "She crosses the flooded bridge. "
    "She arrives as the lights come on."
)


class ScriptedProvider(AIProvider):
    """Returns one fixed payload, so apply logic can be driven precisely."""

    id = "scripted"
    label = "Scripted"
    api_key_env = ""
    default_model = "scripted-1"

    def __init__(self, payload: dict, **kwargs):
        super().__init__(**kwargs)
        self.payload = payload
        self.prompts: list[str] = []

    async def _complete_once(self, request):
        self.prompts.append(request.user_prompt)
        return (
            json.dumps(self.payload), self.model, TokenUsage(), "scripted-resp",
        )


@pytest.fixture()
def provider():
    return MockAIProvider()


@pytest.fixture()
def story_project(db_session, sample_project):
    """A project with enough narrative for decomposition to be meaningful."""
    sample_project.brief_text = "A short film about a delivery at dawn."
    sample_project.plot_text = PLOT
    db_session.commit()
    return sample_project


def shot_entry(order: int, **overrides) -> dict:
    entry = {
        "order": order,
        "shot_type": "wide shot",
        "camera_angle": "eye level",
        "camera_movement": "static",
        "lens_framing": "35mm",
        "subject": "Courier",
        "action": "walks",
        "environment": "depot yard",
        "dialogue": "",
        "planned_duration_sec": 5.0,
        "generation_mode": "image",
        "image_prompt": "a courier at dawn",
        "video_prompt": "",
        "negative_prompt": "watermark",
    }
    entry.update(overrides)
    return entry


def scene_entry(order: int, **overrides) -> dict:
    entry = {
        "order": order,
        "title": f"Scene {order + 1}",
        "purpose": "Establish",
        "summary": "Something happens.",
        "time_of_day": "dawn",
        "emotional_beat": "anticipation",
        "planned_duration_sec": 10.0,
        "character_names": [],
        "location_name": "",
        "shots": [shot_entry(0), shot_entry(1)],
    }
    entry.update(overrides)
    return entry


# ===========================================================================
# Preconditions
# ===========================================================================

@pytest.mark.asyncio
async def test_a_project_with_no_brief_and_no_plot_is_refused(
    db_session, sample_project, provider
):
    """A model asked to work from nothing invents a story unrelated to the
    project, so the task refuses instead."""
    sample_project.brief_text = ""
    sample_project.plot_text = ""
    db_session.commit()

    with pytest.raises(AITaskError) as excinfo:
        await generate_storyboard(db_session, sample_project, provider)
    assert excinfo.value.category == "bad_request"


@pytest.mark.asyncio
async def test_a_brief_alone_is_enough(db_session, sample_project, provider):
    """A brief with no plot is the common starting point."""
    sample_project.brief_text = "A film about a courier."
    sample_project.plot_text = ""
    db_session.commit()

    outcome = await generate_storyboard(db_session, sample_project, provider)
    assert outcome.data["scenes"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"scene_count": 0},
    {"scene_count": 999},
    {"min_shots": 0},
    {"min_shots": 10, "max_shots": 5},
    {"max_shots": 5000},
])
async def test_out_of_range_structure_is_rejected(
    db_session, story_project, provider, kwargs
):
    """Guard rails: a request far outside the band would be truncated
    mid-JSON rather than failing cleanly."""
    with pytest.raises(AITaskError) as excinfo:
        await generate_storyboard(db_session, story_project, provider, **kwargs)
    assert excinfo.value.category == "bad_request"


# ===========================================================================
# Storyboard: preview
# ===========================================================================

@pytest.mark.asyncio
async def test_preview_writes_nothing(db_session, story_project, provider):
    outcome = await generate_storyboard(
        db_session, story_project, provider, apply=False,
    )

    assert outcome.applied is False
    assert outcome.summary == {}
    assert outcome.data["scenes"]
    assert db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).count() == 0


@pytest.mark.asyncio
async def test_preview_carries_provenance(db_session, story_project, provider):
    outcome = await generate_storyboard(db_session, story_project, provider)

    assert outcome.provenance["provider_id"] == "mock"
    assert outcome.provenance["mock"] is True
    assert outcome.provenance["prompt_version"]
    assert outcome.provenance["schema_version"]
    assert outcome.provenance["generated_at"]


# ===========================================================================
# Storyboard: apply
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_creates_scenes_and_shots(
    db_session, story_project, provider
):
    outcome = await generate_storyboard(
        db_session, story_project, provider,
        scene_count=3, min_shots=9, max_shots=15, apply=True,
    )

    assert outcome.applied is True
    scenes = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).order_by(Scene.order).all()

    assert len(scenes) == 3
    assert outcome.summary["scenes_created"] == 3
    assert [s.order for s in scenes] == [0, 1, 2]

    shot_total = sum(
        db_session.query(Shot).filter(Shot.scene_id == s.id).count()
        for s in scenes
    )
    assert 9 <= shot_total <= 15
    assert outcome.summary["shots_created"] == shot_total


@pytest.mark.asyncio
async def test_applied_shots_are_ordered_within_each_scene(
    db_session, story_project, provider
):
    await generate_storyboard(
        db_session, story_project, provider, apply=True,
    )
    for scene in db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).all():
        shots = db_session.query(Shot).filter(
            Shot.scene_id == scene.id
        ).order_by(Shot.order).all()
        assert [s.order for s in shots] == list(range(len(shots)))


@pytest.mark.asyncio
async def test_applied_shots_start_in_draft(
    db_session, story_project, provider
):
    """Generated shots are a draft for review, not approved for generation."""
    await generate_storyboard(db_session, story_project, provider, apply=True)
    assert all(
        shot.status == "Draft" for shot in db_session.query(Shot).all()
    )


@pytest.mark.asyncio
async def test_an_existing_storyboard_is_not_silently_replaced(
    db_session, story_project, sample_scene, provider
):
    """Replacing scenes deletes their shots, jobs and takes. That needs an
    explicit confirmation, not a default."""
    with pytest.raises(AITaskError) as excinfo:
        await generate_storyboard(
            db_session, story_project, provider, apply=True,
        )

    assert excinfo.value.category == "conflict"
    assert "replace_existing" in str(excinfo.value)
    # And nothing was touched.
    assert db_session.query(Scene).count() == 1


@pytest.mark.asyncio
async def test_replace_existing_clears_the_old_storyboard(
    db_session, story_project, sample_scene, sample_shot, provider
):
    old_scene_id = sample_scene.id
    old_shot_id = sample_shot.id

    outcome = await generate_storyboard(
        db_session, story_project, provider,
        apply=True, replace_existing=True,
    )

    assert outcome.summary["scenes_deleted"] == 1
    assert db_session.query(Scene).filter(Scene.id == old_scene_id).first() is None
    # The cascade reached the shot too.
    assert db_session.query(Shot).filter(Shot.id == old_shot_id).first() is None
    assert db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).count() == outcome.summary["scenes_created"]


@pytest.mark.asyncio
async def test_a_preview_never_conflicts_with_existing_scenes(
    db_session, story_project, sample_scene, provider
):
    """Previewing is always safe, so it is never blocked."""
    outcome = await generate_storyboard(
        db_session, story_project, provider, apply=False,
    )
    assert outcome.applied is False
    assert db_session.query(Scene).count() == 1


# ===========================================================================
# Storyboard: derived values and bible linking
# ===========================================================================

@pytest.mark.asyncio
async def test_scene_duration_is_recomputed_from_its_shots(
    db_session, story_project
):
    """The model's own sum is frequently a few seconds out, and duration is a
    derived value, so it is recomputed rather than trusted."""
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0, planned_duration_sec=999.0, shots=[
            shot_entry(0, planned_duration_sec=4.0),
            shot_entry(1, planned_duration_sec=6.5),
        ])],
        "notes": "",
    })

    await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )

    scene = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).one()
    assert scene.planned_duration_sec == pytest.approx(10.5)


@pytest.mark.asyncio
async def test_known_character_and_location_names_are_linked(
    db_session, story_project, sample_character, sample_location
):
    scripted = ScriptedProvider({
        "scenes": [scene_entry(
            0,
            character_names=[sample_character.name],
            location_name=sample_location.name,
        )],
        "notes": "",
    })

    outcome = await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )

    scene = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).one()
    assert scene.character_ids == [sample_character.id]
    assert scene.location_id == sample_location.id
    assert outcome.warnings == []


@pytest.mark.asyncio
async def test_name_matching_ignores_case_and_padding(
    db_session, story_project, sample_character
):
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0, character_names=["  aLiCe  "])],
        "notes": "",
    })

    await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )
    scene = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).one()
    assert scene.character_ids == [sample_character.id]


@pytest.mark.asyncio
async def test_an_unknown_character_name_warns_and_creates_nothing(
    db_session, story_project
):
    """Inventing a bible entry from a bare name would give a character with no
    description, which is worse for prompt compilation than no link."""
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0, character_names=["Nobody"])],
        "notes": "",
    })

    outcome = await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )

    scene = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).one()
    assert scene.character_ids == []
    assert db_session.query(Character).filter(
        Character.name == "Nobody"
    ).count() == 0
    assert any("Nobody" in w for w in outcome.warnings)


@pytest.mark.asyncio
async def test_an_unknown_location_name_warns(db_session, story_project):
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0, location_name="Atlantis")],
        "notes": "",
    })

    outcome = await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )

    scene = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).one()
    assert scene.location_id is None
    assert any("Atlantis" in w for w in outcome.warnings)


@pytest.mark.asyncio
async def test_a_still_shot_never_keeps_a_motion_prompt(
    db_session, story_project
):
    """The JSON Schema cannot express 'empty when mode is image'."""
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0, shots=[shot_entry(
            0, generation_mode="image", video_prompt="camera pushes in",
        )])],
        "notes": "",
    })

    await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )
    shot = db_session.query(Shot).one()
    assert shot.video_prompt == ""


@pytest.mark.asyncio
async def test_a_video_shot_keeps_its_motion_prompt(db_session, story_project):
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0, shots=[shot_entry(
            0, generation_mode="video", video_prompt="camera pushes in",
        )])],
        "notes": "",
    })

    await generate_storyboard(
        db_session, story_project, scripted, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )
    assert db_session.query(Shot).one().video_prompt == "camera pushes in"


@pytest.mark.asyncio
async def test_a_short_count_is_reported_as_a_warning(
    db_session, story_project
):
    """The model returned fewer scenes than asked for; that is worth saying,
    not worth failing over."""
    scripted = ScriptedProvider({
        "scenes": [scene_entry(0)],
        "notes": "",
    })

    outcome = await generate_storyboard(
        db_session, story_project, scripted,
        scene_count=3, min_shots=9, max_shots=15,
    )

    assert any("3 scenes" in w for w in outcome.warnings)
    assert any("9-15 shots" in w for w in outcome.warnings)


# ===========================================================================
# Story bible
# ===========================================================================

@pytest.mark.asyncio
async def test_story_bible_preview_writes_nothing(
    db_session, story_project, provider
):
    outcome = await generate_story_bible(db_session, story_project, provider)

    assert outcome.applied is False
    assert db_session.query(Character).filter(
        Character.project_id == story_project.id
    ).count() == 0


@pytest.mark.asyncio
async def test_story_bible_apply_creates_entries(db_session, story_project):
    scripted = ScriptedProvider({
        "characters": [{
            "name": "Mira", "role": "courier", "age_range": "late 20s",
            "appearance": "close-cropped hair", "clothing": "orange shell",
            "color_palette": "orange, slate", "personality": "dogged",
            "prompt_tokens": "orange shell jacket, close-cropped hair",
        }],
        "locations": [{
            "name": "Depot", "description": "a concrete yard",
            "geography": "riverside", "time_of_day": "dawn",
            "palette": "grey, amber", "lighting": "sodium lamps",
            "props": "pallet stacks",
        }],
        "style": {
            "medium": "live-action", "genre": "quiet drama",
            "visual_keywords": "grounded, filmic",
            "camera_language": "steady", "palette": "cool",
            "lighting_rules": "motivated",
            "negative_constraints": "watermarks",
        },
        "notes": "",
    })

    outcome = await generate_story_bible(
        db_session, story_project, scripted, apply=True,
    )

    assert outcome.summary["characters_created"] == 1
    assert outcome.summary["locations_created"] == 1
    assert outcome.summary["styles_created"] == 1

    character = db_session.query(Character).filter(
        Character.project_id == story_project.id
    ).one()
    assert character.name == "Mira"
    assert character.prompt_tokens.startswith("orange shell jacket")


@pytest.mark.asyncio
async def test_story_bible_merges_onto_an_existing_character_by_name(
    db_session, story_project, sample_character
):
    """The id must survive, or scenes already referencing it break."""
    original_id = sample_character.id
    scripted = ScriptedProvider({
        "characters": [{
            "name": "Alice", "role": "lead", "age_range": "",
            "appearance": "now with a scar", "clothing": "",
            "color_palette": "", "personality": "", "prompt_tokens": "",
        }],
        "locations": [],
        "style": {k: "" for k in (
            "medium", "genre", "visual_keywords", "camera_language",
            "palette", "lighting_rules", "negative_constraints",
        )},
        "notes": "",
    })

    outcome = await generate_story_bible(
        db_session, story_project, scripted, apply=True,
    )

    assert outcome.summary["characters_created"] == 0
    assert outcome.summary["characters_updated"] == 1

    character = db_session.query(Character).filter(
        Character.project_id == story_project.id
    ).one()
    assert character.id == original_id
    assert character.appearance == "now with a scar"
    assert character.role == "lead"
    # An empty field means "nothing to add", not "erase what the user wrote".
    assert character.clothing == "red dress"


@pytest.mark.asyncio
async def test_story_bible_updates_the_existing_style_rather_than_adding_one(
    db_session, story_project, sample_style
):
    """Running twice must not accumulate near-duplicate style rows."""
    scripted = ScriptedProvider({
        "characters": [], "locations": [],
        "style": {
            "medium": "live-action", "genre": "", "visual_keywords": "",
            "camera_language": "", "palette": "", "lighting_rules": "",
            "negative_constraints": "",
        },
        "notes": "",
    })

    outcome = await generate_story_bible(
        db_session, story_project, scripted, apply=True,
    )

    assert outcome.summary["styles_created"] == 0
    assert outcome.summary["styles_updated"] == 1
    styles = db_session.query(Style).filter(
        Style.project_id == story_project.id
    ).all()
    assert len(styles) == 1
    assert styles[0].medium == "live-action"


@pytest.mark.asyncio
async def test_an_all_empty_style_creates_nothing(db_session, story_project):
    scripted = ScriptedProvider({
        "characters": [], "locations": [],
        "style": {k: "" for k in (
            "medium", "genre", "visual_keywords", "camera_language",
            "palette", "lighting_rules", "negative_constraints",
        )},
        "notes": "",
    })

    outcome = await generate_story_bible(
        db_session, story_project, scripted, apply=True,
    )
    assert outcome.summary["styles_created"] == 0
    assert db_session.query(Style).filter(
        Style.project_id == story_project.id
    ).count() == 0


@pytest.mark.asyncio
async def test_existing_bible_entries_reach_the_prompt(
    db_session, story_project, sample_character, sample_location
):
    """So the model reuses names instead of coining new ones."""
    scripted = ScriptedProvider({
        "characters": [], "locations": [],
        "style": {k: "" for k in (
            "medium", "genre", "visual_keywords", "camera_language",
            "palette", "lighting_rules", "negative_constraints",
        )},
        "notes": "",
    })

    await generate_story_bible(db_session, story_project, scripted)

    prompt = scripted.prompts[0]
    assert "Alice" in prompt
    assert "Forest Clearing" in prompt


# ===========================================================================
# Prompt compilation
# ===========================================================================

@pytest.mark.asyncio
async def test_compiling_with_no_shots_is_refused(
    db_session, story_project, provider
):
    with pytest.raises(AITaskError) as excinfo:
        await compile_shot_prompts(db_session, story_project, provider)
    assert excinfo.value.category == "bad_request"


@pytest.mark.asyncio
async def test_compiled_prompts_are_written_to_the_named_shots(
    db_session, story_project, sample_scene, sample_shot
):
    scripted = ScriptedProvider({
        "prompts": [{
            "shot_id": sample_shot.id,
            "image_prompt": "a compiled still",
            "video_prompt": "",
            "negative_prompt": "watermark, text",
            "rationale": "folded in the bible",
        }],
        "notes": "",
    })

    outcome = await compile_shot_prompts(
        db_session, story_project, scripted, apply=True,
    )

    db_session.refresh(sample_shot)
    assert outcome.summary["shots_updated"] == 1
    assert sample_shot.image_prompt == "a compiled still"
    assert sample_shot.negative_prompt == "watermark, text"


@pytest.mark.asyncio
async def test_compilation_preview_writes_nothing(
    db_session, story_project, sample_scene, sample_shot
):
    before = sample_shot.image_prompt
    scripted = ScriptedProvider({
        "prompts": [{
            "shot_id": sample_shot.id, "image_prompt": "changed",
            "video_prompt": "", "negative_prompt": "", "rationale": "",
        }],
        "notes": "",
    })

    outcome = await compile_shot_prompts(
        db_session, story_project, scripted, apply=False,
    )

    db_session.refresh(sample_shot)
    assert outcome.applied is False
    assert sample_shot.image_prompt == before


@pytest.mark.asyncio
async def test_an_invented_shot_id_is_ignored_not_matched_by_position(
    db_session, story_project, sample_scene, sample_shot
):
    """A shifted response would otherwise write every prompt onto the wrong
    shot."""
    before = sample_shot.image_prompt
    scripted = ScriptedProvider({
        "prompts": [{
            "shot_id": str(uuid.uuid4()), "image_prompt": "wrong shot",
            "video_prompt": "", "negative_prompt": "", "rationale": "",
        }],
        "notes": "",
    })

    outcome = await compile_shot_prompts(
        db_session, story_project, scripted, apply=True,
    )

    db_session.refresh(sample_shot)
    assert sample_shot.image_prompt == before
    assert outcome.summary["prompts_ignored"] == 1
    assert outcome.summary["shots_missing"] == 1
    assert any("not in the request" in w for w in outcome.warnings)


@pytest.mark.asyncio
async def test_a_duplicated_shot_id_is_only_applied_once(
    db_session, story_project, sample_scene, sample_shot
):
    scripted = ScriptedProvider({
        "prompts": [
            {"shot_id": sample_shot.id, "image_prompt": "first",
             "video_prompt": "", "negative_prompt": "", "rationale": ""},
            {"shot_id": sample_shot.id, "image_prompt": "second",
             "video_prompt": "", "negative_prompt": "", "rationale": ""},
        ],
        "notes": "",
    })

    outcome = await compile_shot_prompts(
        db_session, story_project, scripted, apply=True,
    )

    db_session.refresh(sample_shot)
    assert sample_shot.image_prompt == "first"
    assert outcome.summary["shots_updated"] == 1
    assert outcome.summary["prompts_ignored"] == 1


@pytest.mark.asyncio
async def test_a_shot_left_out_of_the_response_is_left_unchanged(
    db_session, story_project, sample_scene, sample_shot
):
    other = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
        image_prompt="untouched", generation_mode="image",
    )
    db_session.add(other)
    db_session.commit()

    scripted = ScriptedProvider({
        "prompts": [{
            "shot_id": sample_shot.id, "image_prompt": "compiled",
            "video_prompt": "", "negative_prompt": "", "rationale": "",
        }],
        "notes": "",
    })

    outcome = await compile_shot_prompts(
        db_session, story_project, scripted, apply=True,
    )

    db_session.refresh(other)
    assert other.image_prompt == "untouched"
    assert outcome.summary["shots_missing"] == 1


@pytest.mark.asyncio
async def test_shot_ids_narrow_the_selection(
    db_session, story_project, sample_scene, sample_shot
):
    other = Shot(
        id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
        generation_mode="image",
    )
    db_session.add(other)
    db_session.commit()

    scripted = ScriptedProvider({"prompts": [], "notes": ""})
    await compile_shot_prompts(
        db_session, story_project, scripted, shot_ids=[sample_shot.id],
    )

    prompt = scripted.prompts[0]
    assert sample_shot.id in prompt
    assert other.id not in prompt
    assert "SHOTS TO COMPILE (1)" in prompt


@pytest.mark.asyncio
async def test_a_shot_from_another_project_cannot_be_reached(
    db_session, story_project, sample_scene, sample_shot, provider
):
    """The selection joins through Scene, which confines it to this project."""
    from app.models import Project

    other_project = Project(id=str(uuid.uuid4()), title="Other")
    other_scene = Scene(
        id=str(uuid.uuid4()), project_id=other_project.id, order=0,
    )
    other_shot = Shot(
        id=str(uuid.uuid4()), scene_id=other_scene.id, order=0,
        image_prompt="do not touch", generation_mode="image",
    )
    db_session.add_all([other_project, other_scene, other_shot])
    db_session.commit()

    scripted = ScriptedProvider({
        "prompts": [{
            "shot_id": other_shot.id, "image_prompt": "leaked",
            "video_prompt": "", "negative_prompt": "", "rationale": "",
        }],
        "notes": "",
    })

    outcome = await compile_shot_prompts(
        db_session, story_project, scripted,
        shot_ids=[sample_shot.id, other_shot.id], apply=True,
    )

    db_session.refresh(other_shot)
    assert other_shot.image_prompt == "do not touch"
    assert outcome.summary["prompts_ignored"] == 1


@pytest.mark.asyncio
async def test_a_still_shot_does_not_gain_a_motion_prompt(
    db_session, story_project, sample_scene, sample_shot
):
    assert sample_shot.generation_mode == "image"
    scripted = ScriptedProvider({
        "prompts": [{
            "shot_id": sample_shot.id, "image_prompt": "still",
            "video_prompt": "camera pushes in",
            "negative_prompt": "", "rationale": "",
        }],
        "notes": "",
    })

    await compile_shot_prompts(
        db_session, story_project, scripted, apply=True,
    )

    db_session.refresh(sample_shot)
    assert sample_shot.video_prompt == ""


@pytest.mark.asyncio
async def test_too_many_shots_in_one_call_is_refused(
    db_session, story_project, sample_scene, provider
):
    """Beyond this the response is truncated rather than failing cleanly."""
    from app.services.ai.tasks import MAX_SHOTS_PER_COMPILE

    db_session.add_all([
        Shot(
            id=str(uuid.uuid4()), scene_id=sample_scene.id, order=index,
            generation_mode="image",
        )
        for index in range(MAX_SHOTS_PER_COMPILE + 1)
    ])
    db_session.commit()

    with pytest.raises(AITaskError) as excinfo:
        await compile_shot_prompts(db_session, story_project, provider)
    assert excinfo.value.category == "bad_request"


@pytest.mark.asyncio
async def test_the_story_bible_reaches_the_compilation_prompt(
    db_session, story_project, sample_scene, sample_shot, sample_style
):
    """A shot in a known location must be able to repeat its descriptors."""
    scripted = ScriptedProvider({"prompts": [], "notes": ""})
    await compile_shot_prompts(db_session, story_project, scripted)

    prompt = scripted.prompts[0]
    assert "Alice" in prompt
    assert "Forest Clearing" in prompt
    assert "ethereal, luminous" in prompt


@pytest.mark.asyncio
async def test_guidance_is_appended_to_the_prompt(
    db_session, story_project, sample_scene, sample_shot
):
    scripted = ScriptedProvider({"prompts": [], "notes": ""})
    await compile_shot_prompts(
        db_session, story_project, scripted, guidance="Keep it wordless.",
    )
    assert "Keep it wordless." in scripted.prompts[0]


# ===========================================================================
# End to end through the mock, with no key configured
# ===========================================================================

@pytest.mark.asyncio
async def test_the_whole_chain_runs_offline(db_session, story_project):
    """Bible, storyboard and prompts, no key, no network, all persisted."""
    provider = MockAIProvider()

    await generate_story_bible(db_session, story_project, provider, apply=True)
    storyboard = await generate_storyboard(
        db_session, story_project, provider,
        scene_count=3, min_shots=9, max_shots=15, apply=True,
    )
    prompts = await compile_shot_prompts(
        db_session, story_project, provider, apply=True,
    )

    assert storyboard.summary["scenes_created"] == 3
    assert prompts.summary["shots_updated"] == storyboard.summary["shots_created"]
    assert prompts.summary["prompts_ignored"] == 0
    assert prompts.summary["shots_missing"] == 0

    # Every shot ended up with a prompt to generate from.
    shots = (
        db_session.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Scene.project_id == story_project.id)
        .all()
    )
    assert shots
    assert all(shot.image_prompt for shot in shots)


@pytest.mark.asyncio
async def test_locations_created_by_the_bible_link_on_the_next_storyboard(
    db_session, story_project
):
    """The two tasks compose: names written by one are matched by the other."""
    bible = ScriptedProvider({
        "characters": [{
            "name": "Mira", "role": "courier", "age_range": "",
            "appearance": "", "clothing": "", "color_palette": "",
            "personality": "", "prompt_tokens": "orange shell",
        }],
        "locations": [{
            "name": "Depot", "description": "a yard", "geography": "",
            "time_of_day": "", "palette": "", "lighting": "", "props": "",
        }],
        "style": {k: "" for k in (
            "medium", "genre", "visual_keywords", "camera_language",
            "palette", "lighting_rules", "negative_constraints",
        )},
        "notes": "",
    })
    await generate_story_bible(db_session, story_project, bible, apply=True)

    storyboard = ScriptedProvider({
        "scenes": [scene_entry(
            0, character_names=["Mira"], location_name="Depot",
        )],
        "notes": "",
    })
    outcome = await generate_storyboard(
        db_session, story_project, storyboard, scene_count=1,
        min_shots=1, max_shots=5, apply=True,
    )

    scene = db_session.query(Scene).filter(
        Scene.project_id == story_project.id
    ).one()
    character = db_session.query(Character).filter(
        Character.name == "Mira"
    ).one()
    location = db_session.query(Location).filter(
        Location.name == "Depot"
    ).one()

    assert scene.character_ids == [character.id]
    assert scene.location_id == location.id
    assert outcome.warnings == []
