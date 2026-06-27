from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any

import numpy as np
import xgboost as xgb

from utils.logger import get_logger
from utils.paths import resource_base_dir


logger = get_logger("inference")

MODEL_NAME = "triple_xgb_depth_robust_fusion"
MODEL_VERSION = "triple_xgb_depth_robust_target_band_product"
LABEL_SPACE = "daisee_4class"
CLASS_LABELS = ("very_low", "low", "medium", "high")
ENGAGED_CLASS_INDICES = (3,)
SEQUENCE_LENGTH = 30
RAW_FEATURE_DIM = 168
ENRICHED_FEATURE_DIM = 504
FEATURE_MODE = "tsfresh"
COMPONENTS = ("final_xgb", "boost_xgb", "targeted_xgb")


@dataclass(frozen=True)
class TripleXGBSpec:
    model_dir: Path
    sequence_length: int = SEQUENCE_LENGTH
    raw_feature_dim: int = RAW_FEATURE_DIM
    enriched_feature_dim: int = ENRICHED_FEATURE_DIM
    feature_mode: str = FEATURE_MODE

    def expected_input_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.enriched_feature_dim

    def raw_sequence_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.raw_feature_dim


class TripleXGBDepthRobustInferencer:
    """CPU adapter for the depth-aware Triple XGBoost product bundle."""

    def __init__(self, model_dir: str | Path | None = None) -> None:
        configured_dir = os.getenv("FOCUSFLOW_TRIPLE_XGB_MODEL_DIR", "").strip()
        self._model_dir = Path(
            model_dir
            or configured_dir
            or resource_base_dir() / "models" / MODEL_VERSION
        )
        config_file = self._model_dir / "fusion_config.json"
        summary_file = self._model_dir / "summary.json"
        if not config_file.exists():
            raise FileNotFoundError(
                f"Triple XGB product artifact is missing: {config_file}. "
                "Download triple_xgb_depth_robust_target_band_product.zip before starting."
            )

        self._config = json.loads(config_file.read_text(encoding="utf-8"))
        self._summary = (
            json.loads(summary_file.read_text(encoding="utf-8"))
            if summary_file.exists()
            else {}
        )
        self._weights = self._load_weights()
        self._temperature = float(self._config.get("fusion", {}).get("temperature", 1.0))
        self._bias_vector = self._load_bias_vector()
        self._models: dict[str, xgb.Booster] = {}
        self._preprocessors: dict[str, dict[str, np.ndarray]] = {}
        self.spec = TripleXGBSpec(model_dir=self._model_dir)

        logger.info("Loading Triple XGB depth-robust product bundle from %s", self._model_dir)
        for component in COMPONENTS:
            component_dir = self._model_dir / component
            model_path = component_dir / "model.json"
            preprocessor_path = component_dir / "preprocessor.npz"
            if not model_path.exists():
                raise FileNotFoundError(f"Missing XGBoost component model: {model_path}")
            if not preprocessor_path.exists():
                raise FileNotFoundError(f"Missing XGBoost preprocessor: {preprocessor_path}")

            booster = xgb.Booster()
            booster.load_model(str(model_path))
            self._models[component] = booster

            prep = np.load(preprocessor_path, allow_pickle=False)
            mean = np.asarray(prep["mean"], dtype=np.float32)
            scale = np.asarray(prep["scale"], dtype=np.float32)
            if mean.shape != scale.shape:
                raise ValueError(
                    f"Preprocessor mean/scale shape mismatch for {component}: {mean.shape} != {scale.shape}"
                )
            self._preprocessors[component] = {
                "mean": mean,
                "scale": np.where(np.abs(scale) < 1e-12, 1.0, scale).astype(np.float32),
            }
        logger.info("Triple XGB depth-robust product bundle loaded.")

    def _load_weights(self) -> dict[str, float]:
        raw = self._config.get("fusion", {}).get("weights", {})
        weights = {name: float(raw.get(name, 0.0)) for name in COMPONENTS}
        total = sum(weights.values())
        if total <= 0.0:
            raise ValueError("Triple XGB fusion weights are missing or invalid.")
        return {name: value / total for name, value in weights.items()}

    def _load_bias_vector(self) -> np.ndarray | None:
        fusion = self._config.get("fusion", {})
        power = float(fusion.get("bias_power", 0.0) or 0.0)
        if power <= 0.0:
            return None

        selected = self._summary.get("selected", {})
        validation = selected.get("validation_metrics", {}) if isinstance(selected, dict) else {}
        support = validation.get("support_per_class")
        if not isinstance(support, list) or len(support) != 4:
            return None

        counts = np.asarray(support, dtype=np.float64)
        if np.any(counts <= 0.0):
            return None
        raw = np.power(counts.sum() / (len(counts) * counts), power)
        raw /= raw.mean()
        return raw.astype(np.float32)

    @staticmethod
    def _normalize(probabilities: np.ndarray) -> np.ndarray:
        values = np.asarray(probabilities, dtype=np.float64)
        values = np.clip(values, 1e-12, None)
        values /= values.sum(axis=-1, keepdims=True)
        return values.astype(np.float32)

    def _adjust(self, probabilities: np.ndarray) -> np.ndarray:
        adjusted = np.asarray(probabilities, dtype=np.float64)
        if self._bias_vector is not None:
            adjusted *= self._bias_vector.reshape(1, -1)
        if self._temperature and self._temperature != 1.0:
            adjusted = np.power(np.clip(adjusted, 1e-12, None), 1.0 / self._temperature)
        return self._normalize(adjusted)

    @staticmethod
    def _sequence_to_basic_features(sequence: np.ndarray) -> np.ndarray:
        first_frame = sequence[0]
        last_frame = sequence[-1]
        return np.concatenate(
            (
                sequence.mean(axis=0),
                sequence.std(axis=0),
                sequence.min(axis=0),
                sequence.max(axis=0),
                first_frame,
                last_frame,
                last_frame - first_frame,
                np.asarray([float(sequence.shape[0])], dtype=np.float32),
            )
        ).astype(np.float32, copy=False)

    @classmethod
    def _sequence_to_tsfresh_like_features(cls, sequence: np.ndarray) -> np.ndarray:
        sequence = np.asarray(sequence, dtype=np.float32)
        centered = sequence - sequence.mean(axis=0, keepdims=True)
        time_steps = np.arange(sequence.shape[0], dtype=np.float32)
        centered_t = time_steps - time_steps.mean()
        slope_den = float(np.sum(centered_t * centered_t) + 1e-6)

        diff = np.diff(sequence, axis=0)
        mean_abs_diff = np.mean(np.abs(diff), axis=0) if diff.size else np.zeros(sequence.shape[1], dtype=np.float32)
        max_abs_diff = np.max(np.abs(diff), axis=0) if diff.size else np.zeros(sequence.shape[1], dtype=np.float32)

        slope = (centered_t[:, None] * centered).sum(axis=0) / slope_den
        energy = np.mean(sequence * sequence, axis=0)
        iqr = np.percentile(sequence, 75, axis=0) - np.percentile(sequence, 25, axis=0)
        median = np.median(sequence, axis=0)
        q10 = np.percentile(sequence, 10, axis=0)
        q90 = np.percentile(sequence, 90, axis=0)
        value_range = np.ptp(sequence, axis=0)
        centered_std = sequence.std(axis=0) + 1e-6
        skewness = np.mean((centered / centered_std) ** 3, axis=0)
        kurtosis = np.mean((centered / centered_std) ** 4, axis=0) - 3.0
        abs_sum_change = np.sum(np.abs(diff), axis=0) if diff.size else np.zeros(sequence.shape[1], dtype=np.float32)
        mean_second_diff = (
            np.mean(np.abs(np.diff(sequence, n=2, axis=0)), axis=0)
            if sequence.shape[0] >= 3
            else np.zeros(sequence.shape[1], dtype=np.float32)
        )

        if sequence.shape[0] >= 3:
            middle = sequence[1:-1]
            peak_count = ((middle > sequence[:-2]) & (middle > sequence[2:])).sum(axis=0).astype(np.float32)
            peak_rate = peak_count / max(1.0, float(sequence.shape[0] - 2))
        else:
            peak_rate = np.zeros(sequence.shape[1], dtype=np.float32)

        if sequence.shape[0] >= 2:
            signs = np.sign(centered)
            zero_cross = ((signs[1:] * signs[:-1]) < 0).sum(axis=0).astype(np.float32)
            zero_cross_rate = zero_cross / max(1.0, float(sequence.shape[0] - 1))
            auto_num = (centered[:-1] * centered[1:]).sum(axis=0)
            auto_den = (centered * centered).sum(axis=0) + 1e-6
            autocorr_lag1 = auto_num / auto_den
        else:
            zero_cross_rate = np.zeros(sequence.shape[1], dtype=np.float32)
            autocorr_lag1 = np.zeros(sequence.shape[1], dtype=np.float32)

        spectrum = np.abs(np.fft.rfft(centered, axis=0)).astype(np.float32)
        if spectrum.shape[0] >= 2:
            low_band = spectrum[1 : min(3, spectrum.shape[0]), :].sum(axis=0)
            full_band = spectrum.sum(axis=0) + 1e-6
            low_freq_ratio = low_band / full_band
        else:
            low_freq_ratio = np.zeros(sequence.shape[1], dtype=np.float32)

        return np.concatenate(
            (
                cls._sequence_to_basic_features(sequence),
                slope.astype(np.float32),
                mean_abs_diff.astype(np.float32),
                max_abs_diff.astype(np.float32),
                energy.astype(np.float32),
                iqr.astype(np.float32),
                median.astype(np.float32),
                q10.astype(np.float32),
                q90.astype(np.float32),
                value_range.astype(np.float32),
                skewness.astype(np.float32),
                kurtosis.astype(np.float32),
                abs_sum_change.astype(np.float32),
                mean_second_diff.astype(np.float32),
                peak_rate.astype(np.float32),
                zero_cross_rate.astype(np.float32),
                autocorr_lag1.astype(np.float32),
                low_freq_ratio.astype(np.float32),
            )
        ).astype(np.float32, copy=False)

    def _component_probabilities(self, component: str, features: np.ndarray) -> np.ndarray:
        preprocessor = self._preprocessors[component]
        expected_dim = preprocessor["mean"].shape[0]
        if features.shape[1] != expected_dim:
            raise ValueError(f"Expected {expected_dim} tabular features for {component}, got {features.shape[1]}")
        scaled = (features - preprocessor["mean"]) / preprocessor["scale"]
        probabilities = np.asarray(self._models[component].predict(xgb.DMatrix(scaled)), dtype=np.float32)
        if probabilities.shape != (1, 4):
            raise ValueError(f"{component} returned invalid probability shape: {probabilities.shape}")
        return self._normalize(probabilities)[0]

    @staticmethod
    def _component(values: np.ndarray) -> dict[str, Any]:
        return {
            "probability": float(values[3]),
            "probabilities": values.tolist(),
        }

    def reset(self) -> None:
        return None

    def predict(self, enriched_sequence: np.ndarray) -> dict[str, Any]:
        started = time.perf_counter()
        sequence = np.asarray(enriched_sequence, dtype=np.float32)
        sequence = np.nan_to_num(sequence, nan=0.0, posinf=0.0, neginf=0.0)
        if sequence.shape != self.spec.expected_input_shape():
            raise ValueError(f"Expected Triple XGB sequence {self.spec.expected_input_shape()}, got {sequence.shape}")

        features = self._sequence_to_tsfresh_like_features(sequence).reshape(1, -1)
        component_probs = {
            component: self._component_probabilities(component, features)
            for component in COMPONENTS
        }
        fused_raw = np.zeros((1, 4), dtype=np.float32)
        for component, weight in self._weights.items():
            fused_raw += weight * component_probs[component].reshape(1, -1)
        probabilities = self._adjust(self._normalize(fused_raw))
        values = probabilities[0]
        prediction = int(np.argmax(values))
        focus_score = float(values[3])

        components = {
            component: self._component(component_probs[component])
            for component in COMPONENTS
        }
        return {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "label_space": LABEL_SPACE,
            "probability": focus_score,
            "focus_score": focus_score,
            "state": "ENGAGED" if prediction in ENGAGED_CLASS_INDICES else "DISTRACTED",
            "ready": True,
            "decision_rule": "argmax_4class",
            "weights": dict(self._weights),
            "components": components,
            "class_labels": list(CLASS_LABELS),
            "probabilities_4class": values.tolist(),
            "prediction_4class": prediction,
            "prediction_label": CLASS_LABELS[prediction],
            "engaged_class_indices": list(ENGAGED_CLASS_INDICES),
            "model_inference_latency_ms": (time.perf_counter() - started) * 1000.0,
            "sequence_length": SEQUENCE_LENGTH,
            "raw_feature_dim": RAW_FEATURE_DIM,
            "enriched_feature_dim": ENRICHED_FEATURE_DIM,
            "feature_mode": FEATURE_MODE,
            "feature_schema": "depth_robust_v2",
            "calibration": {
                "weights": dict(self._weights),
                "bias_vector": self._bias_vector.tolist() if self._bias_vector is not None else None,
                "temperature": self._temperature,
            },
        }


ProductInferencer = TripleXGBDepthRobustInferencer
