"""Persistent application settings for FocusFlow AI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from utils.logger import get_logger
from utils.paths import data_dir


logger = get_logger("settings_store")


DEFAULT_SETTINGS: dict[str, Any] = {
    "session_minutes": 25,
    "camera_index": 0,
    "theme_mode": "Dark",
    "show_landmarks": True,
    "camera_distance_scale": 0.18,
    "inference_mode": "hybrid",
    "cloud_api_url": "",
    "device_id": "",
    "demo_video_path": "",
    "engagement_threshold": 0.54,
    "smoothing_window": 5,
    "auth_user_id": "",
    "auth_provider": "",
    "auth_username": "",
    "auth_email": "",
    "auth_display_name": "",
    "auth_last_login_at": "",
}


def _settings_file() -> Path:
    return data_dir() / "settings.json"


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(DEFAULT_SETTINGS)
    if payload:
        source.update(payload)

    normalized: dict[str, Any] = {}
    normalized["session_minutes"] = max(1, min(180, _to_int(source.get("session_minutes"), 25)))
    normalized["camera_index"] = max(0, _to_int(source.get("camera_index"), 0))

    mode = str(source.get("theme_mode", "Dark")).strip().title()
    normalized["theme_mode"] = "Light" if mode == "Light" else "Dark"
    normalized["show_landmarks"] = bool(source.get("show_landmarks", True))
    normalized["camera_distance_scale"] = _clamp(_to_float(source.get("camera_distance_scale"), 0.18), 0.05, 0.4)
    inference_mode = str(
        os.getenv("FOCUSFLOW_INFERENCE_MODE", "")
        or source.get("inference_mode")
        or "hybrid"
    ).strip().lower()
    normalized["inference_mode"] = (
        inference_mode if inference_mode in {"local", "cloud", "hybrid"} else "local"
    )
    normalized["cloud_api_url"] = str(
        os.getenv("FOCUSFLOW_CLOUD_API_URL", "")
        or source.get("cloud_api_url")
    ).strip().rstrip("/")
    normalized["device_id"] = str(
        source.get("device_id")
        or os.getenv("FOCUSFLOW_DEVICE_ID", "")
        or uuid4()
    ).strip()
    normalized["demo_video_path"] = str(source.get("demo_video_path") or "").strip()
    normalized["engagement_threshold"] = round(
        _clamp(_to_float(source.get("engagement_threshold"), 0.54), 0.05, 0.95),
        3,
    )
    normalized["smoothing_window"] = max(3, min(5, _to_int(source.get("smoothing_window"), 5)))
    normalized["auth_user_id"] = str(source.get("auth_user_id") or "").strip()
    normalized["auth_provider"] = str(source.get("auth_provider") or "").strip()
    normalized["auth_username"] = str(source.get("auth_username") or "").strip()
    normalized["auth_email"] = str(source.get("auth_email") or "").strip()
    normalized["auth_display_name"] = str(source.get("auth_display_name") or "").strip()
    normalized["auth_last_login_at"] = str(source.get("auth_last_login_at") or "").strip()
    return normalized


def load_settings() -> dict[str, Any]:
    target = _settings_file()
    if not target.exists():
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Settings file invalid. Rebuilding default settings", exc_info=True)
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    if not isinstance(raw, dict):
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    normalized = normalize_settings(raw)
    save_settings(normalized)
    return normalized


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_settings(settings)
    target = _settings_file()
    target.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Settings saved to %s", target)
    return normalized
