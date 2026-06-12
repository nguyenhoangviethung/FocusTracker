from __future__ import annotations

import threading
import time

import numpy as np

from shared.contracts import InferenceResponse, TelemetryPacket
from tracking.buffer import enrich_raw_sequence
from tracking.inference import MODEL_NAME, MODEL_VERSION, ONNXEngagementInferencer


class CloudInferenceEngine:
    """Thread-safe adapter around the bundled CPU late-fusion ensemble."""

    def __init__(self) -> None:
        self._inferencer = ONNXEngagementInferencer(smoothing_window=1)
        self._lock = threading.Lock()

    def predict(self, packet: TelemetryPacket) -> InferenceResponse:
        started = time.perf_counter()
        if packet.face_found:
            raw = np.asarray(packet.raw_feature_sequence, dtype=np.float32)
            enriched = enrich_raw_sequence(raw, expected_frame_feature_dim=30)
            with self._lock:
                prediction = self._inferencer.predict(enriched)
            focus_score = float(prediction.get("focus_score", prediction.get("probability", 0.0)))
            ai_state = str(prediction.get("state", "DISTRACTED"))
            state = "FOCUSED" if ai_state == "ENGAGED" else "DISTRACTED"
            decision = {
                "state": state,
                "source": "late_fusion_model",
                "reason": "Decision produced by the GRU + TCN + XGBoost ensemble.",
                "ai_probability": focus_score,
                "threshold": float(prediction.get("threshold", 0.54)),
            }
        else:
            prediction = {}
            focus_score = 0.0
            ai_state = "NO_FACE"
            state = "NO_FACE"
            decision = {
                "state": state,
                "source": "face_presence_guard",
                "reason": "No face was detected in the submitted sequence.",
                "ai_probability": 0.0,
            }

        return InferenceResponse(
            message_id=packet.message_id,
            session_id=packet.session_id,
            model_name=str(prediction.get("model_name", MODEL_NAME)),
            model_version=str(prediction.get("model_version", MODEL_VERSION)),
            state=state,
            ai_state=ai_state,
            focus_score=max(0.0, min(1.0, focus_score)),
            components=dict(prediction.get("components") or {}),
            weights=dict(prediction.get("weights") or {}),
            decision=decision,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
