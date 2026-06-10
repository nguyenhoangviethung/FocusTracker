"""Persistent application settings for FocusFlow AI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger
from utils.paths import data_dir


logger = get_logger("settings_store")


DEFAULT_SETTINGS: dict[str, Any] = {
    "session_minutes": 25,
    "camera_index": 0,
    "theme_mode": "Dark",
    "show_landmarks": True,
    "camera_distance_scale": 0.18,
    "hardcore_enabled": False,
    "hardcore_countdown_seconds": 30,
    "mentor_report_enabled": False,
    "mentor_email": "",
    "demo_video_path": "",
    "productive_keywords": "vscode, github, pdf, docx, figma",
    "distracting_keywords": "facebook, netflix, lol, tiktok",
    "engagement_threshold": 0.54,
    "smoothing_window": 5,
    "os_ai_threshold": 0.45,
    "os_override_threshold": 0.60,
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
    normalized["hardcore_enabled"] = bool(source.get("hardcore_enabled", False))
    normalized["hardcore_countdown_seconds"] = max(
        5,
        min(300, _to_int(source.get("hardcore_countdown_seconds"), 30)),
    )
    normalized["mentor_report_enabled"] = bool(source.get("mentor_report_enabled", False))
    normalized["mentor_email"] = str(source.get("mentor_email") or "").strip()
    normalized["demo_video_path"] = str(source.get("demo_video_path") or "").strip()
    normalized["productive_keywords"] = str(
        source.get("productive_keywords") or DEFAULT_SETTINGS["productive_keywords"]
    ).strip()
    normalized["distracting_keywords"] = str(
        source.get("distracting_keywords") or DEFAULT_SETTINGS["distracting_keywords"]
    ).strip()

    normalized["engagement_threshold"] = round(
        _clamp(_to_float(source.get("engagement_threshold"), 0.54), 0.05, 0.95),
        3,
    )
    normalized["smoothing_window"] = max(3, min(5, _to_int(source.get("smoothing_window"), 5)))
    normalized["os_ai_threshold"] = round(
        _clamp(_to_float(source.get("os_ai_threshold"), 0.45), 0.05, 0.95),
        3,
    )
    normalized["os_override_threshold"] = round(
        _clamp(_to_float(source.get("os_override_threshold"), 0.60), 0.05, 0.95),
        3,
    )
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
