from __future__ import annotations

import numpy as np

from tracking.detector import FRAME_FEATURE_DIM
from tracking.tracker import FocusSessionTracker, TrackerConfig


def test_feature_guard_accepts_small_motion() -> None:
    tracker = FocusSessionTracker(TrackerConfig(), output_queue=None)  # type: ignore[arg-type]
    tracker._recent_features.extend(
        [
            np.full(FRAME_FEATURE_DIM, 0.10, dtype=np.float32),
            np.full(FRAME_FEATURE_DIM, 0.11, dtype=np.float32),
            np.full(FRAME_FEATURE_DIM, 0.09, dtype=np.float32),
        ]
    )

    assert tracker._is_feature_stable(np.full(FRAME_FEATURE_DIM, 0.12, dtype=np.float32)) is True


def test_feature_guard_rejects_spiky_outlier() -> None:
    tracker = FocusSessionTracker(TrackerConfig(), output_queue=None)  # type: ignore[arg-type]
    tracker._recent_features.extend(
        [
            np.full(FRAME_FEATURE_DIM, 0.10, dtype=np.float32),
            np.full(FRAME_FEATURE_DIM, 0.11, dtype=np.float32),
            np.full(FRAME_FEATURE_DIM, 0.09, dtype=np.float32),
        ]
    )

    spike = np.full(FRAME_FEATURE_DIM, 0.10, dtype=np.float32)
    spike[5] = 4.0

    assert tracker._is_feature_stable(spike) is False
