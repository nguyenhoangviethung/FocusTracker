from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any, Iterable

import joblib
import numpy as np

from utils.logger import get_logger
from utils.paths import resource_base_dir


logger = get_logger("inference")

MODEL_NAME = "deep_forest_product_4class"
MODEL_VERSION = "deep_forest_product_4class"
LABEL_SPACE = "daisee_4class"
CLASS_LABELS = ("very_low", "low", "medium", "high")
ENGAGED_CLASS_INDICES = (2, 3)
SEQUENCE_LENGTH = 30
RAW_FEATURE_DIM = 168
ENRICHED_FEATURE_DIM = 504
FEATURE_MODE = "basic"


@dataclass(frozen=True)
class DeepForestSpec:
    model_file: Path
    sequence_length: int = SEQUENCE_LENGTH
    raw_feature_dim: int = RAW_FEATURE_DIM
    enriched_feature_dim: int = ENRICHED_FEATURE_DIM
    feature_mode: str = FEATURE_MODE

    def expected_input_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.enriched_feature_dim

    def raw_sequence_shape(self) -> tuple[int, int]:
        return self.sequence_length, self.raw_feature_dim


class DeepForestInferencer:
    """CPU adapter for the calibrated two-layer DeepForest product bundle."""

    def __init__(self, model_dir: str | Path | None = None) -> None:
        configured_dir = os.getenv("FOCUSFLOW_DEEP_FOREST_MODEL_DIR", "").strip()
        self._model_dir = Path(model_dir or configured_dir or resource_base_dir() / "models" / MODEL_VERSION)
        model_file = self._model_dir / "model.joblib"
        if not model_file.exists():
            raise FileNotFoundError(
                f"DeepForest product artifact is missing: {model_file}. "
                "Download deep_forest_product_4class.zip from Hugging Face before starting the server."
            )

        logger.info("Loading calibrated DeepForest product bundle from %s", self._model_dir)
        artifact = joblib.load(model_file)
        self._layer1 = self._require_model_pair(artifact, "layer1")
        self._layer2 = self._require_model_pair(artifact, "layer2")
        self._selected_layer = int(artifact.get("selected_layer", 2))
        if self._selected_layer != 2:
            raise ValueError(f"DeepForest product requires selected_layer=2, got {self._selected_layer}")
        self._temperature = float(artifact.get("temperature", 1.25))
        self._prior_blend = float(artifact.get("prior_blend", 0.0))
        self._class_prior = np.asarray(artifact.get("class_prior", np.zeros(4)), dtype=np.float32)
        self._class_logit_biases = np.asarray(artifact.get("class_logit_biases", [1.5, 2.5, 0.0, 0.5]), dtype=np.float32)
        if self._temperature <= 0.0 or self._class_logit_biases.shape != (4,):
            raise ValueError("DeepForest calibration metadata is invalid.")
        self.spec = DeepForestSpec(model_file=model_file)

    @staticmethod
    def _require_model_pair(artifact: dict[str, Any], key: str) -> tuple[Any, Any]:
        models = artifact.get(key)
        if not isinstance(models, (list, tuple)) or len(models) != 2:
            raise ValueError(f"DeepForest artifact field '{key}' must contain ExtraTrees and RandomForest models.")
        if not all(hasattr(model, "predict_proba") for model in models):
            raise ValueError(f"DeepForest artifact field '{key}' is not a classifier pair.")
        return models[0], models[1]

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

    @staticmethod
    def _ordered_probabilities(model: Any, features: np.ndarray) -> np.ndarray:
        raw = np.asarray(model.predict_proba(features), dtype=np.float32)
        classes = np.asarray(getattr(model, "classes_", np.arange(raw.shape[1])), dtype=np.int64)
        result = np.zeros((features.shape[0], 4), dtype=np.float32)
        for index, class_id in enumerate(classes):
            if 0 <= int(class_id) < 4:
                result[:, int(class_id)] = raw[:, index]
        totals = result.sum(axis=1, keepdims=True)
        if np.any(totals <= 0.0):
            raise ValueError("DeepForest component returned an invalid probability vector.")
        return result / totals

    @classmethod
    def _pair_probabilities(cls, models: Iterable[Any], features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        individual = [cls._ordered_probabilities(model, features) for model in models]
        return np.concatenate(individual, axis=1), np.mean(individual, axis=0, dtype=np.float32)

    def _calibrate(self, probabilities: np.ndarray) -> np.ndarray:
        logits = np.log(np.clip(probabilities, 1e-12, 1.0)) / self._temperature
        logits += self._class_logit_biases.reshape(1, -1)
        if self._prior_blend:
            if self._class_prior.shape != (4,) or self._class_prior.sum() <= 0.0:
                raise ValueError("DeepForest prior-blend calibration is invalid.")
            logits += self._prior_blend * np.log(np.clip(self._class_prior, 1e-12, 1.0)).reshape(1, -1)
        logits -= logits.max(axis=1, keepdims=True)
        exp = np.exp(logits)
        return (exp / exp.sum(axis=1, keepdims=True)).astype(np.float32)

    @staticmethod
    def _component(probabilities: np.ndarray) -> dict[str, Any]:
        values = probabilities[0]
        return {
            "probability": float(values[2] + values[3]),
            "probabilities": values.tolist(),
        }

    def reset(self) -> None:
        return None

    def predict(self, enriched_sequence: np.ndarray) -> dict[str, Any]:
        started = time.perf_counter()
        sequence = np.asarray(enriched_sequence, dtype=np.float32)
        sequence = np.nan_to_num(sequence, nan=0.0, posinf=0.0, neginf=0.0)
        if sequence.shape != self.spec.expected_input_shape():
            raise ValueError(f"Expected DeepForest sequence {self.spec.expected_input_shape()}, got {sequence.shape}")

        features = self._sequence_to_basic_features(sequence).reshape(1, -1)
        expected_tabular_dim = ENRICHED_FEATURE_DIM * 7 + 1
        if features.shape[1] != expected_tabular_dim:
            raise ValueError(f"Expected {expected_tabular_dim} basic features, got {features.shape[1]}")

        layer1_features, layer1_probs = self._pair_probabilities(self._layer1, features)
        _, layer2_probs = self._pair_probabilities(self._layer2, np.concatenate((features, layer1_features), axis=1))
        probabilities = self._calibrate(layer2_probs)
        values = probabilities[0]
        prediction = int(np.argmax(values))
        focus_score = float(values[2] + values[3])

        components = {
            "layer1_extra_trees": self._component(self._ordered_probabilities(self._layer1[0], features)),
            "layer1_random_forest": self._component(self._ordered_probabilities(self._layer1[1], features)),
            "layer2_cascade": self._component(layer2_probs),
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
            "weights": {},
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
                "selected_layer": self._selected_layer,
                "temperature": self._temperature,
                "class_logit_biases": self._class_logit_biases.tolist(),
            },
        }
