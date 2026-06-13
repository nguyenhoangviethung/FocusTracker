from __future__ import annotations

from tracking.tracker import TrackerConfig
from utils.settings_store import normalize_settings


def test_cloud_environment_overrides_stale_local_settings(monkeypatch) -> None:
    cloud_url = "https://focusflow-api.example.run.app"
    monkeypatch.setenv("FOCUSFLOW_CLOUD_API_URL", cloud_url)

    settings = normalize_settings({"cloud_api_url": "http://127.0.0.1:8080"})

    assert settings["cloud_api_url"] == cloud_url


def test_tracker_accepts_server_api_key_for_desktop_cloud_requests(monkeypatch) -> None:
    monkeypatch.delenv("FOCUSFLOW_CLOUD_API_KEY", raising=False)
    monkeypatch.setenv("FOCUSFLOW_API_KEY", "shared-api-key")
    monkeypatch.setenv("FOCUSFLOW_INFERENCE_MODE", "hybrid")

    config = TrackerConfig.from_dict(
        {
            "inference_mode": "local",
            "cloud_api_url": "https://focusflow-api.example.run.app",
            "device_id": "desktop-01",
        }
    )

    assert config.inference_mode == "hybrid"
    assert config.cloud_api_key == "shared-api-key"
