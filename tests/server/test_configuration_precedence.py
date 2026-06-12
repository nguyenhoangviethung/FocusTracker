from __future__ import annotations

from utils.settings_store import normalize_settings


def test_cloud_environment_overrides_stale_local_settings(monkeypatch) -> None:
    cloud_url = "https://focusflow-api.example.run.app"
    monkeypatch.setenv("FOCUSFLOW_CLOUD_API_URL", cloud_url)

    settings = normalize_settings({"cloud_api_url": "http://127.0.0.1:8080"})

    assert settings["cloud_api_url"] == cloud_url
