from __future__ import annotations

import queue
from typing import Any

import cv2
import customtkinter as ctk
from PIL import Image

from ui.components.focus_chart import FocusTrendChart
from ui.screens.base import Card, ThemedPage
from ui.theme import ThemeManager, font
from tracking.tracker import FocusSessionTracker, TrackerConfig


class ActiveSessionPage(ThemedPage):
    def __init__(self, parent, controller, theme: ThemeManager) -> None:
        super().__init__(parent, controller, theme)
        self._remaining_seconds = 25 * 60
        self._duration_seconds = 25 * 60
        self._running = False
        self._paused = False
        self._after_id: str | None = None
        self._queue_after_id: str | None = None
        self._tracker_queue: queue.Queue[dict[str, Any]] | None = None
        self._tracker: FocusSessionTracker | None = None
        self._camera_image: ctk.CTkImage | None = None
        self._latest_focus_score = 0.0
        self._latest_state = "DISTRACTED"
        self._latest_sample_ready = False
        self._tracked_seconds = 0
        self._focused_seconds = 0
        self._distraction_count = 0
        self._current_focus_streak = 0
        self._best_focus_streak = 0
        self._last_second_state: str | None = None
        self._second_samples: list[tuple[int, float]] = []
        self._session_config: dict[str, object] = {}

        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.timer_card = Card(self, theme)
        self.timer_card.grid(row=0, column=0, columnspan=2, sticky="ew", padx=32, pady=(30, 18))
        self.timer_card.grid_columnconfigure(0, weight=1)

        self.timer_label = ctk.CTkLabel(self.timer_card, text="25:00", font=font(62, "bold"))
        self.timer_label.grid(row=0, column=0, pady=(28, 4))

        self.status_label = ctk.CTkLabel(self.timer_card, text="STATUS: FOCUSED", font=font(16, "bold"))
        self.status_label.grid(row=1, column=0, pady=(0, 28))

        self.camera_card = Card(self, theme)
        self.camera_card.grid(row=1, column=0, sticky="nsew", padx=(32, 10), pady=(0, 18))
        self.camera_card.grid_columnconfigure(0, weight=1)
        self.camera_card.grid_rowconfigure(1, weight=1)

        self.camera_title = ctk.CTkLabel(self.camera_card, text="AI CAMERA", font=font(16, "bold"), anchor="w")
        self.camera_title.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        self.camera_preview = ctk.CTkLabel(
            self.camera_card,
            text="Camera sẽ mở khi phiên bắt đầu",
            font=font(14),
            corner_radius=8,
            height=240,
        )
        self.camera_preview.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        self.camera_signal = ctk.CTkLabel(self.camera_card, text="Signal: Đang chờ Phase 2", font=font(14), anchor="w")
        self.camera_signal.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        self.camera_state = ctk.CTkLabel(self.camera_card, text="State : FOCUSED", font=font(14), anchor="w")
        self.camera_state.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 18))

        self.os_card = Card(self, theme)
        self.os_card.grid(row=1, column=1, sticky="nsew", padx=(10, 32), pady=(0, 18))
        self.os_card.grid_columnconfigure(0, weight=1)
        self.os_card.grid_rowconfigure(5, weight=1)

        self.os_title = ctk.CTkLabel(self.os_card, text="OS TRACKER", font=font(16, "bold"), anchor="w")
        self.os_title.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        self.os_app = ctk.CTkLabel(self.os_card, text="Active App: Chưa kích hoạt", font=font(14), anchor="w")
        self.os_app.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        self.os_state = ctk.CTkLabel(self.os_card, text="State     : FOCUSED", font=font(14), anchor="w")
        self.os_state.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        self.hardcore_state = ctk.CTkLabel(self.os_card, text="Hardcore : OFF", font=font(14), anchor="w")
        self.hardcore_state.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 18))

        self.trend_title = ctk.CTkLabel(self.os_card, text="FOCUS TREND", font=font(16, "bold"), anchor="w")
        self.trend_title.grid(row=4, column=0, sticky="ew", padx=20, pady=(8, 10))
        self.focus_chart = FocusTrendChart(self.os_card, max_points=300, palette=self.theme.palette())
        self.focus_chart.grid(row=5, column=0, sticky="nsew", padx=20, pady=(0, 20))

        self.controls = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        self.controls.grid(row=2, column=0, columnspan=2, pady=(0, 28))

        self.pause_button = ctk.CTkButton(
            self.controls,
            text="TẠM DỪNG",
            width=150,
            height=42,
            corner_radius=8,
            border_width=0,
            font=font(14, "bold"),
            command=self.toggle_pause,
        )
        self.pause_button.pack(side="left", padx=8)

        self.end_button = ctk.CTkButton(
            self.controls,
            text="KẾT THÚC",
            width=150,
            height=42,
            corner_radius=8,
            border_width=0,
            font=font(14, "bold"),
            command=self.end_session,
        )
        self.end_button.pack(side="left", padx=8)
        self.apply_theme()

    def begin(self, config: dict[str, object]) -> None:
        self.stop_timer()
        self.stop_tracker()
        self._session_config = dict(config)
        minutes = int(config.get("duration_minutes", 25) or 25)
        self._duration_seconds = max(1, minutes) * 60
        self._remaining_seconds = self._duration_seconds
        self._running = True
        self._paused = False
        self._reset_statistics()
        self.pause_button.configure(text="TẠM DỪNG")
        self.status_label.configure(text="STATUS: STARTING")
        self.camera_signal.configure(text="Signal: Đang khởi động camera/model")
        self.camera_state.configure(text="State : WARMING_UP")
        self.os_app.configure(text="Active App: Đang quét")
        self.os_state.configure(text="State     : WARMING_UP")
        hardcore_text = "Hardcore : ON" if bool(config.get("hardcore_enabled")) else "Hardcore : OFF"
        self.hardcore_state.configure(text=hardcore_text)
        self._start_tracker(config)
        self._render_timer()
        self._tick()

    def toggle_pause(self) -> None:
        if not self._running:
            return
        self._paused = not self._paused
        self.pause_button.configure(text="TIẾP TỤC" if self._paused else "TẠM DỪNG")
        self.status_label.configure(text="STATUS: PAUSED" if self._paused else "STATUS: FOCUSED")
        if self._tracker:
            if self._paused:
                self._tracker.pause()
            else:
                self._tracker.resume()

    def end_session(self, completed: bool = False) -> None:
        summary = self._build_session_summary(completed=completed)
        self.stop_timer()
        self.stop_tracker()
        on_finished = getattr(self.controller, "finish_session", None)
        if callable(on_finished):
            on_finished(summary)
        else:
            self.controller.navigate("report")

    def stop_timer(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        self._running = False
        self._paused = False

    def stop_tracker(self) -> None:
        if self._queue_after_id:
            self.after_cancel(self._queue_after_id)
            self._queue_after_id = None
        if self._tracker:
            self._tracker.stop()
            self._tracker = None
        self._tracker_queue = None

    def apply_theme(self) -> None:
        super().apply_theme()
        palette = self.theme.palette()
        for card in [self.timer_card, self.camera_card, self.os_card]:
            card.apply_theme()
        primary_labels = [self.timer_label, self.camera_title, self.os_title, self.trend_title]
        secondary_labels = [self.camera_signal, self.camera_state, self.os_app, self.os_state, self.hardcore_state]
        for label in primary_labels:
            label.configure(text_color=palette["text_primary"])
        for label in secondary_labels:
            label.configure(text_color=palette["text_secondary"])
        self.camera_preview.configure(fg_color=palette["input"], text_color=palette["text_secondary"])
        self.focus_chart.apply_theme(palette)
        self.status_label.configure(text_color=palette["accent_focus"])
        self.pause_button.configure(
            fg_color=palette["btn_neutral"],
            hover_color=palette["btn_neutral_hover"],
            text_color=palette["text_primary"],
        )
        self.end_button.configure(
            fg_color=palette["accent_warn"],
            hover_color=palette["accent_warn"],
            text_color="#FFFFFF",
        )

    def _tick(self) -> None:
        if not self._running:
            return
        if not self._paused:
            self._remaining_seconds = max(0, self._remaining_seconds - 1)
            self._record_second()
            self._render_timer()
        if self._remaining_seconds <= 0:
            self.end_session(completed=True)
            return
        self._after_id = self.after(1000, self._tick)

    def _render_timer(self) -> None:
        minutes, seconds = divmod(self._remaining_seconds, 60)
        self.timer_label.configure(text=f"{minutes:02d}:{seconds:02d}")

    def _start_tracker(self, config: dict[str, object]) -> None:
        self._tracker_queue = queue.Queue(maxsize=8)
        tracker_config = TrackerConfig.from_dict(config)
        self._tracker = FocusSessionTracker(
            tracker_config,
            self._tracker_queue,
            fusion_logic=getattr(self.controller, "fusion_logic", None),
        )
        self._tracker.start()
        self._poll_tracker_queue()

    def _poll_tracker_queue(self) -> None:
        if not self._tracker_queue:
            return
        while True:
            try:
                payload = self._tracker_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_tracker_payload(payload)
        if self._tracker:
            self._queue_after_id = self.after(33, self._poll_tracker_queue)

    def _handle_tracker_payload(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("type") or "")
        if event_type == "telemetry":
            self._render_telemetry(payload)
            return
        if event_type == "os":
            self._render_os(payload.get("os") if isinstance(payload.get("os"), dict) else None)
            return
        if event_type == "error":
            source = str(payload.get("source") or "tracker")
            message = str(payload.get("message") or "Lỗi không xác định")
            target = self.camera_signal if source == "camera" else self.os_app
            target.configure(text=f"{source}: {message}")
            return
        if event_type == "status":
            self.camera_signal.configure(text=str(payload.get("message") or "Tracking status changed"))
            return
        if event_type == "hardcore":
            self._render_hardcore(payload)

    def _render_telemetry(self, payload: dict[str, Any]) -> None:
        frame = payload.get("frame")
        if frame is not None:
            self._render_frame(frame)

        focus_score = float(payload.get("focus_score") or 0.0)
        state = str(payload.get("state") or "DISTRACTED")
        ai_state = str(payload.get("ai_state") or "WARMING_UP")
        fusion_strategy = str(payload.get("fusion_strategy") or "").strip()
        fps = float(payload.get("fps") or 0.0)
        face_text = "có khuôn mặt" if bool(payload.get("face_found")) else "chưa thấy khuôn mặt"

        model_ready = bool(payload.get("model_ready", ai_state not in {"WARMING_UP", "STARTING"}))
        component_text = self._format_component_scores(payload.get("components"))
        if model_ready:
            signal_text = f"Signal: {focus_score * 100:.1f}%{component_text} | {face_text} | {fps:.1f} FPS"
        else:
            signal_text = f"Signal: đang gom 30 frame | {face_text} | {fps:.1f} FPS"

        self.camera_signal.configure(text=signal_text)
        strategy_text = f" | {fusion_strategy}" if fusion_strategy else ""
        self.camera_state.configure(text=f"State : AI={ai_state}{strategy_text}")
        self.status_label.configure(text=f"STATUS: {state}")
        self.status_label.configure(
            text_color=self.theme.color("accent_focus") if state == "FOCUSED" else self.theme.color("accent_warn")
        )
        self._latest_focus_score = focus_score
        self._latest_state = "FOCUSED" if state == "FOCUSED" else "DISTRACTED"
        self._latest_sample_ready = model_ready
        self._render_os(payload.get("os") if isinstance(payload.get("os"), dict) else None)

    def _render_os(self, os_snapshot: dict[str, Any] | None) -> None:
        if not os_snapshot:
            return
        process_name = str(os_snapshot.get("process_name") or "unknown")
        window_title = str(os_snapshot.get("window_title") or process_name)
        interaction = float(os_snapshot.get("interaction_score") or 0.0)
        productive = bool(os_snapshot.get("is_productive_context"))
        title = window_title[:46] + "..." if len(window_title) > 49 else window_title
        self.os_app.configure(text=f"Active App: {process_name} | {title}")
        self.os_state.configure(
            text=f"State     : {'PRODUCTIVE' if productive else 'NEUTRAL'} ({interaction * 100:.0f}%)"
        )

    def _render_hardcore(self, payload: dict[str, Any]) -> None:
        status = str(payload.get("status") or "")
        message = str(payload.get("message") or "")
        remaining = int(float(payload.get("remaining_seconds") or 0))
        if status == "countdown":
            self.hardcore_state.configure(text=f"Hardcore : {remaining}s trước khi đóng app")
            self.hardcore_state.configure(text_color=self.theme.color("accent_warn"))
            return
        if status == "terminated":
            self.hardcore_state.configure(text=f"Hardcore : Đã đóng app ({message})")
            self.hardcore_state.configure(text_color=self.theme.color("accent_warn"))
            return
        if status == "armed":
            self.hardcore_state.configure(text="Hardcore : ON - đang bảo vệ phiên")
            self.hardcore_state.configure(text_color=self.theme.color("accent_focus"))
            return
        if status == "cleared":
            self.hardcore_state.configure(text=f"Hardcore : {message}")
            self.hardcore_state.configure(text_color=self.theme.color("accent_focus"))
            return
        if status == "blocked":
            self.hardcore_state.configure(text=f"Hardcore : {message}")
            self.hardcore_state.configure(text_color=self.theme.color("accent_warn"))

    def _render_frame(self, frame_bgr: Any) -> None:
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            image.thumbnail((520, 300))
            self._camera_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            self.camera_preview.configure(image=self._camera_image, text="")
        except Exception:
            self.camera_preview.configure(text="Không render được frame camera")

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
        if not self._latest_sample_ready:
            return

        score = max(0.0, min(1.0, float(self._latest_focus_score)))
        state = self._latest_state
        self._second_samples.append((self._tracked_seconds, score))
        self.focus_chart.add_score(score)

        if state == "FOCUSED":
            self._focused_seconds += 1
            self._current_focus_streak += 1
            self._best_focus_streak = max(self._best_focus_streak, self._current_focus_streak)
        else:
            if self._last_second_state == "FOCUSED":
                self._distraction_count += 1
            self._current_focus_streak = 0
        self._last_second_state = state

    def _build_session_summary(self, completed: bool) -> dict[str, object]:
        minute_scores = self._minute_focus_scores()
        if self._second_samples:
            average_score = sum(score for _, score in self._second_samples) / len(self._second_samples)
        else:
            average_score = 0.0

        return {
            "minute_scores": minute_scores,
            "average_score": average_score,
            "completed": bool(completed),
            "total_seconds": max(0, self._tracked_seconds),
            "focused_seconds": max(0, self._focused_seconds),
            "distraction_count": max(0, self._distraction_count),
            "focus_streak_seconds": float(self._best_focus_streak),
            "mentor_email": str(self._session_config.get("mentor_email") or ""),
            "mentor_report_enabled": bool(self._session_config.get("mentor_report_enabled")),
            "hardcore_enabled": bool(self._session_config.get("hardcore_enabled")),
        }

    def _minute_focus_scores(self) -> list[float]:
        buckets: dict[int, list[float]] = {}
        for second, score in self._second_samples:
            minute_index = max(0, (second - 1) // 60)
            buckets.setdefault(minute_index, []).append(score)
        return [
            sum(scores) / len(scores)
            for _, scores in sorted(buckets.items())
            if scores
        ]

    @staticmethod
    def _format_component_scores(components: Any) -> str:
        if not isinstance(components, dict):
            return ""
        labels = []
        for key, label in (("gru", "GRU"), ("tcn", "TCN"), ("xgboost", "XGB")):
            item = components.get(key)
            if not isinstance(item, dict):
                continue
            try:
                probability = float(item.get("probability"))
            except (TypeError, ValueError):
                continue
            labels.append(f"{label} {probability * 100:.0f}")
        if not labels:
            return ""
        return " | " + " ".join(labels)
