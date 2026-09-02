def test_media_catalogue_is_safe_and_separates_image_from_video(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-redacted")
    response = client.get("/api/media/providers")
    assert response.status_code == 200
    assert "test-redacted" not in response.text

    body = response.json()
    providers = {item["id"]: item for item in body["providers"]}
    assert providers["comfyui"]["media_types"] == ["image", "video", "image-to-video"]
    assert providers["openai"]["media_types"] == ["image"]
    assert providers["openai"]["default_model"]
    assert providers["openai"]["cost_warning"]
    assert providers["openai"]["requires_confirmation"] is True


def test_media_health_does_not_call_unconfigured_openai(client):
    response = client.get("/api/media/health")
    assert response.status_code == 200
    openai = next(item for item in response.json()["providers"] if item["id"] == "openai")
    assert openai["configured"] is False
    assert openai["online"] is False
    assert "OPENAI_API_KEY" in openai["error"]
