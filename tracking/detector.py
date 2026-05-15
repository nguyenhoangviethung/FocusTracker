from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import mediapipe as mp
import numpy as np


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
    """Extracts exactly 30 facial features from each frame using MediaPipe FaceMesh."""

    def __init__(
        self,
        max_num_faces: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        draw_landmarks: bool = True,
    ) -> None:
        self.draw_landmarks = draw_landmarks
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=max_num_faces,
            refine_landmarks=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._drawer = mp.solutions.drawing_utils
        self._mesh_style = mp.solutions.drawing_styles.get_default_face_mesh_tesselation_style()

    def close(self) -> None:
        self._face_mesh.close()

    def _lm_xy(self, landmarks, index: int) -> np.ndarray:
        point = landmarks.landmark[index]
        return np.array([point.x, point.y], dtype=np.float32)

    def _lm_xyz(self, landmarks, index: int) -> np.ndarray:
        point = landmarks.landmark[index]
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

        for landmark_index in FLATTEN_LANDMARKS:
            features.extend(self._lm_xyz(landmarks, landmark_index).tolist())

        vector = np.asarray(features, dtype=np.float32)
        if vector.shape != (FRAME_FEATURE_DIM,):
            raise ValueError(f"Expected feature shape {(FRAME_FEATURE_DIM,)}, got {vector.shape}")
        return vector

    def extract(self, frame_bgr: np.ndarray) -> DetectionResult:
        if frame_bgr is None or frame_bgr.size == 0:
            raise ValueError("Input frame is empty.")

        rendered_frame = frame_bgr.copy()
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self._face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            return DetectionResult(
                frame=rendered_frame,
                feature=np.zeros((FRAME_FEATURE_DIM,), dtype=np.float32),
                face_found=False,
            )

        face_landmarks = results.multi_face_landmarks[0]
        if self.draw_landmarks:
            self._drawer.draw_landmarks(
                image=rendered_frame,
                landmark_list=face_landmarks,
                connections=mp.solutions.face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=self._mesh_style,
            )

        return DetectionResult(
            frame=rendered_frame,
            feature=self._build_feature_vector(face_landmarks),
            face_found=True,
        )
