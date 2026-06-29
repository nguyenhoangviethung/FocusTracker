from __future__ import annotations

from typing import Any


CLASS_SIGNAL_BANDS: dict[int, tuple[float, float]] = {
    0: (0.00, 0.30),
    1: (0.30, 0.50),
    2: (0.50, 0.70),
    3: (0.70, 1.00),
}
MEDIUM_HIGH_SUPPORT_THRESHOLD = 0.20


def presentation_signal(
    predicted_class: Any = None,
    class_probabilities: Any = None,
    focus_score: Any = None,
    medium_high_support_threshold: float = MEDIUM_HIGH_SUPPORT_THRESHOLD,
) -> float:
    """Map a 4-class decision to a human-readable timeline signal.

    The product model decision remains argmax over 4 classes. This score is
    only for UI/trend presentation so class regions are visually separable.
    """
    cls = _safe_class(predicted_class)
    if cls is None:
        return _clamp(_safe_float(focus_score, 0.0))

    low, high = CLASS_SIGNAL_BANDS.get(cls, (0.0, 1.0))
    if cls == 2 and _safe_float(focus_score, 0.0) < medium_high_support_threshold:
        low, high = CLASS_SIGNAL_BANDS[1]
    confidence = _class_confidence(cls, class_probabilities, focus_score)
    return _clamp(low + (high - low) * confidence)


def _class_confidence(cls: int, class_probabilities: Any, focus_score: Any) -> float:
    if isinstance(class_probabilities, (list, tuple)) and 0 <= cls < len(class_probabilities):
        return _clamp(_safe_float(class_probabilities[cls], 0.5))
    if cls == 3:
        return _clamp(_safe_float(focus_score, 0.5))
    return 0.5


def _safe_class(value: Any) -> int | None:
    try:
        cls = int(value)
    except (TypeError, ValueError):
        return None
    return cls if cls in CLASS_SIGNAL_BANDS else None


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
