"""Fields that cost generation time must survive the API boundary."""

import pytest


def create_shot(client, seed=None):
    project = client.post("/api/projects", json={"title": "Seed test"}).json()
    pid = project["id"]
    scene = client.post(f"/api/projects/{pid}/scenes", json={"title": "Scene"}).json()
    path = f"/api/projects/{pid}/scenes/{scene['id']}/shots"
    payload = {"image_prompt": "A train", "seed_policy": "fixed"}
    if seed is not None:
        payload["seed"] = seed
    shot = client.post(path, json=payload)
    assert shot.status_code == 201
    return pid, path, shot.json()


@pytest.mark.parametrize("seed", [0, 20260905, 2147483647])
def test_fixed_seed_survives_storage_and_reaches_generation(client, seed):
    pid, path, shot = create_shot(client, seed)
    assert shot["seed"] == seed
    result = client.post(f"/api/projects/{pid}/generate", json={"shot_ids": [shot["id"]]})
    assert result.status_code == 200
    job = result.json()[0]
    assert job["seed"] == seed
    assert job["parameter_map"]["seed"] == seed


def test_legacy_fixed_seed_preserves_42(client):
    pid, path, shot = create_shot(client)
    jobs = client.post(f"/api/projects/{pid}/generate", json={"shot_ids": [shot["id"]]}).json()
    assert jobs[0]["seed"] == 42


def test_misspelled_motion_is_refused_without_updating_the_shot(client):
    pid, path, shot = create_shot(client)
    result = client.put(f"{path}/{shot['id']}", json={"subject_moton": "The train moves"})
    assert result.status_code == 422
    assert "subject_moton" in result.text
    assert client.post(f"/api/projects/{pid}/generate", json={"confirm_paid_generaton": True}).status_code == 422


@pytest.mark.parametrize("seed", [-1, 2147483648, 1.5])
def test_invalid_seed_is_refused(client, seed):
    pid, path, shot = create_shot(client)
    assert client.put(f"{path}/{shot['id']}", json={"seed": seed}).status_code == 422


def test_audio_controls_survive_api_without_invalidating_generated_image(client):
    pid, path, shot = create_shot(client)
    response = client.put(f"{path}/{shot['id']}", json={"audio_mode": "mute", "audio_gain_db": -12})
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["audio_mode"] == "mute" and changed["audio_gain_db"] == -12
    assert changed["content_sha256"] == shot["content_sha256"]
    assert changed["prompt_revision"] == shot["prompt_revision"]
    for payload in [{"audio_gain_db": 80}, {"audio_mode": "off"}]:
        assert client.put(f"{path}/{shot['id']}", json=payload).status_code == 422
