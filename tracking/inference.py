from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from utils.logger import get_logger
from utils.paths import (
    late_fusion_gru_metadata_path,
    late_fusion_gru_model_path,
    late_fusion_report_path,
    late_fusion_tcn_metadata_path,
    late_fusion_tcn_model_path,
    late_fusion_xgb_model_path,
    late_fusion_xgb_preprocessor_path,
    late_fusion_xgb_summary_path,
    model_path,
)

logger = get_logger("inference")


DEFAULT_THRESHOLD = 0.54
DEFAULT_WEIGHTS = {
    "gru": 0.30,
    "tcn": 0.30,
    "xgboost": 0.40,
}
MODEL_NAME = "late_fusion_gru_tcn_xgb"
MODEL_VERSION = "20260608"


@dataclass(frozen=True)
class LateFusionSpec:
    model_file: Path
    sequence_length: int
    raw_feature_dim: int
    enriched_feature_dim: int
    threshold: float
    smoothing_window: int
    weights: dict[str, float]
    gru_model_file: Path
    tcn_model_file: Path
    xgb_model_file: Path
    xgb_summary_file: Path
    xgb_preprocessor_file: Path
    gru_metadata_file: Path
    tcn_metadata_file: Path
    xgb_feature_mode: str = "tsfresh"

    def expected_input_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.enriched_feature_dim

    def raw_sequence_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.raw_feature_dim


class ONNXEngagementInferencer:
    """Late-fusion engagement inferencer for GRU + TCN + XGBoost.

    The class keeps the historic name used by the app, but the runtime now
    loads the bundled late-fusion ensemble and returns the fused probability.
    """

    def __init__(
        self,
        model_file: str | Path | None = None,
        threshold: float = DEFAULT_THRESHOLD,
        smoothing_window: int = 1,
    ) -> None:
        resolved_model = Path(model_file) if model_file else late_fusion_gru_model_path()
        if not resolved_model.exists():
            resolved_model = model_path()
        self._artifact_dir = resolved_model.parent
        logger.info(
            "Initializing late-fusion inferencer (model=%s, threshold=%s, smoothing_window=%s)",
            resolved_model,
            threshold,
            smoothing_window,
        )

        self._report = self._read_json(self._resolve_report_path())
        selected = self._report.get("selected", {}) if isinstance(self._report, dict) else {}
        report_weights = selected.get("weights", {}) if isinstance(selected, dict) else {}

        gru_model = self._resolve_component_path(late_fusion_gru_model_path().name)
        tcn_model = self._resolve_component_path(late_fusion_tcn_model_path().name)
        xgb_model = self._resolve_component_path(late_fusion_xgb_model_path().name)
        xgb_summary = self._resolve_component_path(late_fusion_xgb_summary_path().name)
        xgb_preprocessor = self._resolve_component_path(late_fusion_xgb_preprocessor_path().name)
        gru_metadata = self._resolve_component_path(late_fusion_gru_metadata_path().name)
        tcn_metadata = self._resolve_component_path(late_fusion_tcn_metadata_path().name)

        if not gru_model.exists():
            raise FileNotFoundError(f"GRU artifact not found at {gru_model}")
        if not tcn_model.exists():
            raise FileNotFoundError(f"TCN artifact not found at {tcn_model}")
        if not xgb_model.exists():
            raise FileNotFoundError(f"XGBoost artifact not found at {xgb_model}")
        if not xgb_summary.exists():
            raise FileNotFoundError(f"XGBoost summary not found at {xgb_summary}")
        if not xgb_preprocessor.exists():
            raise FileNotFoundError(f"XGBoost preprocessor not found at {xgb_preprocessor}")
        if not gru_metadata.exists():
            raise FileNotFoundError(f"GRU metadata not found at {gru_metadata}")
        if not tcn_metadata.exists():
            raise FileNotFoundError(f"TCN metadata not found at {tcn_metadata}")

        self._gru_metadata = self._read_json(gru_metadata)
        self._tcn_metadata = self._read_json(tcn_metadata)
        self._xgb_summary = self._read_json(xgb_summary)
        self._xgb_preprocessor = self._load_npz_preprocessor(xgb_preprocessor)
        self._gru_normalizer = self._resolve_sequence_normalizer(self._gru_metadata, "GRU")
        self._tcn_normalizer = self._resolve_sequence_normalizer(self._tcn_metadata, "TCN")

        self._weight_map = self._resolve_weights(report_weights)
        self.threshold = self._resolve_threshold(threshold, selected)
        self.smoothing_window = max(1, int(smoothing_window))

        self.spec = LateFusionSpec(
            model_file=gru_model,
            sequence_length=self._resolve_int(
                self._gru_metadata.get("sequence_length"),
                self._tcn_metadata.get("sequence_length"),
                30,
            ),
            raw_feature_dim=self._resolve_int(
                self._gru_metadata.get("raw_feature_dim"),
                self._tcn_metadata.get("raw_feature_dim"),
                30,
            ),
            enriched_feature_dim=self._resolve_int(
                self._gru_metadata.get("enriched_feature_dim"),
                self._tcn_metadata.get("enriched_feature_dim"),
                90,
            ),
            threshold=self.threshold,
            smoothing_window=self.smoothing_window,
            weights=dict(self._weight_map),
            gru_model_file=gru_model,
            tcn_model_file=tcn_model,
            xgb_model_file=xgb_model,
            xgb_summary_file=xgb_summary,
            xgb_preprocessor_file=xgb_preprocessor,
            gru_metadata_file=gru_metadata,
            tcn_metadata_file=tcn_metadata,
        )

        self._gru_temperature, self._gru_calibration = self._resolve_component_calibration(self._gru_metadata)
        self._tcn_temperature, self._tcn_calibration = self._resolve_component_calibration(self._tcn_metadata)
        self._xgb_threshold = self._resolve_float(self._xgb_summary.get("selected_threshold"), 0.49)
        self._xgb_feature_mode = str(self._xgb_summary.get("feature_mode") or "tsfresh")

        self._gru_session, self._gru_input_name = self._load_onnx_session(gru_model)
        self._tcn_session, self._tcn_input_name = self._load_onnx_session(tcn_model)

        self._xgb_model, self._xgb_backend = self._load_tree_model(xgb_model)
        self._probability_history: deque[float] = deque(maxlen=self.smoothing_window)

        logger.info(
            "Late-fusion inferencer ready: input=%sx%s, threshold=%.3f, weights=%s",
            self.spec.sequence_length,
            self.spec.enriched_feature_dim,
            self.threshold,
            self._weight_map,
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to read JSON artifact at {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"JSON artifact must contain an object: {path}")
        return payload

    def _resolve_report_path(self) -> Path:
        candidate = late_fusion_report_path()
        if candidate.exists():
            return candidate
        return self._artifact_dir / candidate.name

    def _resolve_component_path(self, filename: str) -> Path:
        candidate = self._artifact_dir / filename
        if candidate.exists():
            return candidate
        fallback = Path(filename)
        if fallback.exists():
            return fallback
        return candidate

    @staticmethod
    def _resolve_int(*values: Any) -> int:
        for value in values:
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        raise ValueError("Unable to resolve integer model metadata")

    @staticmethod
    def _resolve_float(*values: Any) -> float:
        for value in values:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        raise ValueError("Unable to resolve float model metadata")

    def _resolve_threshold(self, threshold: float, selected: dict[str, Any]) -> float:
        if threshold is not None:
            return float(threshold)
        if isinstance(selected, dict) and "threshold" in selected:
            try:
                return float(selected["threshold"])
            except (TypeError, ValueError):
                pass
        return DEFAULT_THRESHOLD

    def _resolve_weights(self, report_weights: dict[str, Any]) -> dict[str, float]:
        weights = dict(DEFAULT_WEIGHTS)
        for key, value in report_weights.items():
            if key not in weights:
                continue
            try:
                weights[key] = float(value)
            except (TypeError, ValueError):
                continue
        total = sum(weights.values())
        if total <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {name: weight / total for name, weight in weights.items()}

    @staticmethod
    def _load_npz_preprocessor(path: Path) -> dict[str, Any]:
        payload = np.load(path, allow_pickle=False)
        config: dict[str, Any] = {key: payload[key] for key in payload.files}
        config["dim_reduction"] = str(config["dim_reduction"].item()) if "dim_reduction" in config else "none"
        return config

    @staticmethod
    def _resolve_component_calibration(metadata: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        temperature = 1.0
        calibration: dict[str, Any] = {}
        if isinstance(metadata, dict):
            try:
                temperature = float(metadata.get("best_temperature", 1.0))
            except (TypeError, ValueError):
                temperature = 1.0
            raw_calibration = metadata.get("prior_shift_calibration")
            if isinstance(raw_calibration, dict):
                calibration = dict(raw_calibration)
        return temperature, calibration

    @staticmethod
    def _resolve_sequence_normalizer(metadata: dict[str, Any], component_name: str) -> tuple[np.ndarray, np.ndarray] | None:
        if not bool(metadata.get("normalize_features", False)):
            return None

        mean_raw = metadata.get("feature_mean")
        std_raw = metadata.get("feature_std")
        if not isinstance(mean_raw, list) or not isinstance(std_raw, list):
            raise ValueError(
                f"{component_name} metadata requires feature_mean/feature_std because normalize_features=true."
            )

        mean = np.asarray(mean_raw, dtype=np.float32)
        std = np.asarray(std_raw, dtype=np.float32)
        if mean.ndim != 1 or std.ndim != 1 or mean.shape != std.shape:
            raise ValueError(f"{component_name} feature normalizer must be matching 1D vectors.")
        std = np.where(np.abs(std) < 1e-6, 1.0, std).astype(np.float32)
        return mean, std

    @staticmethod
    def _apply_sequence_normalizer(chunk: np.ndarray, normalizer: tuple[np.ndarray, np.ndarray] | None) -> np.ndarray:
        if normalizer is None:
            return chunk.astype(np.float32, copy=False)
        mean, std = normalizer
        if chunk.shape[-1] != mean.shape[0]:
            raise ValueError(f"Normalizer dim {mean.shape[0]} does not match chunk feature dim {chunk.shape[-1]}")
        return ((chunk - mean.reshape(1, -1)) / std.reshape(1, -1)).astype(np.float32)

    @staticmethod
    def _load_onnx_session(model_file: Path) -> tuple[ort.InferenceSession, str]:
        session = ort.InferenceSession(str(model_file), providers=["CPUExecutionProvider"])
        inputs = session.get_inputs()
        if not inputs:
            raise ValueError(f"ONNX model has no inputs: {model_file}")
        return session, inputs[0].name

    @staticmethod
    def _load_tree_model(model_file: Path):
        try:
            import xgboost as xgb
        except Exception as exc:  # pragma: no cover - import guard
            raise ImportError(
                "xgboost is required for late-fusion inference. Install the runtime requirements first."
            ) from exc

        model = xgb.Booster()
        model.load_model(str(model_file))
        return model, "xgboost"

    @staticmethod
    def _sigmoid(value: float) -> float:
        clipped = float(np.clip(value, -60.0, 60.0))
        return float(1.0 / (1.0 + np.exp(-clipped)))

    @staticmethod
    def _logit(probability: float) -> float:
        clipped = float(np.clip(probability, 1e-6, 1.0 - 1e-6))
        return float(np.log(clipped / (1.0 - clipped)))

    def _calibrate_probability(
        self,
        probability: float,
        *,
        temperature: float,
        calibration: dict[str, Any],
    ) -> float:
        temperature = max(1e-3, float(temperature))
        calibrated = self._sigmoid(self._logit(probability) / temperature)

        if not bool(calibration.get("enabled", False)):
            return calibrated

        source_prior = calibration.get("source_pos_prior")
        target_prior = calibration.get("target_pos_prior")
        if source_prior is None or target_prior is None:
            return calibrated

        source = float(np.clip(float(source_prior), 1e-4, 1.0 - 1e-4))
        target = float(np.clip(float(target_prior), 1e-4, 1.0 - 1e-4))
        if math.isclose(source, target, rel_tol=0.0, abs_tol=1e-8):
            return calibrated

        source_odds = source / (1.0 - source)
        target_odds = target / (1.0 - target)
        odds_multiplier = target_odds / source_odds
        odds = calibrated / (1.0 - calibrated)
        adjusted = odds * odds_multiplier
        return float(np.clip(adjusted / (1.0 + adjusted), 1e-6, 1.0 - 1e-6))

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
        raise ValueError(f"Unsupported feature mode for late fusion XGBoost: {feature_mode}")

    def _apply_feature_preprocessor(self, x: np.ndarray) -> np.ndarray:
        config = self._xgb_preprocessor
        x = np.asarray(x, dtype=np.float32)
        x_scaled = (x - config["mean"]) / config["scale"]
        dim_reduction = str(config.get("dim_reduction", "none"))
        if dim_reduction == "none":
            return x_scaled.astype(np.float32)

        centered = x_scaled
        if dim_reduction == "pca" and "reducer_mean" in config:
            centered = centered - config["reducer_mean"]
        return (centered @ config["components"].T).astype(np.float32)

    def _predict_component_probability(
        self,
        session: ort.InferenceSession,
        input_name: str,
        chunk: np.ndarray,
        *,
        temperature: float,
        calibration: dict[str, Any],
    ) -> float:
        data = chunk[np.newaxis, :, :].astype(np.float32, copy=False)
        outputs = session.run(None, {input_name: data})
        raw = float(np.asarray(outputs[0]).reshape(-1)[0])
        return self._calibrate_probability(raw, temperature=temperature, calibration=calibration)

    def _predict_xgboost_probability(self, enriched_chunk: np.ndarray) -> float:
        features = self._sequence_to_tabular_features(enriched_chunk, feature_mode=self._xgb_feature_mode).reshape(1, -1)
        features = self._apply_feature_preprocessor(features)
        import xgboost as xgb

        probability = float(self._xgb_model.predict(xgb.DMatrix(features))[0])
        return probability

    def reset(self) -> None:
        """Kept for interface compatibility; late fusion itself is stateless."""
        self._probability_history.clear()
        return None

    def predict(self, enriched_chunk: np.ndarray) -> dict[str, float | str | dict[str, Any]]:
        chunk = np.asarray(enriched_chunk, dtype=np.float32)
        chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)
        expected_shape = self.spec.expected_input_shape()
        if chunk.shape != expected_shape:
            raise ValueError(f"Expected chunk shape {expected_shape}, got {chunk.shape}")

        logger.debug("Running late-fusion inference on chunk shape %s", chunk.shape)

        gru_chunk = self._apply_sequence_normalizer(chunk, self._gru_normalizer)
        tcn_chunk = self._apply_sequence_normalizer(chunk, self._tcn_normalizer)

        gru_probability = self._predict_component_probability(
            self._gru_session,
            self._gru_input_name,
            gru_chunk,
            temperature=self._gru_temperature,
            calibration=self._gru_calibration,
        )
        tcn_probability = self._predict_component_probability(
            self._tcn_session,
            self._tcn_input_name,
            tcn_chunk,
            temperature=self._tcn_temperature,
            calibration=self._tcn_calibration,
        )
        xgb_probability = self._predict_xgboost_probability(chunk)

        late_fusion_probability = (
            self._weight_map["gru"] * gru_probability
            + self._weight_map["tcn"] * tcn_probability
            + self._weight_map["xgboost"] * xgb_probability
        )
        late_fusion_probability = float(np.clip(late_fusion_probability, 0.0, 1.0))

        gru_threshold = self._resolve_float(self._gru_metadata.get("best_threshold"), 0.63)
        tcn_threshold = self._resolve_float(self._tcn_metadata.get("best_threshold"), 0.61)
        neural_probability = float(np.clip((gru_probability + tcn_probability) / 2.0, 0.0, 1.0))
        neural_consensus = gru_probability >= gru_threshold and tcn_probability >= tcn_threshold
        if neural_consensus:
            # In live webcam use, XGBoost is useful as a conservative guard, but it
            # can be under-calibrated for a user's own camera/background. When both
            # neural temporal models agree strongly, keep XGB as telemetry instead
            # of letting it suppress the engagement score.
            selected_probability = max(late_fusion_probability, neural_probability)
            fusion_strategy = "neural_consensus_guarded"
        else:
            selected_probability = late_fusion_probability
            fusion_strategy = "late_fusion"

        self._probability_history.append(selected_probability)
        fused_probability = float(np.mean(self._probability_history, dtype=np.float64))
        state = "ENGAGED" if fused_probability >= self.threshold else "DISTRACTED"

        components = {
            "gru": {
                "probability": gru_probability,
                "threshold": gru_threshold,
                "state": "ENGAGED" if gru_probability >= gru_threshold else "DISTRACTED",
            },
            "tcn": {
                "probability": tcn_probability,
                "threshold": tcn_threshold,
                "state": "ENGAGED" if tcn_probability >= tcn_threshold else "DISTRACTED",
            },
            "xgboost": {
                "probability": xgb_probability,
                "threshold": self._xgb_threshold,
                "state": "ENGAGED" if xgb_probability >= self._xgb_threshold else "DISTRACTED",
            },
        }

        logger.debug(
            "Late-fusion result: gru=%.4f tcn=%.4f xgb=%.4f fused=%.4f threshold=%.4f state=%s",
            gru_probability,
            tcn_probability,
            xgb_probability,
            fused_probability,
            self.threshold,
            state,
        )

        return {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "probability": fused_probability,
            "raw_probability": selected_probability,
            "late_fusion_probability": late_fusion_probability,
            "neural_probability": neural_probability,
            "fusion_strategy": fusion_strategy,
            "focus_score": fused_probability,
            "state": state,
            "ready": True,
            "threshold": self.threshold,
            "weights": dict(self._weight_map),
            "components": components,
            "sequence_length": self.spec.sequence_length,
            "raw_feature_dim": self.spec.raw_feature_dim,
            "enriched_feature_dim": self.spec.enriched_feature_dim,
            "feature_mode": self._xgb_feature_mode,
            "artifact_dir": str(self._artifact_dir),
            "model_file": str(self.spec.model_file),
        }
