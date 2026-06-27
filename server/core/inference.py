from __future__ import annotations

import threading
import time

import numpy as np

from shared.contracts import InferenceResponse, TelemetryPacket
from tracking.buffer import DEPTH_ROBUST_V2_FRAME_FEATURE_DIM, enrich_raw_sequence
from tracking.inference import MODEL_NAME, MODEL_VERSION, ProductInferencer


class CloudInferenceEngine:
    """Thread-safe adapter around the depth-aware Triple XGBoost product bundle."""

    def __init__(self) -> None:
        self._inferencer = ProductInferencer()
        self._lock = threading.Lock()

    def predict(self, packet: TelemetryPacket) -> InferenceResponse:
        started = time.perf_counter()
        if packet.face_found:
            raw = np.asarray(packet.raw_feature_sequence, dtype=np.float32)
            enriched = enrich_raw_sequence(
                raw,
                expected_frame_feature_dim=DEPTH_ROBUST_V2_FRAME_FEATURE_DIM,
            )
            with self._lock:
                prediction = self._inferencer.predict(enriched)
            focus_score = float(prediction.get("focus_score", prediction.get("probability", 0.0)))
            ai_state = str(prediction.get("state", "DISTRACTED"))
            state = "FOCUSED" if ai_state == "ENGAGED" else "DISTRACTED"
            decision = {
                "state": state,
                "source": MODEL_VERSION,
                "reason": "Decision produced by the depth-aware Triple XGBoost 4-class fusion model.",
                "ai_probability": focus_score,
                "decision_rule": prediction.get("decision_rule", "argmax_4class"),
                "ai_state": ai_state,
                "predicted_class": prediction.get("prediction_4class"),
                "predicted_label": prediction.get("prediction_label"),
                "engaged_class_indices": prediction.get("engaged_class_indices", [2, 3]),
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

        inference_latency_ms = (time.perf_counter() - started) * 1000.0

        return InferenceResponse(
            message_id=packet.message_id,
            session_id=packet.session_id,
            inference_latency_ms=inference_latency_ms,
            model_name=str(prediction.get("model_name", MODEL_NAME)),
            model_version=str(prediction.get("model_version", MODEL_VERSION)),
            label_space=prediction.get("label_space"),
            state=state,
            ai_state=ai_state,
            focus_score=max(0.0, min(1.0, focus_score)),
            components=dict(prediction.get("components") or {}),
            weights=dict(prediction.get("weights") or {}),
            class_labels=list(prediction.get("class_labels") or []),
            class_probabilities=list(prediction.get("probabilities_4class") or []),
            predicted_class=prediction.get("prediction_4class"),
            predicted_label=prediction.get("prediction_label"),
            decision=decision,
            latency_ms=inference_latency_ms,
        )
