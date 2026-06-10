from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import onnxruntime as ort

from utils.paths import model_path, resource_base_dir
from utils.logger import get_logger


logger = get_logger("model_spec")


@dataclass(frozen=True)
class ModelSpec:
    model_file: Path
    sequence_length: int
    raw_feature_dim: int
    enriched_feature_dim: int
    threshold: float
    smoothing_window: int
    normalize_features: bool = False
    feature_mean: list[float] | None = None
    feature_std: list[float] | None = None
    best_temperature: float = 1.0
    prior_shift_calibration: dict[str, Any] | None = None

    @property
    def metadata_path(self) -> Path:
        return self.model_file.with_suffix(".json")

    @classmethod
    def load(
        cls,
        model_file: str | Path | None = None,
        threshold: float | None = None,
        smoothing_window: int | None = None,
    ) -> "ModelSpec":
        resolved_model = Path(model_file) if model_file else model_path()
        logger.debug("Loading ModelSpec from %s", resolved_model)
        metadata = cls._read_metadata(resolved_model)
        signature = cls._read_onnx_signature(resolved_model)

        sequence_length = cls._coerce_int(
            metadata.get("sequence_length"),
            metadata.get("sequence_len"),
            signature.get("sequence_length"),
            60,
        )
        enriched_feature_dim = cls._coerce_int(
            metadata.get("enriched_feature_dim"),
            metadata.get("input_size"),
            metadata.get("feature_dim"),
            signature.get("enriched_feature_dim"),
            90,
        )
        raw_feature_dim = cls._coerce_int(
            metadata.get("raw_feature_dim"),
            metadata.get("frame_feature_dim"),
            30,
        )

        threshold_value = cls._coerce_float(
            threshold,
            metadata.get("threshold"),
            metadata.get("best_threshold"),
            0.54,
        )
        smoothing_value = cls._coerce_int(
            smoothing_window,
            metadata.get("smoothing_window"),
            5,
        )
        normalize_features = bool(metadata.get("normalize_features", False))
        feature_mean = metadata.get("feature_mean")
        feature_std = metadata.get("feature_std")
        if not isinstance(feature_mean, list):
            feature_mean = None
        if not isinstance(feature_std, list):
            feature_std = None
        best_temperature = cls._coerce_float(metadata.get("best_temperature"), 1.0)
        prior_shift_calibration = metadata.get("prior_shift_calibration")
        if not isinstance(prior_shift_calibration, dict):
            prior_shift_calibration = {}

        if raw_feature_dim <= 0 and enriched_feature_dim % 3 == 0:
            raw_feature_dim = enriched_feature_dim // 3

        logger.debug(
            "Resolved spec: sequence_length=%s, raw_feature_dim=%s, enriched_feature_dim=%s, threshold=%.3f, smoothing_window=%s",
            sequence_length,
            raw_feature_dim,
            enriched_feature_dim,
            threshold_value,
            smoothing_value,
        )

        return cls(
            model_file=resolved_model,
            sequence_length=sequence_length,
            raw_feature_dim=raw_feature_dim,
            enriched_feature_dim=enriched_feature_dim,
            threshold=threshold_value,
            smoothing_window=max(1, smoothing_value),
            normalize_features=normalize_features,
            feature_mean=feature_mean,
            feature_std=feature_std,
            best_temperature=best_temperature,
            prior_shift_calibration=prior_shift_calibration,
        )

    @classmethod
    def _read_metadata(cls, resolved_model: Path) -> dict[str, Any]:
        metadata_path = resolved_model.with_suffix(".json")
        candidates = [
            metadata_path,
            resource_base_dir() / "training" / "checkpoints" / "engagement_gru.json",
            resource_base_dir() / "train_2" / "engagement_gru.json",
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue

            logger.debug("Reading model metadata from %s", candidate)

            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.debug("Failed to parse metadata from %s", candidate, exc_info=True)
                continue

            if isinstance(payload, dict):
                return payload

        return {}

    @classmethod
    def _read_onnx_signature(cls, resolved_model: Path) -> dict[str, int]:
        try:
            session = ort.InferenceSession(str(resolved_model), providers=["CPUExecutionProvider"])
        except Exception:
            logger.debug("Failed to read ONNX signature from %s", resolved_model, exc_info=True)
            return {}

        inputs = session.get_inputs()
        if not inputs:
            return {}

        shape = list(inputs[0].shape)
        signature: dict[str, int] = {}
        if len(shape) >= 2 and isinstance(shape[1], int):
            signature["sequence_length"] = int(shape[1])
        if len(shape) >= 3 and isinstance(shape[2], int):
            signature["enriched_feature_dim"] = int(shape[2])
        logger.debug("ONNX signature resolved: %s", signature)
        return signature

    @staticmethod
    def _coerce_int(*values: Any) -> int:
        for value in values:
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        raise ValueError("Could not resolve an integer model spec value.")

    @staticmethod
    def _coerce_float(*values: Any) -> float:
        for value in values:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        raise ValueError("Could not resolve a float model spec value.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_file": str(self.model_file),
            "sequence_length": self.sequence_length,
            "raw_feature_dim": self.raw_feature_dim,
            "enriched_feature_dim": self.enriched_feature_dim,
            "threshold": self.threshold,
            "smoothing_window": self.smoothing_window,
            "normalize_features": self.normalize_features,
            "feature_mean": self.feature_mean,
            "feature_std": self.feature_std,
            "best_temperature": self.best_temperature,
            "prior_shift_calibration": self.prior_shift_calibration or {},
        }

    def save_metadata(self, extra: dict[str, Any] | None = None) -> Path:
        payload = self.to_dict()
        if extra:
            payload.update(extra)

        self.metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.metadata_path

    def expected_input_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.enriched_feature_dim

    def raw_sequence_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.raw_feature_dim
