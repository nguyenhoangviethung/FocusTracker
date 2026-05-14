import cv2
import mediapipe as mp
import numpy as np
import onnxruntime as ort
from collections import deque
import time
import math

# --- CẤU HÌNH TỪ AGENTS.MD ---
MODEL_PATH = "models/engagement_gru.onnx"
WINDOW_SIZE = 60
FEATURE_DIM = 90
THRESHOLD =0.45

# Các chỉ số landmark từ extract_features.py
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
FLATTEN_LANDMARKS = [33, 133, 362, 263, 61, 291, 13, 14]

class FocusTrackerTester:
    def __init__(self):
        # 1. Khởi tạo ONNX Runtime
        self.ort_session = ort.InferenceSession(MODEL_PATH)
        self.input_name = self.ort_session.get_inputs()[0].name
        
        # 2. Khởi tạo MediaPipe
        self.mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
            refine_landmarks=True, max_num_faces=1, min_detection_confidence=0.5
        )
        
        # 3. Buffer lưu trữ 60 frames (30 đặc trưng gốc)
        self.frame_buffer = deque(maxlen=WINDOW_SIZE)
        self.prob = 0.5
        self.status = "INITIALIZING..."

    def _get_lm_xyz(self, landmarks, idx):
        pt = landmarks.landmark[idx]
        return np.array([pt.x, pt.y, pt.z], dtype=np.float32)

    def _eye_aspect_ratio(self, landmarks, eye_indices):
        pts = [self._get_lm_xyz(landmarks, i)[:2] for i in eye_indices] # Dùng x, y
        def dist(p1, p2): return np.linalg.norm(p1 - p2)
        vertical = dist(pts[1], pts[5]) + dist(pts[2], pts[4])
        horizontal = 2.0 * dist(pts[0], pts[3]) + 1e-6
        return vertical / horizontal

    def _extract_30_features(self, landmarks):
        # Replicate logic from extract_features.py
        ear_l = self._eye_aspect_ratio(landmarks, LEFT_EYE)
        ear_r = self._eye_aspect_ratio(landmarks, RIGHT_EYE)
        
        # Mouth Ratio
        top, bottom = self._get_lm_xyz(landmarks, 13)[:2], self._get_lm_xyz(landmarks, 14)[:2]
        l_m, r_m = self._get_lm_xyz(landmarks, 61)[:2], self._get_lm_xyz(landmarks, 291)[:2]
        mar = np.linalg.norm(top-bottom) / (np.linalg.norm(l_m-r_m) + 1e-6)

        # Head Pose Proxy (Simplified Pitch, Yaw, Roll)
        nose = self._get_lm_xyz(landmarks, 1)[:2]
        chin = self._get_lm_xyz(landmarks, 152)[:2]
        l_e, r_e = self._get_lm_xyz(landmarks, 33)[:2], self._get_lm_xyz(landmarks, 263)[:2]
        eye_center = (l_e + r_e) / 2.0
        yaw = (nose[0] - eye_center[0]) / (np.linalg.norm(l_e - r_e) + 1e-6)
        pitch = (nose[1] - (l_m[1]+r_m[1])/2.0) / (np.linalg.norm(eye_center - chin) + 1e-6)
        roll = math.atan2(r_e[1] - l_e[1], r_e[0] - l_e[0])

        features = [ear_l, ear_r, mar, pitch, yaw, roll]
        for idx in FLATTEN_LANDMARKS:
            features.extend(self._get_lm_xyz(landmarks, idx).tolist())
        return np.array(features, dtype=np.float32)

    def _enrich_features(self):
        # Biến deque thành numpy array (60, 30)
        raw_window = np.array(list(self.frame_buffer), dtype=np.float32)
        
        # 1. Velocity (60, 30)
        velocity = np.zeros_like(raw_window)
        velocity[1:] = raw_window[1:] - raw_window[:-1]
        
        # 2. Std Matrix (60, 30)
        std_val = np.std(raw_window, axis=0)
        std_matrix = np.tile(std_val, (WINDOW_SIZE, 1))
        
        # Concatenate -> (60, 90)
        enriched = np.concatenate([raw_window, velocity, std_matrix], axis=-1)
        return enriched.reshape(1, WINDOW_SIZE, FEATURE_DIM).astype(np.float32)

    def run(self):
        cap = cv2.VideoCapture(0)
        print("--- Đang khởi động Camera và GRU Model ---")
        
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.mp_face_mesh.process(frame_rgb)

            if results.multi_face_landmarks:
                # Trích xuất 30 đặc trưng và đưa vào buffer
                feat_30 = self._extract_30_features(results.multi_face_landmarks[0])
                self.frame_buffer.append(feat_30)

                # Khi đủ 60 frames thì bắt đầu dự đoán
                if len(self.frame_buffer) == WINDOW_SIZE:
                    input_data = self._enrich_features()
                    logits = self.ort_session.run(None, {self.input_name: input_data})[0]
                    
                    # Apply Sigmoid
                    self.prob = 1 / (1 + np.exp(-logits[0]))
                    self.status = "ENGAGED" if self.prob >= THRESHOLD else "DISTRACTED"

            # Hiển thị kết quả lên màn hình
            color = (0, 255, 0) if self.status == "ENGAGED" else (0, 0, 255)
            cv2.putText(frame, f"Focus Score: {self.prob:.2f}", (30, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            cv2.putText(frame, f"Status: {self.status}", (30, 100), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
            cv2.imshow("FocusFlow AI - GRU Test", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'): break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    tester = FocusTrackerTester()
    tester.run()