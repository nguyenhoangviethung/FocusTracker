"""Session statistics storage and serialization."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from utils.paths import data_dir


def save_session_statistics(
    minute_scores: list[float],
    average_score: float,
    completed: bool,
    total_seconds: int,
    focused_seconds: int,
    distraction_count: int,
    focus_streak_seconds: float,
) -> dict[str, Any]:
    """
    Save session statistics to data/history.json.
    
    Args:
        minute_scores: List of per-minute focus scores (0-1)
        average_score: Overall average focus score (0-1)
        completed: Whether session was completed naturally (True) or stopped early (False)
        total_seconds: Total session duration in seconds
        focused_seconds: Total focused duration in seconds
        distraction_count: Number of distraction events
        focus_streak_seconds: Longest focus streak in seconds
    
    Returns:
        Dictionary of saved session data
    """
    session_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": total_seconds,
        "focused_seconds": focused_seconds,
        "minute_focus_scores": [float(s) for s in minute_scores],
        "average_focus": float(average_score),
        "distraction_count": int(distraction_count),
        "focus_streak_seconds": float(focus_streak_seconds),
        "completed": bool(completed),
    }
    
    history_file = data_dir() / "history.json"
    
    # Load existing history
    try:
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
    except Exception:
        history = []
    
    # Ensure history is a list
    if not isinstance(history, list):
        history = []
    
    # Add new session
    history.append(session_record)
    
    # Save back
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Warning: Could not save session statistics: {exc}")
    
    return session_record
