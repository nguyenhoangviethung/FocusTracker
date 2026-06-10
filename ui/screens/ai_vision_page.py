from __future__ import annotations

from pathlib import Path
import queue
from typing import Any

import cv2
import customtkinter as ctk
from PIL import Image

from tracking.tracker import FocusSessionTracker, TrackerConfig
from ui.components.file_picker import open_video_file_picker
from ui.screens.base import Card, PageTitle, ThemedPage
from ui.theme import ThemeManager, font


class AIVisionPage(ThemedPage):
    def __init__(self, parent, controller, theme: ThemeManager) -> None:
        super().__init__(parent, controller, theme)
        self._tracker_queue: queue.Queue[dict[str, Any]] | None = None
        self._tracker: FocusSessionTracker | None = None
        self._queue_after_id: str | None = None
        self._camera_image: ctk.CTkImage | None = None
        self._demo_video_path = ""

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        self.header = PageTitle(
            self,
            theme,
            "AI Vision",
            "Developer showcase cho camera, MediaPipe telemetry và late-fusion output.",
        )
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=32, pady=(28, 18))

        self.camera_card = Card(self, theme)
        self.camera_card.grid(row=1, column=0, sticky="nsew", padx=(32, 10), pady=(0, 18))
        self.camera_card.grid_columnconfigure(0, weight=1)
        self.camera_card.grid_rowconfigure(1, weight=1)

        self.camera_title = ctk.CTkLabel(self.camera_card, text="CAMERA FEED", font=font(16, "bold"), anchor="w")
        self.camera_title.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
        self.camera_frame = ctk.CTkLabel(
            self.camera_card,
            text="Bấm Start để mở webcam hoặc chạy video demo",
            font=font(15),
            corner_radius=8,
            height=320,
        )
        self.camera_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))

        controls = ctk.CTkFrame(self.camera_card, fg_color="transparent", border_width=0)
        controls.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        controls.grid_columnconfigure((0, 1, 2), weight=1)
        self.webcam_button = ctk.CTkButton(
            controls,
            text="Start Webcam",
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self.start_webcam,
        )
        self.webcam_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.demo_button = ctk.CTkButton(
            controls,
            text="Select Demo",
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self.select_and_start_demo,
        )
        self.demo_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.stop_button = ctk.CTkButton(
            controls,
            text="Stop",
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self.shutdown,
        )
        self.stop_button.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.telemetry_card = Card(self, theme)
        self.telemetry_card.grid(row=1, column=1, sticky="nsew", padx=(10, 32), pady=(0, 18))
        self.telemetry_card.grid_columnconfigure(0, weight=1)

        self.telemetry_title = ctk.CTkLabel(self.telemetry_card, text="TELEMETRY", font=font(16, "bold"), anchor="w")
        self.telemetry_title.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))

        self.latency_label = self._telemetry_line("E2E Latency: -- ms", 1)
        self.fps_label = self._telemetry_line("Throughput : -- FPS", 2)
        self.pose_label = self._telemetry_line("Pitch: --   Yaw: --   Roll: --", 3)
        self.face_label = self._telemetry_line("Face: --", 4)

        self.ear_label = ctk.CTkLabel(self.telemetry_card, text="EAR", font=font(13), anchor="w")
        self.ear_label.grid(row=5, column=0, sticky="ew", padx=20, pady=(18, 4))
        self.ear_progress = ctk.CTkProgressBar(self.telemetry_card)
        self.ear_progress.grid(row=6, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.ear_progress.set(0.0)

        self.mar_label = ctk.CTkLabel(self.telemetry_card, text="MAR", font=font(13), anchor="w")
        self.mar_label.grid(row=7, column=0, sticky="ew", padx=20, pady=(8, 4))
        self.mar_progress = ctk.CTkProgressBar(self.telemetry_card)
        self.mar_progress.grid(row=8, column=0, sticky="ew", padx=20, pady=(0, 20))
        self.mar_progress.set(0.0)

        self.output_card = Card(self, theme)
        self.output_card.grid(row=2, column=0, columnspan=2, sticky="ew", padx=32, pady=(0, 32))
        self.output_card.grid_columnconfigure(1, weight=1)

        self.output_title = ctk.CTkLabel(
            self.output_card,
            text="LATE-FUSION MODEL OUTPUT",
            font=font(16, "bold"),
            anchor="w",
        )
        self.output_title.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(18, 12))

        self.confidence_label = ctk.CTkLabel(self.output_card, text="Confidence", font=font(14), anchor="w")
        self.confidence_label.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))
        self.confidence_progress = ctk.CTkProgressBar(self.output_card)
        self.confidence_progress.grid(row=1, column=1, sticky="ew", padx=(0, 20), pady=(0, 18))
        self.confidence_progress.set(0.0)

        self.vote_label = ctk.CTkLabel(self.output_card, text="VOTE: WARMING_UP", font=font(15, "bold"), anchor="w")
        self.vote_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 20))
        self.apply_theme()

    def apply_settings(self, settings: dict[str, object]) -> None:
        self._demo_video_path = str(settings.get("demo_video_path") or "").strip()

    def start_webcam(self) -> None:
        config = self._base_tracker_config()
        config["demo_video_path"] = ""
        self._start_tracker(config)

    def select_and_start_demo(self) -> None:
        open_video_file_picker(self, self.theme, self._demo_video_path, self._start_selected_demo)

    def _start_selected_demo(self, selected: str) -> None:
        self._demo_video_path = selected
        if not self._demo_video_path:
            self.camera_frame.configure(text="Chưa chọn video demo")
            return
        config = self._base_tracker_config()
        config["demo_video_path"] = self._demo_video_path
        self._start_tracker(config)

    def shutdown(self) -> None:
        if self._queue_after_id:
            self.after_cancel(self._queue_after_id)
            self._queue_after_id = None
        if self._tracker:
            self._tracker.stop()
            self._tracker = None
        self._tracker_queue = None
        self.webcam_button.configure(state="normal")
        self.demo_button.configure(state="normal")
        self.vote_label.configure(text="VOTE: STOPPED")

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme()
        palette = self.theme.palette()
        for card in [self.camera_card, self.telemetry_card, self.output_card]:
            card.apply_theme()
        primary = [
            self.camera_title,
            self.telemetry_title,
            self.output_title,
            self.confidence_label,
            self.ear_label,
            self.mar_label,
        ]
        for label in primary:
            label.configure(text_color=palette["text_primary"])
        for label in [self.latency_label, self.fps_label, self.pose_label, self.face_label]:
            label.configure(text_color=palette["text_secondary"])
        self.camera_frame.configure(fg_color=palette["input"], text_color=palette["text_secondary"])
        self.vote_label.configure(text_color=palette["accent_focus"])
        for progress in [self.ear_progress, self.mar_progress, self.confidence_progress]:
            progress.configure(progress_color=palette["accent_focus"])
        for button in [self.webcam_button, self.demo_button]:
            button.configure(
                fg_color=palette["btn_neutral"],
                hover_color=palette["btn_neutral_hover"],
                text_color=palette["text_primary"],
            )
        self.stop_button.configure(
            fg_color=palette["accent_warn"],
            hover_color=palette["accent_warn"],
            text_color="#FFFFFF",
        )

    def _telemetry_line(self, text: str, row: int) -> ctk.CTkLabel:
        label = ctk.CTkLabel(self.telemetry_card, text=text, font=font(14), anchor="w")
        label.grid(row=row, column=0, sticky="ew", padx=20, pady=6)
        return label

    def _base_tracker_config(self) -> dict[str, object]:
        settings_page = getattr(self.controller, "pages", {}).get("settings")
        tracker_config = getattr(settings_page, "tracker_config", None)
        config = tracker_config() if callable(tracker_config) else {}
        config["hardcore_enabled"] = False
        config["show_landmarks"] = True
        return config

    def _start_tracker(self, config: dict[str, object]) -> None:
        self.shutdown()
        self._tracker_queue = queue.Queue(maxsize=8)
        tracker_config = TrackerConfig.from_dict(config)
        self._tracker = FocusSessionTracker(
            tracker_config,
            self._tracker_queue,
            fusion_logic=getattr(self.controller, "fusion_logic", None),
        )
        self._tracker.start()
        self.webcam_button.configure(state="disabled")
        self.demo_button.configure(state="disabled")
        source = Path(str(config.get("demo_video_path") or "")).name if config.get("demo_video_path") else "webcam"
        self.camera_frame.configure(text=f"Đang mở {source}...")
        self.vote_label.configure(text="VOTE: WARMING_UP")
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
        if event_type == "error":
            self.camera_frame.configure(text=str(payload.get("message") or "Lỗi tracker"))

    def _render_telemetry(self, payload: dict[str, Any]) -> None:
        frame = payload.get("frame")
        if frame is not None:
            self._render_frame(frame)

        feature = payload.get("feature") if isinstance(payload.get("feature"), list) else []
        ear_left = _feature_at(feature, 0)
        ear_right = _feature_at(feature, 1)
        mar = _feature_at(feature, 2)
        pitch = _feature_at(feature, 3)
        yaw = _feature_at(feature, 4)
        roll = _feature_at(feature, 5)
        ear = (ear_left + ear_right) / 2.0

        latency = float(payload.get("latency_ms") or 0.0)
        fps = float(payload.get("fps") or 0.0)
        focus_score = max(0.0, min(1.0, float(payload.get("focus_score") or 0.0)))
        state = str(payload.get("state") or "WARMING_UP")

        self.latency_label.configure(text=f"E2E Latency: {latency:.0f} ms")
        self.fps_label.configure(text=f"Throughput : {fps:.1f} FPS")
        self.pose_label.configure(text=f"Pitch: {pitch:+.2f}   Yaw: {yaw:+.2f}   Roll: {roll:+.2f}")
        self.face_label.configure(text=f"Face: {'detected' if payload.get('face_found') else 'not found'}")
        self.ear_progress.set(max(0.0, min(1.0, ear / 0.45)))
        self.mar_progress.set(max(0.0, min(1.0, mar / 0.8)))
        self.confidence_progress.set(focus_score)
        self.vote_label.configure(text=f"VOTE: {state} ({focus_score * 100:.1f}%)")
        self.vote_label.configure(
            text_color=self.theme.color("accent_focus") if state == "FOCUSED" else self.theme.color("accent_warn")
        )

    def _render_frame(self, frame_bgr: Any) -> None:
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            image.thumbnail((720, 420))
            self._camera_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            self.camera_frame.configure(image=self._camera_image, text="")
        except Exception:
            self.camera_frame.configure(text="Không render được frame")


def _feature_at(feature: list[Any], index: int) -> float:
    try:
        return float(feature[index])
    except (IndexError, TypeError, ValueError):
        return 0.0
