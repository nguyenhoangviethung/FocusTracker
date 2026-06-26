from __future__ import annotations

from tracking.tracker import TrackerConfig
from utils.settings_store import normalize_settings


def test_cloud_environment_overrides_stale_local_settings(monkeypatch) -> None:
    cloud_url = "https://focusflow-api.example.run.app"
    monkeypatch.setenv("FOCUSFLOW_CLOUD_API_URL", cloud_url)

    settings = normalize_settings({"cloud_api_url": "http://127.0.0.1:8080"})

    assert settings["cloud_api_url"] == cloud_url


def test_tracker_preserves_explicit_hybrid_mode_and_accepts_cloud_api_key(monkeypatch) -> None:
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


def test_settings_environment_selects_a_supported_inference_mode(monkeypatch) -> None:
    monkeypatch.setenv("FOCUSFLOW_INFERENCE_MODE", "local")

    settings = normalize_settings({"inference_mode": "hybrid"})

    assert settings["inference_mode"] == "local"


def test_settings_defaults_to_local_when_no_inference_mode_is_configured(monkeypatch) -> None:
    monkeypatch.delenv("FOCUSFLOW_INFERENCE_MODE", raising=False)

    settings = normalize_settings({})

    assert settings["inference_mode"] == "local"
