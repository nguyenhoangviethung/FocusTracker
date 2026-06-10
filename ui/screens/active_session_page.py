from __future__ import annotations
import queue
from typing import Any
import cv2
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap

from ui.screens.base import ThemedPage, Card
from ui.theme import ThemeManager, font
from ui.components.focus_chart import FocusTrendChart
from tracking.tracker import FocusSessionTracker, TrackerConfig

class ActiveSessionPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        self._remaining_seconds = 25 * 60
        self._duration_seconds = 25 * 60
        self._running = False
        self._paused = False
        self._tracker = None
        self._tracker_queue = None
        self._latest_focus_score = 0.0
        self._latest_state = "DISTRACTED"
        self._latest_sample_ready = False
        self._tracked_seconds = 0
        self._focused_seconds = 0
        self._distraction_count = 0
        self._current_focus_streak = 0
        self._best_focus_streak = 0
        self._last_second_state = None
        self._second_samples = []
        self._session_config = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self._poll_tracker_queue)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)
        
        self.timer_card = Card()
        layout.addWidget(self.timer_card)
        self.timer_label = QLabel("25:00")
        self.timer_label.setFont(font(62, bold=True))
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label = QLabel("STATUS: FOCUSED")
        self.status_label.setFont(font(16, bold=True))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_card.layout.addWidget(self.timer_label)
        self.timer_card.layout.addWidget(self.status_label)
        
        h_layout = QHBoxLayout()
        h_layout.setSpacing(18)
        layout.addLayout(h_layout)
        
        self.camera_card = Card()
        h_layout.addWidget(self.camera_card)
        c_title = QLabel("AI CAMERA")
        c_title.setFont(font(16, bold=True))
        self.camera_preview = QLabel("Camera will open when session starts")
        self.camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_preview.setMinimumHeight(240)
        self.camera_preview.setStyleSheet("background-color: #222222; border-radius: 8px;")
        self.camera_signal = QLabel("Signal: Waiting for Phase 2")
        self.camera_state = QLabel("State : FOCUSED")
        self.camera_card.layout.addWidget(c_title)
        self.camera_card.layout.addWidget(self.camera_preview)
        self.camera_card.layout.addWidget(self.camera_signal)
        self.camera_card.layout.addWidget(self.camera_state)
        
        self.os_card = Card()
        h_layout.addWidget(self.os_card)
        o_title = QLabel("OS TRACKER")
        o_title.setFont(font(16, bold=True))
        self.os_app = QLabel("Active App: Not activated")
        self.os_state = QLabel("State     : FOCUSED")
        self.hardcore_state = QLabel("Hardcore : OFF")
        self.trend_title = QLabel("FOCUS TREND")
        self.trend_title.setFont(font(16, bold=True))
        self.focus_chart = FocusTrendChart(max_points=300)
        self.os_card.layout.addWidget(o_title)
        self.os_card.layout.addWidget(self.os_app)
        self.os_card.layout.addWidget(self.os_state)
        self.os_card.layout.addWidget(self.hardcore_state)
        self.os_card.layout.addSpacing(16)
        self.os_card.layout.addWidget(self.trend_title)
        self.os_card.layout.addWidget(self.focus_chart)
        
        ctrl_layout = QHBoxLayout()
        self.pause_button = QPushButton("PAUSE")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setFixedSize(150, 42)
        
        self.end_button = QPushButton("END")
        self.end_button.setObjectName("accent_warn")
        self.end_button.clicked.connect(lambda: self.end_session())
        self.end_button.setFixedSize(150, 42)
        
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.pause_button)
        ctrl_layout.addWidget(self.end_button)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

    def begin(self, config: dict) -> None:
        self.stop_timer()
        self.stop_tracker()
        self._session_config = dict(config)
        minutes = int(config.get("pomodoro_minutes", 25) or 25)
        self._duration_seconds = max(1, minutes) * 60
        self._remaining_seconds = self._duration_seconds
        self._running = True
        self._paused = False
        self._reset_statistics()
        
        self.pause_button.setText("PAUSE")
        self.status_label.setText("STATUS: STARTING")
        self.camera_signal.setText("Signal: Starting camera/model")
        self.camera_state.setText("State : WARMING_UP")
        self.os_app.setText("Active App: Scanning")
        self.os_state.setText("State     : WARMING_UP")
        self.hardcore_state.setText("Hardcore : ON" if config.get("hardcore_enabled") else "Hardcore : OFF")
        
        self._start_tracker(config)
        self._render_timer()
        self.timer.start(1000)

    def toggle_pause(self) -> None:
        if not self._running: return
        self._paused = not self._paused
        self.pause_button.setText("RESUME" if self._paused else "PAUSE")
        self.status_label.setText("STATUS: PAUSED" if self._paused else "STATUS: FOCUSED")
        if self._tracker:
            if self._paused: self._tracker.pause()
            else: self._tracker.resume()

    def end_session(self, completed: bool = False) -> None:
        summary = self._build_session_summary(completed=completed)
        self.stop_timer()
        self.stop_tracker()
        app = self.property("app_reference")
        if app:
            app.finish_session(summary)

    def stop_timer(self) -> None:
        self.timer.stop()
        self._running = False
        self._paused = False

    def stop_tracker(self) -> None:
        self.queue_timer.stop()
        if self._tracker:
            self._tracker.stop()
            self._tracker = None

    def _tick(self) -> None:
        if not self._running: return
        if not self._paused:
            self._remaining_seconds = max(0, self._remaining_seconds - 1)
            self._record_second()
            self._render_timer()
        if self._remaining_seconds <= 0:
            self.end_session(completed=True)

    def _render_timer(self) -> None:
        m, s = divmod(self._remaining_seconds, 60)
        self.timer_label.setText(f"{m:02d}:{s:02d}")

    def _start_tracker(self, config: dict) -> None:
        self._tracker_queue = queue.Queue()
        tracker_config = TrackerConfig.from_dict(config)
        app = self.property("app_reference")
        self._tracker = FocusSessionTracker(
            tracker_config,
            self._tracker_queue,
            fusion_logic=app.fusion_logic if app else None,
        )
        self._tracker.start()
        self.queue_timer.start(33)

    def _poll_tracker_queue(self) -> None:
        if not self._tracker_queue: return
        while True:
            try:
                payload = self._tracker_queue.get_nowait()
                self._handle_tracker_payload(payload)
            except queue.Empty:
                break

    def _handle_tracker_payload(self, payload: dict) -> None:
        etype = str(payload.get("type", ""))
        if etype == "telemetry": self._render_telemetry(payload)
        elif etype == "os": self._render_os(payload.get("os"))
        elif etype == "error":
            src, msg = payload.get("source", "tracker"), payload.get("message", "Unknown error")
            target = self.camera_signal if src == "camera" else self.os_app
            target.setText(f"{src}: {msg}")
        elif etype == "status":
            self.camera_signal.setText(payload.get("message", "Tracking status changed"))
        elif etype == "hardcore":
            self._render_hardcore(payload)

    def _render_telemetry(self, payload: dict) -> None:
        if "frame" in payload: self._render_frame(payload["frame"])
        focus_score = float(payload.get("focus_score", 0.0))
        state = str(payload.get("state", "DISTRACTED"))
        ai_state = str(payload.get("ai_state", "WARMING_UP"))
        fps = float(payload.get("fps", 0.0))
        face_text = "face found" if payload.get("face_found") else "no face found"
        model_ready = bool(payload.get("model_ready", ai_state not in {"WARMING_UP", "STARTING"}))
        
        sig_text = f"Signal: {focus_score*100:.1f}% | {face_text} | {fps:.1f} FPS" if model_ready else f"Signal: gathering 30 frames | {face_text} | {fps:.1f} FPS"
        self.camera_signal.setText(sig_text)
        self.camera_state.setText(f"State : AI={ai_state}")
        self.status_label.setText(f"STATUS: {state}")
        
        self.status_label.setStyleSheet(f"color: {self.theme.color('accent_focus') if state == 'FOCUSED' else self.theme.color('accent_warn')};")
        
        self._latest_focus_score = focus_score
        self._latest_state = state
        self._latest_sample_ready = model_ready
        if "os" in payload: self._render_os(payload["os"])

    def _render_os(self, os_snapshot: dict | None) -> None:
        if not os_snapshot: return
        pname = os_snapshot.get("process_name", "unknown")
        wtitle = os_snapshot.get("window_title", pname)
        title = wtitle[:46] + "..." if len(wtitle) > 49 else wtitle
        self.os_app.setText(f"Active App: {pname} | {title}")
        self.os_state.setText(f"State     : {'PRODUCTIVE' if os_snapshot.get('is_productive_context') else 'NEUTRAL'}")

    def _render_hardcore(self, payload: dict) -> None:
        status, msg = payload.get("status", ""), payload.get("message", "")
        if status == "countdown":
            self.hardcore_state.setText(f"Hardcore : {int(payload.get('remaining_seconds', 0))}s before closing app")
            self.hardcore_state.setStyleSheet(f"color: {self.theme.color('accent_warn')};")
        elif status == "terminated":
            self.hardcore_state.setText(f"Hardcore : Closed app ({msg})")
            self.hardcore_state.setStyleSheet(f"color: {self.theme.color('accent_warn')};")
        elif status == "armed":
            self.hardcore_state.setText("Hardcore : ON - protecting session")
            self.hardcore_state.setStyleSheet(f"color: {self.theme.color('accent_focus')};")

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
            self.camera_preview.setStyleSheet("") # Remove border-radius on pixmap parent to render correctly
        except Exception as e:
            pass

    def _reset_statistics(self) -> None:
        self._latest_focus_score = 0.0
        self._latest_state = "DISTRACTED"
        self._latest_sample_ready = False
        self._tracked_seconds = 0
        self._focused_seconds = 0
        self._distraction_count = 0
        self._current_focus_streak = 0
        self._best_focus_streak = 0
        self._last_second_state = None
        self._second_samples.clear()
        self.focus_chart.clear()

    def _record_second(self) -> None:
        self._tracked_seconds += 1
        if not self._latest_sample_ready: return
        s, st = max(0.0, min(1.0, float(self._latest_focus_score))), self._latest_state
        self._second_samples.append((self._tracked_seconds, s))
        self.focus_chart.add_score(s)
        if st == "FOCUSED":
            self._focused_seconds += 1
            self._current_focus_streak += 1
            self._best_focus_streak = max(self._best_focus_streak, self._current_focus_streak)
        else:
            if self._last_second_state == "FOCUSED": self._distraction_count += 1
            self._current_focus_streak = 0
        self._last_second_state = st

    def _build_session_summary(self, completed: bool) -> dict:
        ms = [sum(scores)/len(scores) for k, scores in sorted({max(0, (sec-1)//60): [] for sec, _ in self._second_samples}.items()) if scores] # simplified
        avg = sum(s for _, s in self._second_samples)/len(self._second_samples) if self._second_samples else 0.0
        return {
            "minute_scores": ms, "average_score": avg, "completed": completed,
            "total_seconds": max(0, self._tracked_seconds), "focused_seconds": max(0, self._focused_seconds),
            "distraction_count": max(0, self._distraction_count), "focus_streak_seconds": float(self._best_focus_streak),
            "mentor_email": str(self._session_config.get("mentor_email", "")),
            "mentor_report_enabled": bool(self._session_config.get("mentor_report_enabled")),
            "hardcore_enabled": bool(self._session_config.get("hardcore_enabled")),
        }

    def apply_theme(self) -> None:
        super().apply_theme()
        p = self.theme.palette()
        self.focus_chart.apply_theme(p)
        for label in [self.camera_signal, self.camera_state, self.os_app, self.os_state, self.hardcore_state]:
            label.setStyleSheet(f"color: {p['text_secondary']};")
