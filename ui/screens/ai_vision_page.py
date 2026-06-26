from __future__ import annotations
import queue
import cv2
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
    QPushButton,
    QProgressBar,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap

from ui.screens.base import ThemedPage, Card
from ui.theme import ThemeManager, font
from ui.component_metrics import component_text, normalize_components
from tracking.buffer import DEPTH_ROBUST_V2_FRAME_FEATURE_DIM, SEQUENCE_LENGTH
from tracking.tracker import FocusSessionTracker, TrackerConfig

class AIVisionPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        self._tracker = None
        self._tracker_queue = None
        self._latest_latencies: dict[str, float | None] = {
            "loop": None,
            "model": None,
            "roundtrip": None,
        }
        self._latest_components: dict[str, dict] = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)
        
        h_layout = QHBoxLayout()
        layout.addLayout(h_layout)
        
        self.camera_card = Card()
        self.camera_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        h_layout.addWidget(self.camera_card)
        c_title = QLabel("CAMERA FEED")
        c_title.setFont(font(16, bold=True))
        self.camera_preview = QLabel("Camera Offline")
        self.camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview.setMinimumHeight(300)
        self.camera_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.camera_preview.setStyleSheet("background-color: #222222; border-radius: 8px;")
        self.camera_card.layout.addWidget(c_title)
        self.camera_card.layout.addWidget(self.camera_preview)
        
        self.telemetry_card = Card()
        self.telemetry_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        h_layout.addWidget(self.telemetry_card)
        t_title = QLabel("TELEMETRY")
        t_title.setFont(font(16, bold=True))
        self.telemetry_labels = {
            "fps": QLabel("Throughput: 0.0 FPS"),
            "loop_latency": QLabel("Client Loop Latency: --"),
            "model_latency": QLabel("Model Inference Latency: --"),
            "roundtrip_latency": QLabel("Cloud Round-Trip Latency: --"),
            "schema": QLabel(
                f"Feature Schema: depth_robust_v2 ({DEPTH_ROBUST_V2_FRAME_FEATURE_DIM} values/frame)"
            ),
            "pose": QLabel("Pose: Pitch 0.00 | Yaw 0.00 | Roll 0.00"),
            "depth": QLabel("Depth Cues: inter-eye -- | normalized z-span --"),
        }
        self.focus_score_bar = QProgressBar()
        self.telemetry_card.layout.addWidget(t_title)
        for label in self.telemetry_labels.values():
            self.telemetry_card.layout.addWidget(label)
        self.telemetry_card.layout.addWidget(QLabel("Focus Telemetry"))
        self.telemetry_card.layout.addWidget(self.focus_score_bar)
        self.telemetry_card.layout.addStretch()
        
        self.model_card = Card()
        self.model_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.model_card)
        m_title = QLabel("DEEPFOREST 4-CLASS OUTPUT")
        m_title.setFont(font(16, bold=True))
        self.focus_score_label = QLabel("Focus Telemetry: --")
        self.extra_trees_label = QLabel("Layer 1 ExtraTrees : --")
        self.random_forest_label = QLabel("Layer 1 RandomForest : --")
        self.cascade_label = QLabel("Layer 2 Cascade : --")
        self.model_state_label = QLabel("STATE: WARMING_UP")
        self.model_state_label.setFont(font(16, bold=True))
        self.model_card.layout.addWidget(m_title)
        self.model_card.layout.addWidget(self.focus_score_label)
        self.model_card.layout.addWidget(self.extra_trees_label)
        self.model_card.layout.addWidget(self.random_forest_label)
        self.model_card.layout.addWidget(self.cascade_label)
        self.model_card.layout.addWidget(self.model_state_label)
        
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
        h_layout.setStretch(0, 1)
        h_layout.setStretch(1, 2)
        
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
        self._latest_latencies = {"loop": None, "model": None, "roundtrip": None}
        self._latest_components = {}
        self.camera_preview.setText("Camera Offline")
        self.camera_preview.setPixmap(QPixmap())

    def _start_demo(self) -> None:
        if self._tracker: return
        self._tracker_queue = queue.Queue()
        self._latest_latencies = {"loop": None, "model": None, "roundtrip": None}
        self._latest_components = {}
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
        self.telemetry_labels["fps"].setText(f"Throughput: {fps:.1f} FPS")
        loop_latency_ms = self._format_latency("loop", payload.get("client_loop_latency_ms", payload.get("latency_ms")))
        model_latency_ms = self._format_latency("model", payload.get("model_inference_latency_ms"))
        roundtrip_latency_ms = self._format_latency("roundtrip", payload.get("cloud_roundtrip_latency_ms"))
        self.telemetry_labels["loop_latency"].setText(f"Client Loop Latency: {loop_latency_ms}")
        self.telemetry_labels["model_latency"].setText(f"Model Inference Latency: {model_latency_ms}")
        self.telemetry_labels["roundtrip_latency"].setText(f"Cloud Round-Trip Latency: {roundtrip_latency_ms}")
        feature_values = payload.get("feature") or []
        if not isinstance(feature_values, (list, tuple)):
            feature_values = []
        pitch = float(feature_values[3]) if len(feature_values) > 3 else 0.0
        yaw = float(feature_values[4]) if len(feature_values) > 4 else 0.0
        roll = float(feature_values[5]) if len(feature_values) > 5 else 0.0
        inter_eye = float(feature_values[8]) if len(feature_values) > 8 else 0.0
        normalized_z_span = float(feature_values[12]) if len(feature_values) > 12 else 0.0
        self.telemetry_labels["pose"].setText(
            f"Pose: Pitch {pitch:.3f} | Yaw {yaw:.3f} | Roll {roll:.3f}"
        )
        self.telemetry_labels["depth"].setText(
            f"Depth Cues: inter-eye {inter_eye:.4f} | normalized z-span {normalized_z_span:.4f}"
        )

        score = self._clamp_score(payload.get("focus_score"))
        state = str(payload.get("state", "WARMING_UP")).upper()
        self._set_bar(self.focus_score_bar, score)
        self.focus_score_label.setText(f"Focus Telemetry: {score * 100:.1f}%")

        components = normalize_components(payload.get("components"))
        if components:
            self._latest_components = components
        self.extra_trees_label.setText(
            component_text("Layer 1 ExtraTrees", self._latest_components.get("layer1_extra_trees"))
        )
        self.random_forest_label.setText(
            component_text("Layer 1 RandomForest", self._latest_components.get("layer1_random_forest"))
        )
        self.cascade_label.setText(
            component_text("Layer 2 Cascade", self._latest_components.get("layer2_cascade"))
        )
        self.model_state_label.setText(f"STATE: {state}")
        if state == "FOCUSED":
            color = self.theme.color("accent_focus")
        elif state in {"WARMING_UP", "PAUSED"}:
            color = self.theme.color("text_secondary")
        else:
            color = self.theme.color("accent_warn")
        self.model_state_label.setStyleSheet(f"color: {color};")

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

    @staticmethod
    def _set_bar(bar: QProgressBar, value: float) -> None:
        bar.setRange(0, 1000)
        bar.setValue(max(0, min(1000, int(round(max(0.0, min(1.0, value)) * 1000)))))

    @staticmethod
    def _clamp_score(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def _format_latency(self, key: str, value) -> str:
        try:
            if value is not None:
                self._latest_latencies[key] = float(value)
        except (TypeError, ValueError):
            pass
        cached_value = self._latest_latencies.get(key)
        if cached_value is None:
            return "--"
        return f"{cached_value:.1f} ms"
