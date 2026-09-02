"""
Tests for the AI HTTP endpoints.

These are the routes the cockpit calls, so the contract asserted here - paths,
status codes, and the ``category`` field the UI branches on - is what the
frontend depends on.

Every test runs with no ``OPENAI_API_KEY`` (cleared by the ``ai_env`` fixture in
conftest) except where one is set deliberately, and none reaches the network:
the mock provider is the default in that state, which is the point.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Project, Scene, Shot


@pytest.fixture()
def story_project(db_session: Session, sample_project: Project) -> Project:
    sample_project.brief_text = "A short film about a delivery at dawn."
    sample_project.plot_text = (
        "A courier leaves the depot at dawn. She crosses the flooded bridge. "
        "She arrives as the lights come on."
    )
    db_session.commit()
    return sample_project


# ===========================================================================
# Catalogue
# ===========================================================================

class TestProviderCatalogue:
    def test_lists_every_provider(self, client):
        resp = client.get("/api/ai/providers")
        assert resp.status_code == 200

        body = resp.json()
        assert {p["id"] for p in body["providers"]} == {"mock", "openai"}

    def test_the_mock_is_the_default_with_no_key(self, client):
        body = client.get("/api/ai/providers").json()
        assert body["default_provider_id"] == "mock"

    def test_openai_becomes_the_default_once_configured(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        body = client.get("/api/ai/providers").json()
        assert body["default_provider_id"] == "openai"

    def test_each_provider_offers_selectable_models(self, client):
        body = client.get("/api/ai/providers").json()
        for provider in body["providers"]:
            assert provider["models"]
            assert all(m["id"] and m["label"] for m in provider["models"])

    def test_the_key_variable_is_named_but_never_the_key(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-must-not-appear")
        resp = client.get("/api/ai/providers")

        openai = next(
            p for p in resp.json()["providers"] if p["id"] == "openai"
        )
        assert openai["api_key_env"] == "OPENAI_API_KEY"
        assert openai["configured"] is True
        assert "sk-secret-must-not-appear" not in resp.text

    def test_the_mock_is_flagged_as_mock(self, client):
        body = client.get("/api/ai/providers").json()
        mock = next(p for p in body["providers"] if p["id"] == "mock")
        assert mock["mock"] is True
        assert mock["requires_key"] is False


# ===========================================================================
# Health
# ===========================================================================

class TestAIHealth:
    def test_reports_every_provider(self, client):
        resp = client.get("/api/ai/health")
        assert resp.status_code == 200
        assert {
            p["provider_id"] for p in resp.json()["providers"]
        } == {"mock", "openai"}

    def test_the_mock_is_online_without_configuration(self, client):
        body = client.get("/api/ai/health").json()
        mock = next(p for p in body["providers"] if p["provider_id"] == "mock")
        assert mock["online"] is True
        assert mock["mock"] is True

    def test_an_unconfigured_openai_is_reported_not_an_error(self, client):
        """A provider that is down is a result, not a failed request."""
        resp = client.get("/api/ai/health")
        assert resp.status_code == 200

        openai = next(
            p for p in resp.json()["providers"] if p["provider_id"] == "openai"
        )
        assert openai["configured"] is False
        assert openai["online"] is False
        assert "OPENAI_API_KEY" in openai["error"]

    def test_the_missing_key_is_listed_as_a_blocker(self, client):
        body = client.get("/api/ai/health").json()
        assert any("OPENAI_API_KEY" in b for b in body["blockers"])

    def test_can_target_a_single_provider(self, client):
        body = client.get("/api/ai/health?provider_id=mock").json()
        assert len(body["providers"]) == 1
        assert body["providers"][0]["provider_id"] == "mock"

    def test_an_unknown_provider_is_a_400_with_a_category(self, client):
        resp = client.get("/api/ai/health?provider_id=nope")
        assert resp.status_code == 400
        assert resp.json()["category"] == "bad_request"


class TestSystemHealth:
    def test_reports_the_ai_default_without_a_network_call(self, client):
        body = client.get("/api/health").json()
        assert body["ai"]["default_provider_id"] == "mock"
        assert body["ai"]["mock"] is True

    def test_the_ai_blocker_appears_alongside_the_comfyui_ones(self, client):
        body = client.get("/api/health").json()
        assert any("OPENAI_API_KEY" in b for b in body["blockers"])

    def test_the_blocker_clears_once_a_key_is_configured(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        body = client.get("/api/health").json()
        assert not any("OPENAI_API_KEY" in b for b in body["blockers"])
        assert body["ai"]["default_provider_id"] == "openai"

    def test_existing_health_fields_are_unchanged(self, client):
        """The AI section is additive; nothing the UI already reads moved."""
        body = client.get("/api/health").json()
        for key in ("status", "service", "version", "comfyui", "queue",
                    "workflows", "blockers"):
            assert key in body


# ===========================================================================
# Storyboard generation
# ===========================================================================

class TestStoryboardEndpoint:
    def test_previews_without_writing(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"scene_count": 3, "min_shots": 9, "max_shots": 15},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["applied"] is False
        assert body["task"] == "scene_decomposition"
        assert len(body["data"]["scenes"]) == 3

        scenes = client.get(f"/api/projects/{story_project.id}/scenes").json()
        assert scenes == []

    def test_applying_creates_scenes_and_shots(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={
                "scene_count": 3, "min_shots": 9, "max_shots": 15,
                "apply": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True

        scenes = client.get(f"/api/projects/{story_project.id}/scenes").json()
        assert len(scenes) == 3

        total = 0
        for scene in scenes:
            shots = client.get(
                f"/api/projects/{story_project.id}/scenes/{scene['id']}/shots"
            ).json()
            total += len(shots)
        assert 9 <= total <= 15
        assert body["summary"]["shots_created"] == total

    def test_provenance_marks_mock_output(self, client, story_project):
        """The UI must be able to label output no language model produced."""
        body = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard", json={},
        ).json()

        assert body["provenance"]["provider_id"] == "mock"
        assert body["provenance"]["mock"] is True
        assert body["provenance"]["prompt_version"]
        assert body["provenance"]["schema_version"]

    def test_an_existing_storyboard_is_a_409(
        self, client, story_project, sample_scene
    ):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"apply": True},
        )
        assert resp.status_code == 409
        assert resp.json()["category"] == "conflict"

    def test_replace_existing_confirms_the_overwrite(
        self, client, story_project, sample_scene
    ):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"apply": True, "replace_existing": True},
        )
        assert resp.status_code == 200
        assert resp.json()["summary"]["scenes_deleted"] == 1

    def test_a_project_with_no_story_is_a_400(self, client, sample_project):
        # sample_project ships with placeholder text; clear it first.
        client.put(
            f"/api/projects/{sample_project.id}/story",
            json={"brief_text": "", "plot_text": ""},
        )
        resp = client.post(
            f"/api/projects/{sample_project.id}/ai/storyboard", json={},
        )
        assert resp.status_code == 400
        assert resp.json()["category"] == "bad_request"

    def test_an_out_of_range_scene_count_is_a_400(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"scene_count": 500},
        )
        assert resp.status_code == 400
        assert resp.json()["category"] == "bad_request"

    def test_an_unknown_project_is_a_404(self, client):
        resp = client.post(
            f"/api/projects/{uuid.uuid4()}/ai/storyboard", json={},
        )
        assert resp.status_code == 404

    def test_an_unknown_provider_is_a_400(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"provider_id": "anthropic"},
        )
        assert resp.status_code == 400
        assert resp.json()["category"] == "bad_request"

    def test_requesting_openai_without_a_key_is_a_409_not_mock_output(
        self, client, story_project
    ):
        """The anti-surprise contract, at the HTTP boundary.

        The request must fail with an actionable category rather than quietly
        returning placeholder text the user would take for authored work.
        """
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"provider_id": "openai"},
        )
        assert resp.status_code == 409

        body = resp.json()
        assert body["category"] == "not_configured"
        assert "OPENAI_API_KEY" in body["detail"]
        assert "data" not in body

    def test_guidance_is_accepted(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"guidance": "Keep every shot wordless."},
        )
        assert resp.status_code == 200

    def test_a_key_cannot_be_supplied_over_the_api(self, client, story_project):
        """Extra fields are ignored, so a client cannot inject a credential."""
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"provider_id": "openai", "api_key": "sk-injected"},
        )
        # Still unconfigured: the body's key was not read.
        assert resp.status_code == 409
        assert resp.json()["category"] == "not_configured"


# ===========================================================================
# Story bible
# ===========================================================================

class TestStoryBibleEndpoint:
    def test_previews_without_writing(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/story-bible", json={},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["task"] == "story_bible"
        assert body["applied"] is False
        assert "characters" in body["data"]

    def test_applying_reports_a_summary(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/story-bible",
            json={"apply": True},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["applied"] is True
        assert "characters_created" in body["summary"]

    def test_an_unknown_project_is_a_404(self, client):
        resp = client.post(
            f"/api/projects/{uuid.uuid4()}/ai/story-bible", json={},
        )
        assert resp.status_code == 404


# ===========================================================================
# Prompt compilation
# ===========================================================================

class TestPromptCompilationEndpoint:
    def test_compiles_and_applies_to_the_projects_shots(
        self, client, db_session, story_project, sample_scene, sample_shot
    ):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/prompts",
            json={"apply": True},
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["task"] == "shot_prompts"
        assert body["summary"]["shots_updated"] == 1

        shot = client.get(
            f"/api/projects/{story_project.id}/scenes/{sample_scene.id}"
            f"/shots/{sample_shot.id}"
        ).json()
        assert shot["image_prompt"]

    def test_a_subset_can_be_selected(
        self, client, db_session, story_project, sample_scene, sample_shot
    ):
        other = Shot(
            id=str(uuid.uuid4()), scene_id=sample_scene.id, order=2,
            image_prompt="untouched", generation_mode="image",
        )
        db_session.add(other)
        db_session.commit()

        resp = client.post(
            f"/api/projects/{story_project.id}/ai/prompts",
            json={"apply": True, "shot_ids": [sample_shot.id]},
        )
        assert resp.status_code == 200
        assert resp.json()["summary"]["shots_updated"] == 1

        untouched = client.get(
            f"/api/projects/{story_project.id}/scenes/{sample_scene.id}"
            f"/shots/{other.id}"
        ).json()
        assert untouched["image_prompt"] == "untouched"

    def test_a_project_with_no_shots_is_a_400(self, client, story_project):
        resp = client.post(
            f"/api/projects/{story_project.id}/ai/prompts", json={},
        )
        assert resp.status_code == 400
        assert resp.json()["category"] == "bad_request"

    def test_an_unknown_project_is_a_404(self, client):
        resp = client.post(
            f"/api/projects/{uuid.uuid4()}/ai/prompts", json={},
        )
        assert resp.status_code == 404


# ===========================================================================
# The full flow over HTTP, offline
# ===========================================================================

class TestOfflineEndToEnd:
    def test_brief_to_storyboard_to_prompts_with_no_key(
        self, client, db_session
    ):
        """The vertical slice the product promises without any configuration."""
        project = client.post("/api/projects", json={
            "title": "Offline Run",
            "objective": "Prove the mock path",
            "brief_text": "A courier film.",
            "plot_text": (
                "A courier leaves at dawn. She crosses the bridge. "
                "She arrives at dusk."
            ),
        }).json()

        bible = client.post(
            f"/api/projects/{project['id']}/ai/story-bible",
            json={"apply": True},
        )
        assert bible.status_code == 200

        storyboard = client.post(
            f"/api/projects/{project['id']}/ai/storyboard",
            json={
                "scene_count": 3, "min_shots": 9, "max_shots": 15,
                "apply": True,
            },
        )
        assert storyboard.status_code == 200
        assert storyboard.json()["summary"]["scenes_created"] == 3

        prompts = client.post(
            f"/api/projects/{project['id']}/ai/prompts",
            json={"apply": True},
        )
        assert prompts.status_code == 200
        assert prompts.json()["summary"]["prompts_ignored"] == 0

        # Persisted and readable through the pre-existing endpoints.
        scenes = client.get(f"/api/projects/{project['id']}/scenes").json()
        assert len(scenes) == 3

        shot_count = 0
        for scene in scenes:
            shots = client.get(
                f"/api/projects/{project['id']}/scenes/{scene['id']}/shots"
            ).json()
            shot_count += len(shots)
            assert all(s["image_prompt"] for s in shots)
        assert 9 <= shot_count <= 15

    def test_the_generated_storyboard_reaches_preflight(
        self, client, db_session
    ):
        """What AI produced flows into the stage that follows it."""
        project = client.post("/api/projects", json={
            "title": "Preflight Handoff",
            "brief_text": "A courier film.",
            "plot_text": "A courier leaves. She arrives.",
        }).json()

        client.post(
            f"/api/projects/{project['id']}/ai/storyboard",
            json={"scene_count": 2, "min_shots": 4, "max_shots": 8,
                  "apply": True},
        )

        preflight = client.get(f"/api/projects/{project['id']}/preflight")
        assert preflight.status_code == 200
        # Preflight sees the shots that AI created, whatever its verdict.
        assert preflight.json()["total_shots"] >= 4

    def test_preflight_identifies_only_shots_breaking_recurring_prop_continuity(
        self, client, db_session, sample_project, sample_scene, sample_shot,
        sample_location,
    ):
        sample_location.props = "Exactly one recurring white paper boat throughout."
        sample_shot.subject = "Alice holding the paper boat"
        sample_shot.image_prompt = "Alice holding a boat"
        other = Shot(
            id=str(uuid.uuid4()),
            scene_id=sample_scene.id,
            order=2,
            subject="empty forest",
            image_prompt="empty forest",
            generation_mode="image",
            status="Draft",
        )
        db_session.add(other)
        db_session.commit()

        body = client.get(f"/api/projects/{sample_project.id}/preflight").json()

        continuity = [
            issue for issue in body["issues"]
            if any("recurring prop continuity" in text for text in issue["issues"])
        ]
        assert [issue["shot_id"] for issue in continuity] == [sample_shot.id]

    def test_generated_scenes_survive_a_new_session(
        self, client, db_engine, story_project
    ):
        """Written through the ORM, not held in memory."""
        client.post(
            f"/api/projects/{story_project.id}/ai/storyboard",
            json={"scene_count": 2, "min_shots": 4, "max_shots": 8,
                  "apply": True},
        )

        from sqlalchemy.orm import sessionmaker
        fresh = sessionmaker(bind=db_engine)()
        try:
            assert fresh.query(Scene).filter(
                Scene.project_id == story_project.id
            ).count() == 2
            assert fresh.query(Shot).count() >= 4
        finally:
            fresh.close()
