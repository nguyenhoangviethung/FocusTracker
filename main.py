from __future__ import annotations
import sys
from typing import Any

from PyQt6.QtWidgets import QApplication
from ui.app_window import FocusFlowApp
from utils.logger import get_logger, setup_logging

logger = get_logger("main")

def fusion_logic(ai_probability: float, os_snapshot: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    probability = max(0.0, min(1.0, float(ai_probability)))
    engagement_threshold = _to_float(config.get("engagement_threshold"), 0.54)
    os_ai_threshold = _to_float(config.get("os_ai_threshold"), 0.45)
    os_override_threshold = _to_float(config.get("os_override_threshold"), 0.60)
    
    prod_kws = _normalize_keywords(config.get("productive_keywords", "vscode,github,pdf,docx,figma"))
    dist_kws = _normalize_keywords(config.get("distracting_keywords", "facebook,netflix,lol,tiktok"))

    snapshot = os_snapshot or {}
    os_text = f"{snapshot.get('process_name', '')} {snapshot.get('window_title', '')}".lower()
    interaction_score = _to_float(snapshot.get("interaction_score"), 0.0)

    has_prod = any(kw in os_text for kw in prod_kws)
    has_dist = any(kw in os_text for kw in dist_kws)
    ai_focused = probability >= engagement_threshold

    if has_dist and not ai_focused:
        return {"state": "DISTRACTED", "ai_probability": probability, "os_state": "DISTRACTING"}

    if ai_focused:
        return {"state": "FOCUSED", "ai_probability": probability, "os_state": "PRODUCTIVE" if has_prod else "NEUTRAL"}

    if (has_prod and interaction_score >= os_override_threshold) or (has_prod and probability >= os_ai_threshold):
        return {"state": "FOCUSED", "ai_probability": probability, "os_state": "PRODUCTIVE"}

    return {"state": "DISTRACTED", "ai_probability": probability, "os_state": "NEUTRAL"}

def main() -> None:
    setup_logging()
    logger.info("Starting FocusFlow AI PyQt6 desktop app")
    
    app = QApplication(sys.argv)
    window = FocusFlowApp(fusion_logic=fusion_logic)
    window.show()
    sys.exit(app.exec())

def _normalize_keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, str): items = value.split(",")
    elif isinstance(value, (list, tuple)): items = value
    else: items = ()
    return tuple(str(i).strip().lower() for i in items if str(i).strip())

def _to_float(value: Any, default: float) -> float:
    try: return float(value)
    except: return default

if __name__ == "__main__":
    main()
