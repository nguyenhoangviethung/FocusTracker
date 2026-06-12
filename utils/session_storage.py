"""Session history read/write helpers for production workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from utils.logger import get_logger
from utils.paths import data_dir


logger = get_logger("session_storage")


def _history_file() -> Path:
    return data_dir() / "history.json"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_session_history() -> list[dict[str, Any]]:
    target = _history_file()
    if not target.exists():
        return []
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Cannot parse history file, returning empty list", exc_info=True)
        return []
    if not isinstance(raw, list):
        return []
    normalized = [normalize_session_record(item) for item in raw if isinstance(item, dict)]
    return sorted(normalized, key=lambda item: item.get("timestamp") or "", reverse=True)


def save_session_history(records: list[dict[str, Any]]) -> None:
    target = _history_file()
    target.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_session_record(record: dict[str, Any]) -> dict[str, Any]:
    minute_scores_raw = record.get("minute_focus_scores", [])
    if isinstance(minute_scores_raw, list):
        minute_scores = [max(0.0, min(1.0, _safe_float(item))) for item in minute_scores_raw]
    else:
        minute_scores = []

    average_focus = _safe_float(record.get("average_focus"), 0.0)
    if minute_scores and (average_focus <= 0.0 and any(score > 0.0 for score in minute_scores)):
        average_focus = sum(minute_scores) / len(minute_scores)
    average_focus = max(0.0, min(1.0, average_focus))

    duration_seconds = _safe_int(record.get("duration_seconds"), 0)
    if duration_seconds <= 0 and minute_scores:
        duration_seconds = len(minute_scores) * 60

    focused_seconds = _safe_int(record.get("focused_seconds"), int(round(duration_seconds * average_focus)))
    focused_seconds = max(0, min(duration_seconds if duration_seconds > 0 else focused_seconds, focused_seconds))

    distraction_count = max(0, _safe_int(record.get("distraction_count"), 0))
    focus_streak_seconds = max(0.0, _safe_float(record.get("focus_streak_seconds"), 0.0))
    completed = _safe_bool(record.get("completed"), True)

    normalized = {
        "timestamp": str(record.get("timestamp") or _now_iso()),
        "duration_seconds": duration_seconds,
        "focused_seconds": focused_seconds,
        "minute_focus_scores": minute_scores,
        "average_focus": average_focus,
        "distraction_count": distraction_count,
        "focus_streak_seconds": focus_streak_seconds,
        "completed": completed,
    }
    if record.get("inference_mode"):
        normalized["inference_mode"] = str(record.get("inference_mode") or "local")
    if record.get("cloud_session_id"):
        normalized["cloud_session_id"] = str(record.get("cloud_session_id") or "")
    if record.get("report_status"):
        normalized["report_status"] = str(record.get("report_status") or "").strip()
    if record.get("report_started_at"):
        normalized["report_started_at"] = str(record.get("report_started_at") or "").strip()
    if record.get("report_completed_at"):
        normalized["report_completed_at"] = str(record.get("report_completed_at") or "").strip()
    return normalized


def save_session_statistics(
    minute_scores: list[float],
    average_score: float,
    completed: bool,
    total_seconds: int,
    focused_seconds: int,
    distraction_count: int,
    focus_streak_seconds: float,
) -> dict[str, Any]:
    session_record = normalize_session_record(
        {
            "timestamp": _now_iso(),
            "duration_seconds": int(total_seconds),
            "focused_seconds": int(focused_seconds),
            "minute_focus_scores": [float(score) for score in minute_scores],
            "average_focus": float(average_score),
            "distraction_count": int(distraction_count),
            "focus_streak_seconds": float(focus_streak_seconds),
            "completed": bool(completed),
        }
    )
    history = load_session_history()
    history.insert(0, session_record)
    save_session_history(history)
    logger.info("Saved session record. Total sessions: %s", len(history))
    return session_record


def update_session_record(timestamp: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    history = load_session_history()
    updated_record: dict[str, Any] | None = None
    for index, record in enumerate(history):
        if str(record.get("timestamp")) != str(timestamp):
            continue
        merged = dict(record)
        merged.update(updates)
        updated_record = normalize_session_record(merged)
        history[index] = updated_record
        break

    if updated_record is None:
        logger.warning("Cannot update session record; timestamp not found: %s", timestamp)
        return None

    save_session_history(history)
    return updated_record


def summarize_history(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "total_sessions": 0,
            "avg_focus": 0.0,
            "avg_duration_seconds": 0,
            "completion_rate": 0.0,
            "last_session": None,
        }

    total_sessions = len(records)
    avg_focus = sum(_safe_float(item.get("average_focus")) for item in records) / total_sessions
    avg_duration_seconds = int(round(sum(_safe_int(item.get("duration_seconds")) for item in records) / total_sessions))
    completion_rate = sum(1 for item in records if _safe_bool(item.get("completed"), False)) / total_sessions

    return {
        "total_sessions": total_sessions,
        "avg_focus": max(0.0, min(1.0, avg_focus)),
        "avg_duration_seconds": max(0, avg_duration_seconds),
        "completion_rate": max(0.0, min(1.0, completion_rate)),
        "last_session": records[0],
    }
