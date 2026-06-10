from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ui.components.file_picker import open_video_file_picker
from ui.screens.base import Card, PageTitle, ThemedPage
from ui.theme import ThemeManager, font


class HomePage(ThemedPage):
    def __init__(self, parent, controller, theme: ThemeManager) -> None:
        super().__init__(parent, controller, theme)
        self.duration_minutes = ctk.IntVar(value=25)
        self.hardcore_enabled = ctk.BooleanVar(value=False)
        self.mentor_report_enabled = ctk.BooleanVar(value=False)
        self.demo_video_path = ctk.StringVar(value="")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = PageTitle(
            self,
            theme,
            "Xin chào! Sẵn sàng vào phiên tập trung?",
            "Thiết lập Pomodoro, demo video và các tuỳ chọn kỷ luật trước khi bắt đầu.",
        )
        self.header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 18))

        self.card = Card(self, theme)
        self.card.grid(row=1, column=0, sticky="n", padx=32, pady=(0, 32), ipadx=6, ipady=6)
        self.card.grid_columnconfigure(1, weight=1)

        self.card_title = ctk.CTkLabel(self.card, text="POMODORO SETUP", font=font(16, "bold"), anchor="w")
        self.card_title.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=(22, 18))

        self.duration_label = ctk.CTkLabel(self.card, text="Thời lượng", font=font(14), anchor="w")
        self.duration_label.grid(row=1, column=0, sticky="w", padx=24, pady=12)

        self.minus_button = ctk.CTkButton(
            self.card,
            text="<",
            width=44,
            height=36,
            corner_radius=8,
            border_width=0,
            font=font(14, "bold"),
            command=lambda: self._change_duration(-5),
        )
        self.minus_button.grid(row=1, column=1, sticky="e", padx=(0, 10), pady=12)

        self.duration_value = ctk.CTkLabel(self.card, width=110, text="", font=font(16, "bold"))
        self.duration_value.grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=12)

        self.plus_button = ctk.CTkButton(
            self.card,
            text=">",
            width=44,
            height=36,
            corner_radius=8,
            border_width=0,
            font=font(14, "bold"),
            command=lambda: self._change_duration(5),
        )
        self.plus_button.grid(row=1, column=3, sticky="e", padx=(0, 24), pady=12)

        self.hardcore_switch = ctk.CTkSwitch(
            self.card,
            text="Hardcore Mode",
            variable=self.hardcore_enabled,
            font=font(14),
            border_width=0,
        )
        self.hardcore_switch.grid(row=2, column=0, columnspan=4, sticky="w", padx=24, pady=10)

        self.mentor_switch = ctk.CTkSwitch(
            self.card,
            text="Gửi báo cáo mentor",
            variable=self.mentor_report_enabled,
            font=font(14),
            border_width=0,
        )
        self.mentor_switch.grid(row=3, column=0, columnspan=4, sticky="w", padx=24, pady=10)

        self.demo_label = ctk.CTkLabel(self.card, text="Demo video", font=font(14), anchor="w")
        self.demo_label.grid(row=4, column=0, sticky="w", padx=24, pady=12)

        self.demo_path_label = ctk.CTkLabel(self.card, text="Chưa chọn file .mp4", font=font(13), anchor="w")
        self.demo_path_label.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=12)

        self.demo_button = ctk.CTkButton(
            self.card,
            text="Chọn .mp4",
            height=36,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self._select_demo_video,
        )
        self.demo_button.grid(row=4, column=3, sticky="e", padx=(0, 24), pady=12)

        self.start_button = ctk.CTkButton(
            self.card,
            text="BẮT ĐẦU PHIÊN",
            height=46,
            corner_radius=8,
            border_width=0,
            font=font(15, "bold"),
            command=self._start_session,
        )
        self.start_button.grid(row=5, column=0, columnspan=4, sticky="ew", padx=24, pady=(20, 24))

        self._refresh_duration()
        self.apply_theme()

    def session_config(self) -> dict[str, object]:
        return {
            "duration_minutes": int(self.duration_minutes.get()),
            "session_minutes": int(self.duration_minutes.get()),
            "hardcore_enabled": bool(self.hardcore_enabled.get()),
            "mentor_report_enabled": bool(self.mentor_report_enabled.get()),
            "demo_video_path": self.demo_video_path.get(),
        }

    def apply_settings(self, settings: dict[str, object]) -> None:
        try:
            self.duration_minutes.set(int(float(settings.get("session_minutes", 25))))
        except (TypeError, ValueError):
            self.duration_minutes.set(25)
        self.hardcore_enabled.set(bool(settings.get("hardcore_enabled", False)))
        self.mentor_report_enabled.set(bool(settings.get("mentor_report_enabled", False)))
        self.demo_video_path.set(str(settings.get("demo_video_path") or ""))
        path = self.demo_video_path.get().strip()
        self.demo_path_label.configure(text=Path(path).name if path else "Chưa chọn file .mp4")
        self._refresh_duration()

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme()
        self.card.apply_theme()
        palette = self.theme.palette()
        labels = [
            self.card_title,
            self.duration_label,
            self.duration_value,
            self.hardcore_switch,
            self.mentor_switch,
            self.demo_label,
        ]
        for label in labels:
            label.configure(text_color=palette["text_primary"])
        self.demo_path_label.configure(text_color=palette["text_secondary"])
        for button in [self.minus_button, self.plus_button, self.demo_button]:
            button.configure(
                fg_color=palette["btn_neutral"],
                hover_color=palette["btn_neutral_hover"],
                text_color=palette["text_primary"],
            )
        self.start_button.configure(
            fg_color=palette["accent_focus"],
            hover_color=palette["accent_focus"],
            text_color="#FFFFFF",
        )

    def _change_duration(self, delta: int) -> None:
        value = max(5, min(180, int(self.duration_minutes.get()) + delta))
        self.duration_minutes.set(value)
        self._refresh_duration()

    def _refresh_duration(self) -> None:
        self.duration_value.configure(text=f"{int(self.duration_minutes.get())} phút")

    def _select_demo_video(self) -> None:
        open_video_file_picker(self, self.theme, self.demo_video_path.get(), self._set_demo_video)

    def _set_demo_video(self, selected: str) -> None:
        self.demo_video_path.set(selected)
        self.demo_path_label.configure(text=Path(selected).name)

    def _start_session(self) -> None:
        self.controller.start_session(self.session_config())
