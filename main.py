from __future__ import annotations

from typing import Any

from ui.app_window import FocusFlowApp
from utils.logger import get_logger, setup_logging


logger = get_logger("main")


def fusion_logic(
    ai_probability: float,
    os_snapshot: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Fuse webcam AI confidence with active-window keyword heuristics."""
    probability = max(0.0, min(1.0, float(ai_probability)))
    engagement_threshold = _to_float(config.get("engagement_threshold"), 0.54)
    os_ai_threshold = _to_float(config.get("os_ai_threshold"), 0.45)
    os_override_threshold = _to_float(config.get("os_override_threshold"), 0.60)
    productive_keywords = _normalize_keywords(config.get("productive_keywords"))
    distracting_keywords = _normalize_keywords(config.get("distracting_keywords"))

    snapshot = os_snapshot or {}
    process_name = str(snapshot.get("process_name") or "")
    window_title = str(snapshot.get("window_title") or "")
    interaction_score = _to_float(snapshot.get("interaction_score"), 0.0)
    os_text = f"{process_name} {window_title}".lower()

    has_productive_context = any(keyword in os_text for keyword in productive_keywords)
    has_distracting_context = any(keyword in os_text for keyword in distracting_keywords)
    ai_is_focused = probability >= engagement_threshold
    weak_ai_can_be_helped = probability >= os_ai_threshold
    os_can_override = has_productive_context and interaction_score >= os_override_threshold

    if has_distracting_context and not ai_is_focused:
        return {
            "state": "DISTRACTED",
            "source": "os_distracting_keyword",
            "reason": "Active window matched a distracting keyword while AI confidence was low.",
            "ai_probability": probability,
            "os_state": "DISTRACTING",
            "interaction_score": interaction_score,
        }

    if ai_is_focused:
        return {
            "state": "FOCUSED",
            "source": "ai",
            "reason": "AI confidence reached the engagement threshold.",
            "ai_probability": probability,
            "os_state": "PRODUCTIVE" if has_productive_context else "NEUTRAL",
            "interaction_score": interaction_score,
        }

    if os_can_override or (has_productive_context and weak_ai_can_be_helped):
        return {
            "state": "FOCUSED",
            "source": "os_productive_override",
            "reason": "OS tracker found a productive active window that supports the AI signal.",
            "ai_probability": probability,
            "os_state": "PRODUCTIVE",
            "interaction_score": interaction_score,
        }

    return {
        "state": "DISTRACTED",
        "source": "combined_low_signal",
        "reason": "AI confidence and OS productivity signal are both below threshold.",
        "ai_probability": probability,
        "os_state": "NEUTRAL",
        "interaction_score": interaction_score,
    }


def main() -> None:
    setup_logging()
    logger.info("Starting FocusFlow AI desktop app")
    app = FocusFlowApp(fusion_logic=fusion_logic)
    app.mainloop()


def _normalize_keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = ()
    return tuple(str(item).strip().lower() for item in items if str(item).strip())


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    main()
