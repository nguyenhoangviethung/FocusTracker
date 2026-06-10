from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path

import cv2
import numpy as np

# Reduce native shutdown instability on some Linux driver stacks.
os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")

import mediapipe as mp
from mediapipe.tasks.python.core import base_options as base_options_lib
from mediapipe.tasks.python.vision import face_landmarker as face_landmarker_lib
from mediapipe.tasks.python.vision.core import image as image_lib
from mediapipe.tasks.python.vision.core import vision_task_running_mode as running_mode_lib

from utils.paths import resource_base_dir
from utils.logger import get_logger


logger = get_logger("detector")


LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]
FLATTEN_LANDMARKS = [33, 133, 362, 263, 61, 291, 13, 14]
FRAME_FEATURE_DIM = 30


@dataclass
class DetectionResult:
    frame: np.ndarray
    feature: np.ndarray
    face_found: bool


class FaceFeatureDetector:
    """Extracts exactly 30 facial features from each frame using MediaPipe Face Landmarker."""

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        draw_landmarks: bool = True,
        expected_feature_dim: int = FRAME_FEATURE_DIM,
        camera_distance_scale: float = 0.085,
    ) -> None:
        logger.debug("Initializing FaceFeatureDetector (draw_landmarks=%s)", draw_landmarks)
        self.draw_landmarks = draw_landmarks
        self.expected_feature_dim = int(expected_feature_dim)
        self.camera_distance_scale = float(camera_distance_scale)
        self._closed = False
        self._model_path = self._resolve_model_path()
        logger.info("Loading FaceLandmarker model from: %s", self._model_path)

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
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._face_landmarker = face_landmarker_lib.FaceLandmarker.create_from_options(options)
        logger.info("FaceFeatureDetector initialized successfully")

    @staticmethod
    def _resolve_model_path() -> Path:
        candidate = resource_base_dir() / "models" / "face_landmarker.task"
        logger.debug("Resolving model path: %s", candidate)
        if not candidate.exists():
            logger.error("FaceLandmarker model not found at %s", candidate)
            raise FileNotFoundError(
                f"FaceLandmarker model not found at {candidate}. Download it before running the detector."
            )
        logger.info("Model found at: %s (size: %s bytes)", candidate, candidate.stat().st_size)
        return candidate

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        logger.info("Closing FaceFeatureDetector")
        try:
            if self._face_landmarker is not None:
                self._face_landmarker.close()
        except Exception:
            logger.warning("Detector close raised exception", exc_info=True)
        finally:
            self._face_landmarker = None

    @staticmethod
    def _landmark_at(landmarks, index: int):
        """Support both MediaPipe Solutions and Tasks landmark containers."""
        if hasattr(landmarks, "landmark"):
            return landmarks.landmark[index]
        return landmarks[index]

    def _lm_xy(self, landmarks, index: int) -> np.ndarray:
        point = self._landmark_at(landmarks, index)
        return np.array([point.x, point.y], dtype=np.float32)

    def _lm_xyz(self, landmarks, index: int) -> np.ndarray:
        point = self._landmark_at(landmarks, index)
        return np.array([point.x, point.y, point.z], dtype=np.float32)

    @staticmethod
    def _distance(point_a: np.ndarray, point_b: np.ndarray) -> float:
        return float(np.linalg.norm(point_a - point_b))

    def _eye_aspect_ratio(self, landmarks, eye_indices: list[int]) -> float:
        p1 = self._lm_xy(landmarks, eye_indices[0])
        p2 = self._lm_xy(landmarks, eye_indices[1])
        p3 = self._lm_xy(landmarks, eye_indices[2])
        p4 = self._lm_xy(landmarks, eye_indices[3])
        p5 = self._lm_xy(landmarks, eye_indices[4])
        p6 = self._lm_xy(landmarks, eye_indices[5])

        vertical = self._distance(p2, p6) + self._distance(p3, p5)
        horizontal = 2.0 * self._distance(p1, p4) + 1e-6
        return vertical / horizontal

    def _mouth_aspect_ratio(self, landmarks) -> float:
        top = self._lm_xy(landmarks, 13)
        bottom = self._lm_xy(landmarks, 14)
        left = self._lm_xy(landmarks, 61)
        right = self._lm_xy(landmarks, 291)

        vertical = self._distance(top, bottom)
        horizontal = self._distance(left, right) + 1e-6
        return vertical / horizontal

    def _head_pose_proxy(self, landmarks) -> np.ndarray:
        # Pitch, yaw, roll proxy using landmark set {1, 152, 33, 263, 61, 291}
        nose = self._lm_xy(landmarks, 1)
        chin = self._lm_xy(landmarks, 152)
        left_eye = self._lm_xy(landmarks, 33)
        right_eye = self._lm_xy(landmarks, 263)
        mouth_left = self._lm_xy(landmarks, 61)
        mouth_right = self._lm_xy(landmarks, 291)

        eye_center = (left_eye + right_eye) / 2.0
        mouth_center = (mouth_left + mouth_right) / 2.0
        face_width = self._distance(left_eye, right_eye) + 1e-6
        face_height = self._distance(eye_center, chin) + 1e-6

        yaw = (nose[0] - eye_center[0]) / face_width
        pitch = (nose[1] - mouth_center[1]) / face_height
        roll = math.atan2(float(right_eye[1] - left_eye[1]), float(right_eye[0] - left_eye[0]) + 1e-6)
        return np.array([pitch, yaw, roll], dtype=np.float32)

    def _build_feature_vector(self, landmarks) -> np.ndarray:
        # Exact order: EAR_L, EAR_R, MAR, [pitch,yaw,roll], 8 selected XYZ landmarks
        features = [
            self._eye_aspect_ratio(landmarks, LEFT_EYE_IDX),
            self._eye_aspect_ratio(landmarks, RIGHT_EYE_IDX),
            self._mouth_aspect_ratio(landmarks),
        ]
        features.extend(self._head_pose_proxy(landmarks).tolist())

        # Normalize 8 selected XYZ landmarks to simulate a fixed distance (scale factor)
        left_eye = self._lm_xy(landmarks, 33)
        right_eye = self._lm_xy(landmarks, 263)
        eye_center = (left_eye + right_eye) / 2.0
        face_width = self._distance(left_eye, right_eye) + 1e-6
        
        # Only shrink faces that are too close (face_width > camera_distance_scale).
        # Do not stretch faces that are far away (scale_factor <= 1.0).
        scale_factor = min(1.0, self.camera_distance_scale / face_width)

        for landmark_index in FLATTEN_LANDMARKS:
            p = self._lm_xyz(landmarks, landmark_index)
            # Scale X and Y around the eye center to stretch/shrink the face
            p[0] = eye_center[0] + (p[0] - eye_center[0]) * scale_factor
            p[1] = eye_center[1] + (p[1] - eye_center[1]) * scale_factor
            # Z is relative, so we just scale it directly
            p[2] = p[2] * scale_factor
            features.extend(p.tolist())

        vector = np.asarray(features, dtype=np.float32)
        if vector.shape != (self.expected_feature_dim,):
            raise ValueError(f"Expected feature shape {(self.expected_feature_dim,)}, got {vector.shape}")
        return vector

    def extract(self, frame_bgr: np.ndarray) -> DetectionResult:
        if self._face_landmarker is None:
            raise RuntimeError("FaceFeatureDetector has been closed.")
        if frame_bgr is None or frame_bgr.size == 0:
            logger.warning("Input frame is empty")
            raise ValueError("Input frame is empty.")

        rendered_frame = frame_bgr.copy()
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = image_lib.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        try:
            results = self._face_landmarker.detect(mp_image)
        except Exception as e:
            logger.error("Error during face detection: %s", e, exc_info=True)
            raise

        if not results.face_landmarks:
            logger.debug("No face detected in frame")
            return DetectionResult(
                frame=rendered_frame,
                feature=np.zeros((self.expected_feature_dim,), dtype=np.float32),
                face_found=False,
            )

        face_landmarks = results.face_landmarks[0]
        landmark_count = len(face_landmarks.landmark) if hasattr(face_landmarks, "landmark") else len(face_landmarks)
        logger.debug("Face detected with %s landmarks", landmark_count)

        if self.draw_landmarks:
            self._draw_landmarks(rendered_frame, face_landmarks)

        feature = self._build_feature_vector(face_landmarks)
        logger.debug(
            "Feature vector extracted: shape=%s, range=[%.3f, %.3f]",
            feature.shape,
            float(feature.min()),
            float(feature.max()),
        )

        return DetectionResult(
            frame=rendered_frame,
            feature=feature,
            face_found=True,
        )

    @staticmethod
    def _draw_landmarks(frame_bgr: np.ndarray, landmarks) -> None:
        height, width = frame_bgr.shape[:2]
        for index in FLATTEN_LANDMARKS:
            point = landmarks[index] if not hasattr(landmarks, "landmark") else landmarks.landmark[index]
            center = (int(point.x * width), int(point.y * height))
            cv2.circle(frame_bgr, center, 2, (0, 255, 0), -1)
