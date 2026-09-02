def test_paid_openai_image_requires_explicit_confirmation(client, sample_project, sample_scene, sample_shot):
    client.put(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots/{sample_shot.id}",
        json={"image_provider_id": "openai", "image_model": "gpt-image-1-mini", "status": "Ready"},
    )
    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 409
    assert "confirm_paid_generation" in response.json()["detail"]


def test_confirmed_openai_image_job_records_provider_and_model(
    client, monkeypatch, sample_project, sample_scene, sample_shot
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-redacted")
    client.put(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots/{sample_shot.id}",
        json={"image_provider_id": "openai", "image_model": "gpt-image-1-mini", "status": "Ready"},
    )
    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id], "confirm_paid_generation": True},
    )
    assert response.status_code == 200
    job = response.json()[0]
    assert job["media_provider_id"] == "openai"
    assert job["media_model"] == "gpt-image-1-mini"
    assert job["workflow_id"] is None
    assert job["request_params"]["paid_generation_confirmed"] is True


def test_video_ignores_image_provider_and_stays_comfyui(
    client, sample_project, sample_scene, sample_shot
):
    client.put(
        f"/api/projects/{sample_project.id}/scenes/{sample_scene.id}/shots/{sample_shot.id}",
        json={
            "generation_mode": "video",
            "video_prompt": "camera moves",
            "image_provider_id": "openai",
            "image_model": "gpt-image-1-mini",
            "status": "Ready",
        },
    )
    response = client.post(
        f"/api/projects/{sample_project.id}/generate",
        json={"shot_ids": [sample_shot.id]},
    )
    assert response.status_code == 200
    assert response.json()[0]["media_provider_id"] == "comfyui"
