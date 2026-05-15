from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
import onnxruntime as ort

from utils.paths import model_path


class ONNXEngagementInferencer:
    """Runs ONNX inference and returns smoothed engagement score/state."""

    DEFAULT_THRESHOLD = 0.30

    def __init__(
        self,
        model_file: str | Path | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        smoothing_window: int = 5,
    ) -> None:
        resolved_model = Path(model_file) if model_file else model_path()
        if not resolved_model.exists():
            raise FileNotFoundError(
                f"ONNX model not found at {resolved_model}. Run scripts/export_to_onnx.py first."
            )

        self.threshold = float(threshold)
        self.smoothing_window = max(3, min(5, int(smoothing_window)))
        self._scores: deque[float] = deque(maxlen=self.smoothing_window)

        self.session = ort.InferenceSession(
            str(resolved_model),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    @staticmethod
    def _sigmoid(logit: float) -> float:
        clipped = np.clip(logit, -60.0, 60.0)
        return float(1.0 / (1.0 + np.exp(-clipped)))

    def reset(self) -> None:
        self._scores.clear()

    def predict(self, enriched_chunk: np.ndarray) -> dict[str, float | str]:
        chunk = np.asarray(enriched_chunk, dtype=np.float32)
        if chunk.shape != (60, 90):
            raise ValueError(f"Expected chunk shape (60, 90), got {chunk.shape}")

        data = chunk[np.newaxis, :, :].astype(np.float32, copy=False)
        outputs = self.session.run(None, {self.input_name: data})
        raw_logit = float(np.asarray(outputs[0]).reshape(-1)[0])

        probability = self._sigmoid(raw_logit)
        self._scores.append(probability)
        smoothed_probability = float(np.mean(self._scores))

        state = "ENGAGED" if smoothed_probability >= self.threshold else "DISTRACTED"
        return {
            "logit": raw_logit,
            "probability": probability,
            "focus_score": smoothed_probability,
            "state": state,
        }
