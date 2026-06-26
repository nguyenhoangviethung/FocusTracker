from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

import cv2
import numpy as np

os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")

import mediapipe as mp
from mediapipe.tasks.python.core import base_options as base_options_lib
from mediapipe.tasks.python.vision import face_landmarker as face_landmarker_lib
from mediapipe.tasks.python.vision.core import image as image_lib
from mediapipe.tasks.python.vision.core import vision_task_running_mode as running_mode_lib

from utils.logger import get_logger
from utils.paths import resource_base_dir


logger = get_logger("detector")

LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]
DRAW_LANDMARKS = [33, 133, 362, 263, 61, 291, 13, 14]
DEPTH_ROBUST_LANDMARKS = [
    1, 4, 10, 33, 46, 52, 61, 78, 93, 133, 152, 159, 168,
    172, 197, 234, 263, 276, 282, 291, 308, 323, 362, 386, 454,
]
SCALAR_FEATURE_DIM = 25
BLENDSHAPE_DIM = 52
TRANSFORM_DIM = 16
VALIDITY_INDEX = 24
FRAME_FEATURE_DIM = SCALAR_FEATURE_DIM + len(DEPTH_ROBUST_LANDMARKS) * 3 + BLENDSHAPE_DIM + TRANSFORM_DIM
FEATURE_CLIP = 100.0


@dataclass
class DetectionResult:
    frame: np.ndarray
    feature: np.ndarray
    face_found: bool


class FaceFeatureDetector:
    """Extract the production depth_robust_v2 168-D feature schema per frame."""

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        draw_landmarks: bool = True,
        expected_feature_dim: int = FRAME_FEATURE_DIM,
        camera_distance_scale: float = 0.18,
    ) -> None:
        self.draw_landmarks = draw_landmarks
        self.expected_feature_dim = int(expected_feature_dim)
        # Retained only so persisted client settings remain compatible. The
        # depth-robust schema derives scale from landmarks rather than this UI knob.
        self.camera_distance_scale = float(camera_distance_scale)
        self._closed = False
        self._model_path = self._resolve_model_path()

        options = face_landmarker_lib.FaceLandmarkerOptions(
            base_options=base_options_lib.BaseOptions(
                model_asset_path=str(self._model_path),
                delegate=base_options_lib.BaseOptions.Delegate.CPU,
            ),
            running_mode=running_mode_lib.VisionTaskRunningMode.IMAGE,
            num_faces=max_num_faces,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._face_landmarker = face_landmarker_lib.FaceLandmarker.create_from_options(options)
        logger.info("FaceFeatureDetector initialized with depth_robust_v2 schema (%dD)", FRAME_FEATURE_DIM)

    @staticmethod
    def _resolve_model_path() -> Path:
        candidate = resource_base_dir() / "models" / "face_landmarker.task"
        if not candidate.exists():
            raise FileNotFoundError(f"FaceLandmarker model not found at {candidate}.")
        return candidate

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._face_landmarker.close()
        except Exception:
            logger.warning("Detector close raised exception", exc_info=True)
        finally:
            self._face_landmarker = None

    @staticmethod
    def _point(landmarks, index: int):
        return landmarks.landmark[index] if hasattr(landmarks, "landmark") else landmarks[index]

    @classmethod
    def _xy(cls, landmarks, index: int, aspect: float) -> np.ndarray:
        point = cls._point(landmarks, index)
        return np.asarray([point.x * aspect, point.y], dtype=np.float32)

    @classmethod
    def _xyz(cls, landmarks, index: int, aspect: float) -> np.ndarray:
        point = cls._point(landmarks, index)
        return np.asarray([point.x * aspect, point.y, point.z * aspect], dtype=np.float32)

    @staticmethod
    def _distance(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    @classmethod
    def _eye_aspect_ratio(cls, landmarks, indices: list[int], aspect: float) -> float:
        points = [cls._xy(landmarks, index, aspect) for index in indices]
        vertical = cls._distance(points[1], points[5]) + cls._distance(points[2], points[4])
        horizontal = 2.0 * cls._distance(points[0], points[3]) + 1e-6
        return vertical / horizontal

    @classmethod
    def _mouth_aspect_ratio(cls, landmarks, aspect: float) -> float:
        return cls._distance(cls._xy(landmarks, 13, aspect), cls._xy(landmarks, 14, aspect)) / (
            cls._distance(cls._xy(landmarks, 61, aspect), cls._xy(landmarks, 291, aspect)) + 1e-6
        )

    @classmethod
    def _iris_diameter(cls, landmarks, indices: tuple[int, int, int, int], aspect: float) -> float:
        landmark_count = len(landmarks.landmark) if hasattr(landmarks, "landmark") else len(landmarks)
        if landmark_count <= max(indices):
            return 0.0
        horizontal = cls._distance(cls._xy(landmarks, indices[0], aspect), cls._xy(landmarks, indices[1], aspect))
        vertical = cls._distance(cls._xy(landmarks, indices[2], aspect), cls._xy(landmarks, indices[3], aspect))
        return 0.5 * (horizontal + vertical)

    @staticmethod
    def _blendshape_vector(face_blendshapes) -> np.ndarray:
        if not face_blendshapes:
            return np.zeros(BLENDSHAPE_DIM, dtype=np.float32)
        categories = face_blendshapes[0] if isinstance(face_blendshapes, list) else face_blendshapes
        ordered = sorted(categories, key=lambda item: str(getattr(item, "category_name", "")))
        scores = [float(getattr(item, "score", 0.0)) for item in ordered]
        return np.asarray((scores + [0.0] * BLENDSHAPE_DIM)[:BLENDSHAPE_DIM], dtype=np.float32)

    @staticmethod
    def _transform_vector(matrices) -> np.ndarray:
        if not matrices:
            return np.zeros(TRANSFORM_DIM, dtype=np.float32)
        matrix = matrices[0]
        values = np.asarray(getattr(matrix, "data", matrix), dtype=np.float32).reshape(-1)
        result = np.zeros(TRANSFORM_DIM, dtype=np.float32)
        result[: min(values.size, TRANSFORM_DIM)] = values[:TRANSFORM_DIM]
        return result

    def _build_feature_vector(self, landmarks, *, aspect: float, face_blendshapes, matrices) -> np.ndarray:
        left_eye = (self._xy(landmarks, 33, aspect) + self._xy(landmarks, 133, aspect)) / 2.0
        right_eye = (self._xy(landmarks, 362, aspect) + self._xy(landmarks, 263, aspect)) / 2.0
        eye_center = (left_eye + right_eye) / 2.0
        left_mouth, right_mouth = self._xy(landmarks, 61, aspect), self._xy(landmarks, 291, aspect)
        mouth_center = (left_mouth + right_mouth) / 2.0
        nose = self._xy(landmarks, 1, aspect)
        forehead, chin = self._xy(landmarks, 10, aspect), self._xy(landmarks, 152, aspect)
        left_cheek, right_cheek = self._xy(landmarks, 234, aspect), self._xy(landmarks, 454, aspect)

        inter_eye = self._distance(left_eye, right_eye) + 1e-6
        face_width = self._distance(left_cheek, right_cheek) + 1e-6
        face_height = self._distance(forehead, chin) + 1e-6
        roll = math.atan2(float(right_eye[1] - left_eye[1]), float(right_eye[0] - left_eye[0]) + 1e-6)
        yaw = float((nose[0] - eye_center[0]) / inter_eye)
        pitch = float((nose[1] - mouth_center[1]) / face_height)

        selected_xyz = np.stack([self._xyz(landmarks, index, aspect) for index in DEPTH_ROBUST_LANDMARKS])
        nose_z = float(self._xyz(landmarks, 1, aspect)[2])
        raw_z_span = float(np.ptp(selected_xyz[:, 2]))
        normalized_z_span = raw_z_span / inter_eye
        left_iris = self._iris_diameter(landmarks, (469, 471, 470, 472), aspect)
        right_iris = self._iris_diameter(landmarks, (474, 476, 475, 477), aspect)
        iris_values = [value for value in (left_iris, right_iris) if value > 1e-6]
        mean_iris = float(np.mean(iris_values)) if iris_values else 0.0
        log_inverse_iris = -math.log(mean_iris + 1e-6) if mean_iris else 0.0

        scalar = np.asarray([
            self._eye_aspect_ratio(landmarks, LEFT_EYE_IDX, aspect),
            self._eye_aspect_ratio(landmarks, RIGHT_EYE_IDX, aspect),
            self._mouth_aspect_ratio(landmarks, aspect),
            pitch, yaw, roll, face_width, face_height, inter_eye, -math.log(inter_eye),
            math.sqrt(face_width * face_height), face_width / face_height, normalized_z_span,
            raw_z_span, left_iris, right_iris, mean_iris, log_inverse_iris,
            (nose[0] - left_eye[0]) / face_width, (nose[1] - left_eye[1]) / face_height,
            (nose[0] - right_eye[0]) / face_width, (nose[1] - right_eye[1]) / face_height,
            (mouth_center[0] - nose[0]) / face_width, (mouth_center[1] - nose[1]) / face_height,
            1.0,
        ], dtype=np.float32)
        if scalar.size != SCALAR_FEATURE_DIM:
            raise RuntimeError(f"Unexpected scalar feature dimension: {scalar.size}")

        cos_roll, sin_roll = math.cos(roll), math.sin(roll)
        rotation = np.asarray([[cos_roll, sin_roll], [-sin_roll, cos_roll]], dtype=np.float32)
        canonical: list[float] = []
        for point in selected_xyz:
            xy = rotation @ ((point[:2] - eye_center) / inter_eye)
            canonical.extend((float(xy[0]), float(xy[1]), (float(point[2]) - nose_z) / inter_eye))

        vector = np.concatenate((scalar, np.asarray(canonical, dtype=np.float32), self._blendshape_vector(face_blendshapes), self._transform_vector(matrices)))
        vector = np.nan_to_num(np.clip(vector, -FEATURE_CLIP, FEATURE_CLIP), nan=0.0, posinf=FEATURE_CLIP, neginf=-FEATURE_CLIP).astype(np.float32)
        if vector.shape != (self.expected_feature_dim,):
            raise ValueError(f"Expected feature shape {(self.expected_feature_dim,)}, got {vector.shape}")
        return vector

    def extract(self, frame_bgr: np.ndarray) -> DetectionResult:
        if self._face_landmarker is None:
            raise RuntimeError("FaceFeatureDetector has been closed.")
        if frame_bgr is None or frame_bgr.size == 0:
            raise ValueError("Input frame is empty.")
        rendered = frame_bgr.copy()
        height, width = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._face_landmarker.detect(image_lib.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not result.face_landmarks:
            return DetectionResult(rendered, np.zeros(self.expected_feature_dim, dtype=np.float32), False)

        landmarks = result.face_landmarks[0]
        if self.draw_landmarks:
            self._draw_landmarks(rendered, landmarks)
        feature = self._build_feature_vector(
            landmarks,
            aspect=width / max(1.0, float(height)),
            face_blendshapes=result.face_blendshapes,
            matrices=result.facial_transformation_matrixes,
        )
        return DetectionResult(rendered, feature, True)

    @staticmethod
    def _draw_landmarks(frame_bgr: np.ndarray, landmarks) -> None:
        height, width = frame_bgr.shape[:2]
        for index in DRAW_LANDMARKS:
            point = landmarks.landmark[index] if hasattr(landmarks, "landmark") else landmarks[index]
            cv2.circle(frame_bgr, (int(point.x * width), int(point.y * height)), 2, (0, 255, 0), -1)
