from __future__ import annotations

from datetime import datetime, timedelta
import queue
import threading
import time

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

from os_tracker import ActiveWindowTracker
from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from tracking.inference import ONNXEngagementInferencer
from ui.components.timer import TimerChip, format_seconds
from utils.session_storage import save_session_statistics


STATE_LABELS = {
    "ENGAGED": "Đang tập trung",
    "DISTRACTED": "Đang phân tán",
    "WARMING_UP": "Đang khởi động mô hình",
    "NO_FACE": "Không thấy khuôn mặt",
}


def _format_clock(moment: datetime | None) -> str:
    if moment is None:
        return "--:--:--"
    return moment.strftime("%H:%M:%S")


class FocusGuardianScreen(ctk.CTkFrame):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent, fg_color="#08111d")
        self.controller = controller

        self._frame_queue: queue.Queue[dict[str, object]] = queue.Queue(maxsize=4)
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        self._duration_seconds = 25 * 60
        self._remaining_seconds = self._duration_seconds
        self._session_running = False
        self._session_paused = False
        self._session_start_monotonic = 0.0
        self._paused_duration = 0.0
        self._pause_started_monotonic: float | None = None
        self._session_started_at: datetime | None = None

        self._focus_samples: list[tuple[float, float]] = []
        self._camera_image_ref: ImageTk.PhotoImage | None = None
        self._last_payload_focused: bool | None = None
        self._last_payload_elapsed = 0.0
        self._focused_seconds_accumulated = 0.0
        self._current_focus_streak = 0.0
        self._distraction_count = 0
        self._last_distract_elapsed: float | None = None
        self._last_average_score = 0.0
        self._last_final_reason = "Chưa khởi động phiên"
        self._last_minute_scores: list[float] = []

        self._metric_labels: dict[str, ctk.CTkLabel] = {}

        self._build_layout()
        self.reset_ui()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)
        self.grid_rowconfigure(4, weight=0)

        banner = ctk.CTkFrame(self, corner_radius=26, fg_color="#0d1827")
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(18, 10))
        banner.grid_columnconfigure(0, weight=3)
        banner.grid_columnconfigure(1, weight=2)

        title_box = ctk.CTkFrame(banner, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w", padx=24, pady=18)

        ctk.CTkLabel(
            title_box,
            text="Focus Guardian",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="Bảng giám sát tập trung theo bố cục ASCII",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color="#9eb4d1",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.status_badge = ctk.CTkLabel(
            banner,
            text="  ĐANG GIÁM SÁT  ",
            corner_radius=12,
            fg_color="#213655",
            text_color="#dfe8f7",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.status_badge.grid(row=0, column=1, sticky="e", padx=24, pady=(20, 8))

        self.timer_chip = TimerChip(banner)
        self.timer_chip.grid(row=1, column=1, sticky="e", padx=24, pady=(0, 18))

        self.session_note = ctk.CTkLabel(
            banner,
            text="Phiên mới sẵn sàng",
            corner_radius=12,
            fg_color="#132133",
            text_color="#c9d6ea",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.session_note.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 18))

        ai_card = ctk.CTkFrame(self, corner_radius=24, fg_color="#111c2d")
        ai_card.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=8)
        ai_card.grid_columnconfigure(0, weight=1)
        ai_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            ai_card,
            text="AI VISION (GRU Model)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))

        preview_wrap = ctk.CTkFrame(ai_card, corner_radius=18, fg_color="#0b1422")
        preview_wrap.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        preview_wrap.grid_columnconfigure(0, weight=1)
        preview_wrap.grid_rowconfigure(0, weight=1)

        self.camera_label = ctk.CTkLabel(
            preview_wrap,
            text="Chờ camera khởi động...",
            text_color="#8ca0be",
            corner_radius=14,
            fg_color="#0b1422",
        )
        self.camera_label.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        ai_metrics = ctk.CTkFrame(ai_card, fg_color="transparent")
        ai_metrics.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        ai_metrics.grid_columnconfigure((0, 1), weight=1)

        self._add_metric(ai_metrics, 0, 0, "Camera", "camera", "Chưa mở")
        self._add_metric(ai_metrics, 0, 1, "FPS", "fps", "0.0")
        self._add_metric(ai_metrics, 1, 0, "Tư thế", "posture", "Đang chờ")
        self._add_metric(ai_metrics, 1, 1, "AI Vote", "ai_vote", "--")

        self.ai_progress = ctk.CTkProgressBar(ai_card, progress_color="#2cb884")
        self.ai_progress.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 16))
        self.ai_progress.set(0.0)

        os_card = ctk.CTkFrame(self, corner_radius=24, fg_color="#111c2d")
        os_card.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=8)
        os_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            os_card,
            text="OS TRACKER (Heuristic)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 8))

        os_metrics = ctk.CTkFrame(os_card, fg_color="transparent")
        os_metrics.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        os_metrics.grid_columnconfigure((0, 1), weight=1)

        self._add_metric(os_metrics, 0, 0, "Ứng dụng active", "active_app", "--")
        self._add_metric(os_metrics, 0, 1, "Tiêu đề cửa sổ", "window_title", "--")
        self._add_metric(os_metrics, 1, 0, "Tương tác", "interaction", "0.0")
        self._add_metric(os_metrics, 1, 1, "CPU / RAM", "resource", "--")

        self._add_full_metric(os_card, 2, "OS Vote", "os_vote", "--")

        fusion_card = ctk.CTkFrame(self, corner_radius=24, fg_color="#132133")
        fusion_card.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 8))
        fusion_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            fusion_card,
            text="FUSION ENGINE (Quyết định cuối)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 6))

        self.fusion_state_label = ctk.CTkLabel(
            fusion_card,
            text="ĐANG KHỞI ĐỘNG",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#eaf2ff",
        )
        self.fusion_state_label.grid(row=1, column=0, sticky="w", padx=18, pady=(2, 4))

        self.fusion_source_label = ctk.CTkLabel(
            fusion_card,
            text="Nguồn: --",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#96aac7",
        )
        self.fusion_source_label.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 4))

        self.fusion_reason_label = ctk.CTkLabel(
            fusion_card,
            text="Lý do: Chưa khởi động phiên.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#bfd0ea",
            wraplength=1160,
            justify="left",
        )
        self.fusion_reason_label.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 16))

        stats_card = ctk.CTkFrame(self, corner_radius=24, fg_color="#111c2d")
        stats_card.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(2, 8))
        stats_card.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        ctk.CTkLabel(
            stats_card,
            text="SESSION STATISTICS",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, columnspan=5, sticky="w", padx=18, pady=(16, 10))

        self._add_stat_tile(stats_card, 1, 0, "Tổng tập trung", "focused_total", "00:00:00")
        self._add_stat_tile(stats_card, 1, 1, "Focus streak", "focus_streak", "00:00:00")
        self._add_stat_tile(stats_card, 1, 2, "Số lần phân tán", "distractions", "0")
        self._add_stat_tile(stats_card, 1, 3, "Lần cuối phân tán", "last_distract", "--:--:--")
        self._add_stat_tile(stats_card, 1, 4, "Focus trung bình", "focus_average", "0.0%")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=4, column=0, columnspan=2, pady=(8, 18))

        self.pause_button = ctk.CTkButton(
            controls,
            text="Tạm dừng",
            width=150,
            fg_color="#355e9a",
            hover_color="#2a4b7a",
            command=self.toggle_pause,
            state="disabled",
        )
        self.pause_button.pack(side="left", padx=8)

        self.dashboard_button = ctk.CTkButton(
            controls,
            text="Về Dashboard",
            width=170,
            fg_color="#203451",
            hover_color="#2d4a73",
            command=self.controller.show_dashboard,
        )
        self.dashboard_button.pack(side="left", padx=8)

        self.stop_button = ctk.CTkButton(
            controls,
            text="Kết thúc phiên",
            width=150,
            fg_color="#9e3c4c",
            hover_color="#873445",
            command=lambda: self._finish_session(completed=False),
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=8)

    def _add_metric(self, parent, row: int, column: int, title: str, key: str, default: str) -> None:
        tile = ctk.CTkFrame(parent, corner_radius=16, fg_color="#0d1726")
        tile.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
        tile.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tile,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#93a7c3",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        value_label = ctk.CTkLabel(
            tile,
            text=default,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#f4f7fb",
            wraplength=210,
            justify="left",
        )
        value_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        self._metric_labels[key] = value_label

    def _add_full_metric(self, parent, row: int, title: str, key: str, default: str) -> None:
        tile = ctk.CTkFrame(parent, corner_radius=16, fg_color="#0d1726")
        tile.grid(row=row, column=0, sticky="ew", padx=16, pady=(2, 16))
        tile.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tile,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#93a7c3",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        value_label = ctk.CTkLabel(
            tile,
            text=default,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#f4f7fb",
            wraplength=460,
            justify="left",
        )
        value_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        self._metric_labels[key] = value_label

    def _add_stat_tile(self, parent, row: int, column: int, title: str, key: str, default: str) -> None:
        tile = ctk.CTkFrame(parent, corner_radius=16, fg_color="#0d1726")
        tile.grid(row=row, column=column, sticky="nsew", padx=8, pady=(0, 16))
        tile.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tile,
            text=title,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#93a7c3",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        value_label = ctk.CTkLabel(
            tile,
            text=default,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#f4f7fb",
        )
        value_label.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))
        self._metric_labels[key] = value_label

    def prepare_session(self, minutes: int) -> None:
        self._duration_seconds = max(1, int(minutes)) * 60
        self._remaining_seconds = self._duration_seconds
        self._focus_samples.clear()
        self._last_payload_focused = None
        self._last_payload_elapsed = 0.0
        self._focused_seconds_accumulated = 0.0
        self._current_focus_streak = 0.0
        self._distraction_count = 0
        self._last_distract_elapsed = None
        self._last_average_score = 0.0
        self._last_final_reason = "Phiên mới đã sẵn sàng."
        self._last_minute_scores = []
        self._session_started_at = None
        self.timer_chip.set_seconds(self._remaining_seconds)
        self._set_metric("camera", "Chưa mở")
        self._set_metric("fps", "0.0")
        self._set_metric("posture", "Đang chờ")
        self._set_metric("ai_vote", "--")
        self._set_metric("active_app", "--")
        self._set_metric("window_title", "--")
        self._set_metric("interaction", "0.0%")
        self._set_metric("resource", "--")
        self._set_metric("os_vote", "--")
        self._set_metric("focused_total", "00:00:00")
        self._set_metric("focus_streak", "00:00:00")
        self._set_metric("distractions", "0")
        self._set_metric("last_distract", "--:--:--")
        self._set_metric("focus_average", "0.0%")
        self.fusion_state_label.configure(text="ĐANG CHỜ PHIÊN")
        self.fusion_source_label.configure(text="Nguồn: --")
        self.fusion_reason_label.configure(text="Lý do: Phiên chưa bắt đầu.")
        self.session_note.configure(text=f"Phiên {int(minutes)} phút đã sẵn sàng")
        self.ai_progress.set(0.0)
        self.status_badge.configure(text="  SẴN SÀNG  ", fg_color="#213655")

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
        self._session_started_at = datetime.now()
        self._last_payload_focused = None
        self._last_payload_elapsed = 0.0
        self._focused_seconds_accumulated = 0.0
        self._current_focus_streak = 0.0
        self._distraction_count = 0
        self._last_distract_elapsed = None
        self._last_final_reason = "Đang khởi động camera và mô hình."
        self._last_minute_scores = []

        self.pause_button.configure(state="normal", text="Tạm dừng")
        self.stop_button.configure(state="normal")
        self.status_badge.configure(text="  ĐANG GIÁM SÁT  ", fg_color="#2d6b4f")
        self.session_note.configure(text="Camera, FaceMesh, ONNX và OS tracker đang chạy.")

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
            self.status_badge.configure(text="  ĐÃ TẠM DỪNG  ", fg_color="#6d5a2d")
            self.session_note.configure(text="Phiên đã tạm dừng. Camera vẫn sẵn sàng để tiếp tục.")
            return

        self._session_paused = False
        if self._pause_started_monotonic is not None:
            self._paused_duration += max(0.0, time.monotonic() - self._pause_started_monotonic)
        self._pause_started_monotonic = None
        self.pause_button.configure(text="Tạm dừng")
        self.status_badge.configure(text="  ĐANG GIÁM SÁT  ", fg_color="#2d6b4f")
        self.session_note.configure(text="Phiên đang chạy trở lại.")

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
        self._remaining_seconds = max(0, int(np.ceil(self._duration_seconds - elapsed)))
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
            window_tracker = ActiveWindowTracker()

            capture = cv2.VideoCapture(0)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            if not capture.isOpened():
                self._safe_put({"error": "Không mở được camera"})
                return

            fps_window_started = time.monotonic()
            frame_count = 0
            current_fps = 0.0
            cached_snapshot = None
            cached_snapshot_at = 0.0
            start_at = time.monotonic()

            while not self._stop_event.is_set():
                success, frame = capture.read()
                if not success:
                    continue

                frame_count += 1
                now = time.monotonic()
                elapsed_fps = now - fps_window_started
                if elapsed_fps >= 1.0:
                    current_fps = frame_count / max(elapsed_fps, 1e-6)
                    frame_count = 0
                    fps_window_started = now

                detection = detector.extract(frame)
                enriched = sequence_buffer.append(detection.feature)

                ai_probability = 0.0
                ai_state = "NO_FACE" if not detection.face_found else "WARMING_UP"
                if enriched is not None:
                    prediction = inferencer.predict(enriched)
                    ai_probability = float(prediction["focus_score"])
                    ai_state = str(prediction["state"])

                if cached_snapshot is None or (now - cached_snapshot_at) >= 0.65:
                    try:
                        cached_snapshot = window_tracker.snapshot()
                        cached_snapshot_at = now
                    except Exception:
                        cached_snapshot = None

                fusion = window_tracker.fuse_ai_and_os_signals(
                    ai_probability=ai_probability,
                    window_info=cached_snapshot,
                )

                snapshot = fusion.window_info
                if snapshot is None:
                    snapshot = window_tracker.snapshot()

                final_state = "TẬP TRUNG SÂU" if fusion.is_focused else "PHÂN TÁN"
                os_vote = "TẬP TRUNG" if window_tracker.should_override_to_focused(snapshot) else "CHƯA RÕ"

                # Scale AI probability to 0-0.65 range for display
                scaled_probability = ai_probability / 0.65
                scaled_percentage = scaled_probability * 100.0

                payload = {
                    "frame": detection.frame,
                    "camera_active": True,
                    "fps": current_fps,
                    "face_found": detection.face_found,
                    "posture": "Ổn định" if detection.face_found else "Không thấy mặt",
                    "ai_state": ai_state,
                    "ai_probability": ai_probability,
                    "ai_vote": f"{STATE_LABELS.get(ai_state, ai_state)} ({scaled_percentage:.1f}%)",
                    "window_info": snapshot.as_dict() if snapshot else None,
                    "os_vote": os_vote,
                    "final_state": final_state,
                    "final_focused": fusion.is_focused,
                    "final_source": fusion.source,
                    "final_reason": fusion.reason,
                    "elapsed_seconds": time.monotonic() - start_at,
                }
                self._safe_put(payload)

        except Exception as exc:  # pragma: no cover - runtime safety path
            self._safe_put({"error": str(exc)})
        finally:
            if capture is not None:
                capture.release()
            if detector is not None:
                detector.close()

    def _safe_put(self, payload: dict[str, object]) -> None:
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
        latest_payload: dict[str, object] | None = None

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

    def _render_payload(self, payload: dict[str, object]) -> None:
        if "error" in payload:
            self.status_badge.configure(text="  LỖI  ", fg_color="#8f3d4c")
            self.session_note.configure(text=f"Không thể chạy camera: {payload['error']}")
            self.fusion_state_label.configure(text="LỖI HỆ THỐNG")
            self.fusion_source_label.configure(text="Nguồn: worker")
            self.fusion_reason_label.configure(text=f"Lý do: {payload['error']}")
            self._stop_worker()
            self.pause_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self._session_running = False
            return

        frame = payload.get("frame")
        if isinstance(frame, np.ndarray):
            self._update_camera_image(frame)

        if self._session_running and not self._session_paused:
            self._advance_statistics(payload)

        camera_active = bool(payload.get("camera_active", False))
        fps = float(payload.get("fps", 0.0))
        posture = str(payload.get("posture", "Đang chờ"))
        ai_vote = str(payload.get("ai_vote", "--"))
        ai_probability = float(payload.get("ai_probability", 0.0))
        window_info = payload.get("window_info")
        os_vote = str(payload.get("os_vote", "--"))
        final_state = str(payload.get("final_state", "ĐANG KHỞI ĐỘNG"))
        final_focused = bool(payload.get("final_focused", False))
        final_source = str(payload.get("final_source", "--"))
        final_reason = str(payload.get("final_reason", ""))
        elapsed_seconds = float(payload.get("elapsed_seconds", 0.0))

        self._set_metric("camera", "Đang mở" if camera_active else "Chưa mở")
        self._set_metric("fps", f"{fps:.1f}")
        self._set_metric("posture", posture)
        self._set_metric("ai_vote", ai_vote)
        # Scale progress bar to 0-0.65 range (0.65 max → 1.0 fill)
        scaled_progress = max(0.0, min(1.0, ai_probability / 0.65))
        self.ai_progress.set(scaled_progress)

        if isinstance(window_info, dict):
            process_name = str(window_info.get("process_name", "unknown"))
            window_title = str(window_info.get("window_title", ""))
            interaction_score = float(window_info.get("interaction_score", 0.0))
            cpu_percent = window_info.get("cpu_percent")
            memory_percent = window_info.get("memory_percent")

            self._set_metric("active_app", process_name)
            self._set_metric("window_title", window_title or "--")
            self._set_metric("interaction", f"{interaction_score * 100:.1f}%")

            if cpu_percent is None and memory_percent is None:
                resource_text = "--"
            else:
                cpu_text = "--" if cpu_percent is None else f"{float(cpu_percent):.0f}%"
                mem_text = "--" if memory_percent is None else f"{float(memory_percent):.0f}%"
                resource_text = f"{cpu_text} / {mem_text}"
            self._set_metric("resource", resource_text)
        else:
            self._set_metric("active_app", "--")
            self._set_metric("window_title", "--")
            self._set_metric("interaction", "0.0%")
            self._set_metric("resource", "--")

        self._set_metric("os_vote", os_vote)

        self.fusion_state_label.configure(text=final_state)
        self.fusion_source_label.configure(text=f"Nguồn: {final_source}")
        self.fusion_reason_label.configure(text=f"Lý do: {final_reason}")

        self._refresh_statistics(elapsed_seconds)

        if final_focused:
            self.status_badge.configure(text="  TẬP TRUNG  ", fg_color="#2d6b4f")
        elif self._session_paused:
            self.status_badge.configure(text="  ĐÃ TẠM DỪNG  ", fg_color="#6d5a2d")
        else:
            self.status_badge.configure(text="  CẦN CHÚ Ý  ", fg_color="#8f3d4c")

        if self._session_running:
            self.session_note.configure(
                text=(
                    f"Đã ghi nhận {format_seconds(int(round(elapsed_seconds)))} | "
                    f"Tỷ lệ tập trung {self._current_focus_streak / max(elapsed_seconds, 1e-6) * 100:.1f}%"
                )
            )

        self._last_final_reason = final_reason

    def _advance_statistics(self, payload: dict[str, object]) -> None:
        elapsed = float(payload.get("elapsed_seconds", 0.0))
        focused = bool(payload.get("final_focused", False))

        if elapsed < self._last_payload_elapsed:
            self._last_payload_elapsed = elapsed
            self._last_payload_focused = focused
            return

        if self._last_payload_focused is not None:
            delta = max(0.0, elapsed - self._last_payload_elapsed)
            if self._last_payload_focused:
                self._focused_seconds_accumulated += delta
                self._current_focus_streak += delta
            else:
                self._current_focus_streak = 0.0

        if self._last_payload_focused is True and not focused:
            self._distraction_count += 1
            self._last_distract_elapsed = elapsed
            self._current_focus_streak = 0.0

        if focused and self._last_payload_focused is False:
            self._current_focus_streak = max(0.0, elapsed - self._last_payload_elapsed)

        self._focus_samples.append((elapsed, 1.0 if focused else 0.0))
        self._last_payload_elapsed = elapsed
        self._last_payload_focused = focused

    def _refresh_statistics(self, elapsed_seconds: float) -> None:
        total_elapsed = max(elapsed_seconds, self._last_payload_elapsed, 0.0)
        focused_total = self._focused_seconds_accumulated
        if self._last_payload_focused:
            focused_total += max(0.0, total_elapsed - self._last_payload_elapsed)

        focus_rate = focused_total / total_elapsed if total_elapsed > 0 else 0.0
        average_score = float(np.mean([score for _, score in self._focus_samples])) if self._focus_samples else 0.0
        self._last_average_score = average_score

        self._set_metric("focused_total", format_seconds(int(round(focused_total))))
        self._set_metric("focus_streak", format_seconds(int(round(self._current_focus_streak))))
        self._set_metric("distractions", str(self._distraction_count))
        self._set_metric(
            "last_distract",
            _format_clock(self._session_started_at + timedelta(seconds=self._last_distract_elapsed))
            if self._session_started_at is not None and self._last_distract_elapsed is not None
            else "--:--:--",
        )
        self._set_metric("focus_average", f"{average_score * 100:.1f}%")

        if self._session_running:
            self.timer_chip.set_seconds(self._remaining_seconds)
        self.session_note.configure(
            text=(
                f"Đã ghi nhận {format_seconds(int(round(total_elapsed)))} | "
                f"Tỷ lệ tập trung {focus_rate * 100:.1f}%"
            )
        )

    def _set_metric(self, key: str, value: str) -> None:
        label = self._metric_labels.get(key)
        if label is not None:
            label.configure(text=value)

    def _update_camera_image(self, frame_bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (720, 420))
        image = Image.fromarray(resized)
        photo = ImageTk.PhotoImage(image=image)
        self.camera_label.configure(image=photo, text="")
        self._camera_image_ref = photo

    def _compute_minute_averages(self, elapsed_seconds: int) -> list[float]:
        minute_count = max(1, int(np.ceil(max(1, elapsed_seconds) / 60)))
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

        self.pause_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.status_badge.configure(text="  ĐÃ KẾT THÚC  ", fg_color="#374860")

        minute_scores = self._compute_minute_averages(elapsed_seconds=elapsed_seconds)
        average_score = float(np.mean(minute_scores)) if minute_scores else 0.0
        self._last_minute_scores = minute_scores
        self._last_average_score = average_score

        self.controller.on_session_finished(
            minute_scores=minute_scores,
            average_score=average_score,
            completed=completed,
        )

    def finalize_session(self, minute_scores: list[float], average_score: float, completed: bool) -> None:
        self._last_minute_scores = minute_scores
        self._last_average_score = float(average_score)
        self._session_running = False
        self._session_paused = False
        self._stop_worker()

        self.pause_button.configure(state="disabled", text="Tạm dừng")
        self.stop_button.configure(state="disabled")
        self.status_badge.configure(text="  ĐÃ KẾT THÚC  ", fg_color="#374860")
        self.session_note.configure(
            text=(
                f"Phiên {'đã hoàn tất' if completed else 'đã dừng sớm'} | "
                f"Focus trung bình {average_score * 100:.1f}%"
            )
        )
        self._set_metric("focus_average", f"{average_score * 100:.1f}%")
        
        # Save session statistics to history.json
        try:
            total_seconds = max(1, self._duration_seconds - self._remaining_seconds)
            focused_seconds = max(0, int(round(self._focused_seconds_accumulated)))
            save_session_statistics(
                minute_scores=minute_scores,
                average_score=average_score,
                completed=completed,
                total_seconds=total_seconds,
                focused_seconds=focused_seconds,
                distraction_count=self._distraction_count,
                focus_streak_seconds=max(0.0, self._current_focus_streak),
            )
        except Exception as exc:
            print(f"Warning: Could not save session statistics: {exc}")

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
        self._last_minute_scores.clear()
        self._last_payload_focused = None
        self._last_payload_elapsed = 0.0
        self._focused_seconds_accumulated = 0.0
        self._current_focus_streak = 0.0
        self._distraction_count = 0
        self._last_distract_elapsed = None
        self._last_average_score = 0.0
        self._camera_image_ref = None
        self._remaining_seconds = self._duration_seconds
        self.timer_chip.set_seconds(self._remaining_seconds)

        self.status_badge.configure(text="  SẴN SÀNG  ", fg_color="#213655")
        self.session_note.configure(text="Chọn số phút và bắt đầu phiên mới.")
        self.camera_label.configure(text="Chờ camera khởi động...", image=None)
        self.fusion_state_label.configure(text="ĐANG CHỜ PHIÊN")
        self.fusion_source_label.configure(text="Nguồn: --")
        self.fusion_reason_label.configure(text="Lý do: Phiên chưa bắt đầu.")
        self.ai_progress.set(0.0)

        self._set_metric("camera", "Chưa mở")
        self._set_metric("fps", "0.0")
        self._set_metric("posture", "Đang chờ")
        self._set_metric("ai_vote", "--")
        self._set_metric("active_app", "--")
        self._set_metric("window_title", "--")
        self._set_metric("interaction", "0.0%")
        self._set_metric("resource", "--")
        self._set_metric("os_vote", "--")
        self._set_metric("focused_total", "00:00:00")
        self._set_metric("focus_streak", "00:00:00")
        self._set_metric("distractions", "0")
        self._set_metric("last_distract", "--:--:--")
        self._set_metric("focus_average", "0.0%")

        self.pause_button.configure(state="disabled", text="Tạm dừng")
        self.stop_button.configure(state="disabled")

    def shutdown(self) -> None:
        self._stop_worker()
