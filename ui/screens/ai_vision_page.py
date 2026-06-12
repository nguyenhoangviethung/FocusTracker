from __future__ import annotations
import queue
import cv2
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QWidget, QPushButton
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap

from ui.screens.base import ThemedPage, Card
from ui.theme import ThemeManager, font
from tracking.tracker import FocusSessionTracker, TrackerConfig

class AIVisionPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        self._tracker = None
        self._tracker_queue = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)
        
        h_layout = QHBoxLayout()
        layout.addLayout(h_layout)
        
        self.camera_card = Card()
        h_layout.addWidget(self.camera_card)
        c_title = QLabel("CAMERA FEED")
        c_title.setFont(font(16, bold=True))
        self.camera_preview = QLabel("Camera Offline")
        self.camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview.setMinimumHeight(300)
        self.camera_preview.setStyleSheet("background-color: #222222; border-radius: 8px;")
        self.camera_card.layout.addWidget(c_title)
        self.camera_card.layout.addWidget(self.camera_preview)
        
        self.telemetry_card = Card()
        h_layout.addWidget(self.telemetry_card)
        t_title = QLabel("TELEMETRY")
        t_title.setFont(font(16, bold=True))
        self.telemetry_labels = {
            "fps": QLabel("FPS: 0.0"),
            "latency": QLabel("E2E Latency: 0 ms"),
            "ear": QLabel("EAR: 0.00"),
            "mar": QLabel("MAR: 0.00"),
            "pose": QLabel("Pitch: 0 | Yaw: 0"),
        }
        self.telemetry_card.layout.addWidget(t_title)
        for label in self.telemetry_labels.values():
            self.telemetry_card.layout.addWidget(label)
        self.telemetry_card.layout.addStretch()
        
        self.model_card = Card()
        layout.addWidget(self.model_card)
        m_title = QLabel("LATE-FUSION MODEL OUTPUT")
        m_title.setFont(font(16, bold=True))
        self.conf_label = QLabel("Confidence: 0%")
        self.vote_label = QLabel("VOTE: NONE")
        self.vote_label.setFont(font(16, bold=True))
        self.model_card.layout.addWidget(m_title)
        self.model_card.layout.addWidget(self.conf_label)
        self.model_card.layout.addWidget(self.vote_label)
        
        # Add Control Buttons
        ctrl_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Camera Demo")
        self.start_btn.setObjectName("accent_focus")
        self.start_btn.clicked.connect(self._start_demo)
        
        self.stop_btn = QPushButton("Stop Camera")
        self.stop_btn.clicked.connect(self.shutdown)
        
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.start_btn)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)
        
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self._poll_tracker_queue)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.shutdown()

    def shutdown(self) -> None:
        self.queue_timer.stop()
        if self._tracker:
            self._tracker.stop()
            self._tracker = None
        self.camera_preview.setText("Camera Offline")
        self.camera_preview.setPixmap(QPixmap())

    def _start_demo(self) -> None:
        if self._tracker: return
        self._tracker_queue = queue.Queue()
        app = self.property("app_reference")
        config_dict = app.settings if app else {}
        config = TrackerConfig.from_dict(config_dict)
        self._tracker = FocusSessionTracker(config, self._tracker_queue)
        self._tracker.start()
        self.queue_timer.start(33)

    def _poll_tracker_queue(self) -> None:
        if not self._tracker_queue: return
        while True:
            try:
                payload = self._tracker_queue.get_nowait()
                if str(payload.get("type")) == "telemetry":
                    self._render_telemetry(payload)
            except queue.Empty:
                break

    def _render_telemetry(self, payload: dict) -> None:
        if "frame" in payload:
            self._render_frame(payload["frame"])
            
        fps = payload.get("fps", 0.0)
        self.telemetry_labels["fps"].setText(f"Throughput : {fps:.1f} FPS")
        self.telemetry_labels["latency"].setText(f"E2E Latency: {int(1000/fps) if fps > 0 else 0} ms")
        
        features = payload.get("features", {})
        self.telemetry_labels["ear"].setText(f"EAR : {features.get('ear', 0.0):.2f}")
        self.telemetry_labels["mar"].setText(f"MAR : {features.get('mar', 0.0):.2f}")
        self.telemetry_labels["pose"].setText(f"Pitch: {features.get('pitch', 0.0):.1f}° | Yaw: {features.get('yaw', 0.0):.1f}°")
        
        score = payload.get("focus_score", 0.0)
        state = payload.get("state", "DISTRACTED")
        self.conf_label.setText(f"Confidence: {score*100:.1f}%")
        self.vote_label.setText(f"VOTE: {state}")
        self.vote_label.setStyleSheet(f"color: {self.theme.color('accent_focus') if state == 'FOCUSED' else self.theme.color('accent_warn')};")

    def _render_frame(self, frame_bgr) -> None:
        if frame_bgr is None or len(frame_bgr) == 0:
            return
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_data = rgb.tobytes()
            qimg = QImage(bytes_data, w, h, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimg).scaled(520, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.camera_preview.setPixmap(pixmap)
            self.camera_preview.setStyleSheet("")
        except Exception as e:
            pass
