from __future__ import annotations

import math
import queue
import threading
import time

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from tracking.inference import ONNXEngagementInferencer
from ui.components.focus_chart import FocusTrendChart
from ui.components.timer import TimerChip


STATE_VI = {
    "ENGAGED": "Đang tập trung",
    "DISTRACTED": "Đang mất tập trung",
    "WARMING_UP": "Đang khởi động mô hình...",
    "NO_FACE": "Không thấy khuôn mặt",
}

DISPLAY_CONFIDENCE_FLOOR = 0.0
DISPLAY_CONFIDENCE_CEILING = 0.65


def _scale_display_confidence(raw_score: float) -> float:
    bounded = max(DISPLAY_CONFIDENCE_FLOOR, min(DISPLAY_CONFIDENCE_CEILING, float(raw_score)))
    if DISPLAY_CONFIDENCE_CEILING <= DISPLAY_CONFIDENCE_FLOOR:
        return 0.0
    return (bounded - DISPLAY_CONFIDENCE_FLOOR) / (DISPLAY_CONFIDENCE_CEILING - DISPLAY_CONFIDENCE_FLOOR)


class SessionScreen(ctk.CTkFrame):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent, fg_color="#0f1724")
        self.controller = controller

        self._frame_queue: queue.Queue[dict] = queue.Queue(maxsize=3)
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        self._duration_seconds = 25 * 60
        self._remaining_seconds = self._duration_seconds
        self._session_running = False
        self._session_paused = False
        self._session_start_monotonic = 0.0
        self._paused_duration = 0.0
        self._pause_started_monotonic: float | None = None

        self._focus_samples: list[tuple[float, float]] = []
        self._camera_image_ref: ImageTk.PhotoImage | None = None

        self._build_layout()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 10))
        top.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            top,
            text="Phiên tập trung",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#f3f7fd",
        ).grid(row=0, column=0, sticky="w", padx=(4, 14))

        self.timer_chip = TimerChip(top)
        self.timer_chip.grid(row=0, column=1, padx=8)

        self.state_label = ctk.CTkLabel(
            top,
            text="Sẵn sàng",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#b3c8e6",
        )
        self.state_label.grid(row=0, column=2, padx=14)

        self.score_label = ctk.CTkLabel(
            top,
            text="Focus: 0.0%",
            font=ctk.CTkFont(family="Segoe UI", size=16),
            text_color="#8eddbd",
        )
        self.score_label.grid(row=0, column=3, padx=12)

        self.score_bar = ctk.CTkProgressBar(top, width=220, progress_color="#2cb884")
        self.score_bar.grid(row=0, column=4, sticky="e", padx=(10, 4))
        self.score_bar.set(0.0)

        camera_card = ctk.CTkFrame(self, fg_color="#152238", corner_radius=16)
        camera_card.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=8)
        camera_card.grid_rowconfigure(1, weight=1)
        camera_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            camera_card,
            text="Camera + FaceMesh",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f3f7fd",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))

        self.camera_label = ctk.CTkLabel(
            camera_card,
            text="Nhấn Bắt đầu để mở camera",
            text_color="#93a9ca",
            corner_radius=10,
            fg_color="#0f1a2d",
        )
        self.camera_label.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        chart_card = ctk.CTkFrame(self, fg_color="#152238", corner_radius=16)
        chart_card.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=8)
        chart_card.grid_rowconfigure(1, weight=1)
        chart_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            chart_card,
            text="Biểu đồ tập trung theo thời gian",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f3f7fd",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))

        self.focus_chart = FocusTrendChart(chart_card)
        self.focus_chart.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=2, column=0, columnspan=2, pady=(8, 18))

        self.start_button = ctk.CTkButton(
            controls,
            text="Bắt đầu",
            width=140,
            fg_color="#2db07f",
            hover_color="#23996e",
            command=self.start_session,
        )
        self.start_button.pack(side="left", padx=8)

        self.pause_button = ctk.CTkButton(
            controls,
            text="Tạm dừng",
            width=140,
            fg_color="#355e9a",
            hover_color="#2a4b7a",
            command=self.toggle_pause,
            state="disabled",
        )
        self.pause_button.pack(side="left", padx=8)

        self.stop_button = ctk.CTkButton(
            controls,
            text="Kết thúc",
            width=140,
            fg_color="#9e3c4c",
            hover_color="#873445",
            command=lambda: self._finish_session(completed=False),
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=8)

        self.back_button = ctk.CTkButton(
            controls,
            text="Về Dashboard",
            width=160,
            fg_color="#2a3b5e",
            hover_color="#344a73",
            command=self.controller.show_dashboard,
        )
        self.back_button.pack(side="left", padx=8)

        self.timer_chip.set_seconds(self._duration_seconds)

    def prepare_session(self, minutes: int) -> None:
        self._duration_seconds = max(1, int(minutes)) * 60
        self._remaining_seconds = self._duration_seconds
        self._focus_samples.clear()
        self.focus_chart.clear()
        self.timer_chip.set_seconds(self._remaining_seconds)
        self.state_label.configure(text="Sẵn sàng")
        self.score_bar.set(0.0)
        self.score_label.configure(text="Focus: 0.0%")

    def start_session(self) -> None:
        if self._session_running:
            return

        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

        self._session_running = True
        self._session_paused = False
        self._session_start_monotonic = time.monotonic()
        self._paused_duration = 0.0
        self._pause_started_monotonic = None

        self.start_button.configure(state="disabled")
        self.pause_button.configure(state="normal", text="Tạm dừng")
        self.stop_button.configure(state="normal")

        self._start_worker_if_needed()
        self._tick_timer()
        self._process_queue()

    def toggle_pause(self) -> None:
        if not self._session_running:
            return

        if not self._session_paused:
            self._session_paused = True
            self._pause_started_monotonic = time.monotonic()
            self.pause_button.configure(text="Tiếp tục")
            self.state_label.configure(text="Đã tạm dừng")
            return

        self._session_paused = False
        if self._pause_started_monotonic is not None:
            self._paused_duration += max(0.0, time.monotonic() - self._pause_started_monotonic)
        self._pause_started_monotonic = None
        self.pause_button.configure(text="Tạm dừng")

    def _current_elapsed_seconds(self) -> float:
        if not self._session_running:
            return float(self._duration_seconds - self._remaining_seconds)

        now = time.monotonic()
        paused_live = 0.0
        if self._session_paused and self._pause_started_monotonic is not None:
            paused_live = max(0.0, now - self._pause_started_monotonic)

        elapsed = now - self._session_start_monotonic - self._paused_duration - paused_live
        return max(0.0, elapsed)

    def _tick_timer(self) -> None:
        if not self._session_running:
            return

        elapsed = self._current_elapsed_seconds()
        self._remaining_seconds = max(0, int(math.ceil(self._duration_seconds - elapsed)))
        self.timer_chip.set_seconds(self._remaining_seconds)

        if self._remaining_seconds <= 0:
            self._finish_session(completed=True)
            return

        self.after(1000, self._tick_timer)

    def _start_worker_if_needed(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._tracking_worker, daemon=True)
        self._worker_thread.start()

    def _tracking_worker(self) -> None:
        detector: FaceFeatureDetector | None = None
        capture: cv2.VideoCapture | None = None

        try:
            detector = FaceFeatureDetector(draw_landmarks=True)
            sequence_buffer = FeatureSequenceBuffer(sequence_length=60, frame_feature_dim=30)
            inferencer = ONNXEngagementInferencer(smoothing_window=5)

            capture = cv2.VideoCapture(0)
            if not capture.isOpened():
                self._safe_put({"error": "Không mở được camera"})
                return

            while not self._stop_event.is_set():
                success, frame = capture.read()
                if not success:
                    continue

                detection = detector.extract(frame)
                enriched = sequence_buffer.append(detection.feature)

                state = "NO_FACE" if not detection.face_found else "WARMING_UP"
                focus_score = 0.0

                if enriched is not None:
                    prediction = inferencer.predict(enriched)
                    state = str(prediction["state"])
                    focus_score = float(prediction["focus_score"])

                self._safe_put(
                    {
                        "frame": detection.frame,
                        "state": state,
                        "focus_score": focus_score,
                    }
                )

        except Exception as exc:  # pragma: no cover - runtime safety path
            self._safe_put({"error": str(exc)})
        finally:
            if capture is not None:
                capture.release()
            if detector is not None:
                detector.close()

    def _safe_put(self, payload: dict) -> None:
        if self._frame_queue.full():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self._frame_queue.put_nowait(payload)
        except queue.Full:
            pass

    def _process_queue(self) -> None:
        latest_payload: dict | None = None

        while True:
            try:
                latest_payload = self._frame_queue.get_nowait()
            except queue.Empty:
                break

        if latest_payload is not None:
            self._render_payload(latest_payload)

        still_alive = self._worker_thread is not None and self._worker_thread.is_alive()
        if self._session_running or still_alive:
            self.after(15, self._process_queue)

    def _render_payload(self, payload: dict) -> None:
        if "error" in payload:
            self.state_label.configure(text=f"Lỗi: {payload['error']}")
            self._stop_worker()
            self.start_button.configure(state="normal")
            self.pause_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self._session_running = False
            return

        frame = payload.get("frame")
        if frame is not None:
            self._update_camera_image(frame)

        state = str(payload.get("state", "WARMING_UP"))
        focus_score = float(payload.get("focus_score", 0.0))

        self.state_label.configure(text=STATE_VI.get(state, state))
        display_score = _scale_display_confidence(focus_score)
        self.score_bar.set(display_score)
        self.score_label.configure(text=f"Focus: {display_score * 100:.1f}%")
        # Color based on actual ENGAGED threshold (0.30)
        self.score_bar.configure(progress_color="#2cb884" if state == "ENGAGED" else "#4c6f9f")

        if self._session_running and not self._session_paused and state in {"ENGAGED", "DISTRACTED"}:
            elapsed = self._current_elapsed_seconds()
            self._focus_samples.append((elapsed, focus_score))
            self.focus_chart.add_score(focus_score)

    def _update_camera_image(self, frame_bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (720, 420))
        image = Image.fromarray(resized)
        photo = ImageTk.PhotoImage(image=image)
        self.camera_label.configure(image=photo, text="")
        self._camera_image_ref = photo

    def _compute_minute_averages(self, elapsed_seconds: int) -> list[float]:
        minute_count = max(1, int(math.ceil(max(1, elapsed_seconds) / 60)))
        buckets: list[list[float]] = [[] for _ in range(minute_count)]

        for elapsed, score in self._focus_samples:
            minute_index = min(minute_count - 1, int(elapsed // 60))
            buckets[minute_index].append(float(score))

        averages: list[float] = []
        carry = 0.0
        for bucket in buckets:
            if bucket:
                carry = float(np.mean(bucket))
            averages.append(carry)

        return averages

    def _finish_session(self, completed: bool) -> None:
        if not self._session_running:
            return

        elapsed_seconds = max(1, self._duration_seconds - self._remaining_seconds)

        self._session_running = False
        self._session_paused = False
        self.pause_button.configure(text="Tạm dừng")
        self._stop_worker()

        self.start_button.configure(state="normal")
        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")

        minute_scores = self._compute_minute_averages(elapsed_seconds=elapsed_seconds)
        average_score = float(np.mean(minute_scores)) if minute_scores else 0.0

        self.controller.on_session_finished(
            minute_scores=minute_scores,
            average_score=average_score,
            completed=completed,
        )

    def _stop_worker(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=0.8)
        self._worker_thread = None

    def reset_ui(self) -> None:
        self._stop_worker()
        self._session_running = False
        self._session_paused = False
        self._focus_samples.clear()
        self.focus_chart.clear()
        self.score_bar.set(0.0)
        self.score_label.configure(text="Focus: 0.0%")
        self.state_label.configure(text="Sẵn sàng")
        self.camera_label.configure(text="Nhấn Bắt đầu để mở camera", image=None)
        self._camera_image_ref = None
        self._remaining_seconds = self._duration_seconds
        self.timer_chip.set_seconds(self._remaining_seconds)

        self.start_button.configure(state="normal")
        self.pause_button.configure(state="disabled", text="Tạm dừng")
        self.stop_button.configure(state="disabled")

    def shutdown(self) -> None:
        self._stop_worker()
