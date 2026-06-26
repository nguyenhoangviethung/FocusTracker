from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import time

import numpy as np
import xgboost as xgb

from utils.logger import get_logger
from utils.paths import resource_base_dir

logger = get_logger("inference")

MODEL_NAME = "fixed_triple_xgb_fusion"
MODEL_VERSION = "product_4class_fixed_triple_xgb"
LABEL_SPACE = "daisee_4class"
CLASS_LABELS = ("very_low", "low", "medium", "high")
ENGAGED_CLASS_INDICES = (2, 3)

# Static bias vector from the product reproduction config:
# class_bias(validation_labels, power=0.42), validation counts [23, 143, 813, 450].
BIAS_VECTOR = np.array([2.0256370928321137, 0.9402561797523197, 0.4531576365407765, 0.58094909087479], dtype=np.float32)
TEMPERATURE = 1.15
WEIGHTS = {
    "final_xgb": 0.84,
    "boost_xgb": 0.14,
    "targeted_xgb": 0.02,
}

@dataclass(frozen=True)
class TripleXGBoostSpec:
    model_file: Path
    sequence_length: int
    raw_feature_dim: int
    enriched_feature_dim: int
    smoothing_window: int
    weights: dict[str, float]
    # Placeholders for compatibility
    gru_model_file: Path | None = None
    tcn_model_file: Path | None = None
    xgb_model_file: Path | None = None
    xgb_summary_file: Path | None = None
    xgb_preprocessor_file: Path | None = None
    gru_metadata_file: Path | None = None
    tcn_metadata_file: Path | None = None
    xgb_feature_mode: str = "tsfresh"

    def expected_input_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.enriched_feature_dim

    def raw_sequence_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.raw_feature_dim


class TripleXGBoostInferencer:
    """Four-class weighted-probability fusion over three XGBoost models.
    
    Loads three components: final_xgb, boost_xgb, and targeted_xgb.
    Generates tsfresh features from the (30, 90) enriched sequence,
    fuses prediction probabilities, applies validation-based class bias,
    and performs temperature calibration.
    """

    def __init__(
        self,
        model_file: str | Path | None = None,
        smoothing_window: int = 1,
    ) -> None:
        self.smoothing_window = max(1, int(smoothing_window))

        # Set model directory path
        if model_file:
            # If a model directory or file is passed, resolve its parent/directory
            model_path_obj = Path(model_file)
            if model_path_obj.is_file():
                self._model_dir = model_path_obj.parent
            else:
                self._model_dir = model_path_obj
        else:
            self._model_dir = resource_base_dir() / "models" / "product_4class_fixed_triple_xgb"

        logger.info(
            "Initializing 4-class multiclass model from %s (decision_rule=argmax_4class, smoothing_window=%s)",
            self._model_dir,
            self.smoothing_window,
        )

        # Load models and preprocessors
        self._models = {}
        self._preprocessors = {}

        components = ["final_xgb", "boost_xgb", "targeted_xgb"]
        for comp in components:
            comp_dir = self._model_dir / comp
            model_path = comp_dir / "model.json"
            prep_path = comp_dir / "preprocessor.npz"

            if not model_path.exists():
                raise FileNotFoundError(f"Model file not found: {model_path}")
            if not prep_path.exists():
                raise FileNotFoundError(f"Preprocessor file not found: {prep_path}")

            # Load booster
            booster = xgb.Booster()
            booster.load_model(str(model_path))
            self._models[comp] = booster

            # Load preprocessor
            prep_data = np.load(prep_path, allow_pickle=False)
            mean = prep_data["mean"]
            scale = prep_data["scale"]
            if mean.shape != scale.shape:
                raise ValueError(f"Preprocessor mean/scale shape mismatch for {comp}: {mean.shape} != {scale.shape}")
            self._preprocessors[comp] = {
                "mean": mean,
                "scale": scale,
            }

        # Setup compatibility Spec
        self.spec = TripleXGBoostSpec(
            model_file=self._model_dir / "final_xgb" / "model.json",
            sequence_length=30,
            raw_feature_dim=30,
            enriched_feature_dim=90,
            smoothing_window=self.smoothing_window,
            weights=dict(WEIGHTS),
        )

        logger.info("4-class multiclass models successfully loaded.")

    @staticmethod
    def _normalize(probabilities: np.ndarray) -> np.ndarray:
        probabilities = probabilities.astype(np.float64)
        probabilities /= np.clip(probabilities.sum(axis=-1, keepdims=True), 1e-12, None)
        return probabilities.astype(np.float32)

    @staticmethod
    def _adjust(probabilities: np.ndarray, bias: np.ndarray | None, temperature: float) -> np.ndarray:
        adjusted = probabilities.astype(np.float64)
        if bias is not None:
            adjusted *= bias.reshape(1, -1)
        if temperature != 1.0:
            adjusted = np.power(np.clip(adjusted, 1e-12, None), 1.0 / temperature)
        return TripleXGBoostInferencer._normalize(adjusted)

    @staticmethod
    def _sequence_to_basic_features(sequence: np.ndarray) -> np.ndarray:
        first_frame = sequence[0]
        last_frame = sequence[-1]
        return np.concatenate(
            [
                sequence.mean(axis=0),
                sequence.std(axis=0),
                sequence.min(axis=0),
                sequence.max(axis=0),
                first_frame,
                last_frame,
                last_frame - first_frame,
                np.array([float(sequence.shape[0])], dtype=np.float32),
            ]
        ).astype(np.float32)

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
            [
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
            ]
        ).astype(np.float32)

    @classmethod
    def _sequence_to_tabular_features(cls, sequence: np.ndarray, feature_mode: str = "tsfresh") -> np.ndarray:
        sequence = np.asarray(sequence, dtype=np.float32)
        if sequence.ndim == 1:
            sequence = sequence[:, None]

        sequence = np.nan_to_num(sequence, nan=0.0, posinf=0.0, neginf=0.0)
        mode = feature_mode.lower().strip()
        if mode == "basic":
            return cls._sequence_to_basic_features(sequence)
        if mode == "tsfresh":
            return cls._sequence_to_tsfresh_like_features(sequence)
        raise ValueError(f"Unsupported feature mode: {feature_mode}")

    def reset(self) -> None:
        return None

    def predict(self, enriched_chunk: np.ndarray) -> dict[str, Any]:
        started = time.perf_counter()
        chunk = np.asarray(enriched_chunk, dtype=np.float32)
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)
        expected_shape = self.spec.expected_input_shape()
        if chunk.shape != expected_shape:
            raise ValueError(f"Expected chunk shape {expected_shape}, got {chunk.shape}")

        # Extract features (2161 dim)
        features = self._sequence_to_tabular_features(chunk, feature_mode="tsfresh").reshape(1, -1)

        # Get probabilities for each component
        comp_probs = {}
        for comp in ["final_xgb", "boost_xgb", "targeted_xgb"]:
            prep = self._preprocessors[comp]
            if features.shape[1] != prep["mean"].shape[0]:
                raise ValueError(
                    f"Expected {prep['mean'].shape[0]} tabular features for {comp}, got {features.shape[1]}"
                )
            x_scaled = (features - prep["mean"]) / prep["scale"]
            dmat = xgb.DMatrix(x_scaled)
            # DMatrix prediction shape is (1, 4)
            prob_raw = self._models[comp].predict(dmat)
            comp_probs[comp] = prob_raw[0]  # shape (4,)

        # Late-fusion weighted probability sum
        fused_raw = (
            WEIGHTS["final_xgb"] * comp_probs["final_xgb"]
            + WEIGHTS["boost_xgb"] * comp_probs["boost_xgb"]
            + WEIGHTS["targeted_xgb"] * comp_probs["targeted_xgb"]
        )
        normalized = self._normalize(fused_raw.reshape(1, -1))
        adjusted = self._adjust(normalized, bias=BIAS_VECTOR, temperature=TEMPERATURE)

        # Output predictions
        probs = adjusted[0].tolist()
        pred_class = int(np.argmax(adjusted, axis=-1)[0])

        # Continuous focus score is telemetry only. The 4-class prediction uses argmax.
        raw_focus_score = float(probs[2] + probs[3])
        state = "ENGAGED" if pred_class in ENGAGED_CLASS_INDICES else "DISTRACTED"

        # Populate components structure for the UI
        components = {
            "final_xgb": {
                "probability": float(comp_probs["final_xgb"][2] + comp_probs["final_xgb"][3]),
                "probabilities": comp_probs["final_xgb"].tolist()
            },
            "boost_xgb": {
                "probability": float(comp_probs["boost_xgb"][2] + comp_probs["boost_xgb"][3]),
                "probabilities": comp_probs["boost_xgb"].tolist()
            },
            "targeted_xgb": {
                "probability": float(comp_probs["targeted_xgb"][2] + comp_probs["targeted_xgb"][3]),
                "probabilities": comp_probs["targeted_xgb"].tolist()
            }
        }

        return {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "label_space": LABEL_SPACE,
            "probability": raw_focus_score,
            "raw_probability": raw_focus_score,
            "focus_score": raw_focus_score,
            "state": state,
            "ready": True,
            "decision_rule": "argmax_4class",
            "weights": dict(WEIGHTS),
            "components": components,
            "class_labels": list(CLASS_LABELS),
            "probabilities_4class": probs,
            "prediction_4class": pred_class,
            "prediction_label": CLASS_LABELS[pred_class],
            "engaged_class_indices": list(ENGAGED_CLASS_INDICES),
            "model_inference_latency_ms": (time.perf_counter() - started) * 1000.0,
            "sequence_length": self.spec.sequence_length,
            "raw_feature_dim": self.spec.raw_feature_dim,
            "enriched_feature_dim": self.spec.enriched_feature_dim,
            "feature_mode": "tsfresh",
        }


# Backward-compatible aliases for legacy callers. New code should use the
# names above because the production artifact does not execute ONNX models.
LateFusionSpec = TripleXGBoostSpec
ONNXEngagementInferencer = TripleXGBoostInferencer
