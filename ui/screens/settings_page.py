from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ui.components.file_picker import open_video_file_picker
from ui.screens.base import Card, PageTitle, ThemedPage
from ui.theme import ThemeManager, font


class SettingsPage(ThemedPage):
    def __init__(self, parent, controller, theme: ThemeManager) -> None:
        super().__init__(parent, controller, theme)
        self.theme_var = ctk.StringVar(value=theme.mode)
        self.mentor_email = ctk.StringVar(value="")
        self.camera_index = ctk.StringVar(value="0")
        self.demo_video_path = ctk.StringVar(value="")
        self.engagement_threshold = ctk.StringVar(value="0.54")
        self.smoothing_window = ctk.StringVar(value="5")
        self.os_ai_threshold = ctk.StringVar(value="0.45")
        self.os_override_threshold = ctk.StringVar(value="0.60")
        self.hardcore_countdown_seconds = ctk.StringVar(value="30")
        self.productive_keywords = ctk.StringVar(value="vscode, github, pdf, docx, figma")
        self.distracting_keywords = ctk.StringVar(value="facebook, netflix, lol, tiktok")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header = PageTitle(
            self,
            theme,
            "Cài đặt",
            "Tùy chỉnh giao diện, mentor email và keyword cho OS Tracker.",
        )
        self.header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 18))

        self.account_card = Card(self, theme)
        self.account_card.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 18))
        self.account_card.grid_columnconfigure(1, weight=1)

        self.account_title = ctk.CTkLabel(
            self.account_card,
            text="APPEARANCE & ACCOUNT",
            font=font(16, "bold"),
            anchor="w",
        )
        self.account_title.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=(22, 14))

        self.theme_label = ctk.CTkLabel(self.account_card, text="Theme", font=font(14), anchor="w")
        self.theme_label.grid(row=1, column=0, sticky="w", padx=24, pady=12)
        self.light_radio = ctk.CTkRadioButton(
            self.account_card,
            text="Light",
            value="Light",
            variable=self.theme_var,
            font=font(14),
            border_width_checked=5,
            border_width_unchecked=2,
            command=self._theme_changed,
        )
        self.light_radio.grid(row=1, column=1, sticky="w", padx=(0, 18), pady=12)
        self.dark_radio = ctk.CTkRadioButton(
            self.account_card,
            text="Dark",
            value="Dark",
            variable=self.theme_var,
            font=font(14),
            border_width_checked=5,
            border_width_unchecked=2,
            command=self._theme_changed,
        )
        self.dark_radio.grid(row=1, column=2, sticky="w", padx=(0, 24), pady=12)

        self.email_label = ctk.CTkLabel(self.account_card, text="Mentor Email", font=font(14), anchor="w")
        self.email_label.grid(row=2, column=0, sticky="w", padx=24, pady=8)
        self.email_entry = ctk.CTkEntry(
            self.account_card,
            textvariable=self.mentor_email,
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(14),
            placeholder_text="mentor@example.com",
        )
        self.email_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 24), pady=8)

        self.camera_label = ctk.CTkLabel(self.account_card, text="Camera Index", font=font(14), anchor="w")
        self.camera_label.grid(row=3, column=0, sticky="w", padx=24, pady=8)
        self.camera_entry = ctk.CTkEntry(
            self.account_card,
            textvariable=self.camera_index,
            height=38,
            width=120,
            corner_radius=8,
            border_width=0,
            font=font(14),
        )
        self.camera_entry.grid(row=3, column=1, sticky="w", padx=(0, 24), pady=8)

        self.demo_label = ctk.CTkLabel(self.account_card, text="Demo Video", font=font(14), anchor="w")
        self.demo_label.grid(row=4, column=0, sticky="w", padx=24, pady=(8, 24))
        self.demo_path_label = ctk.CTkLabel(self.account_card, text="Chưa chọn video", font=font(13), anchor="w")
        self.demo_path_label.grid(row=4, column=1, sticky="ew", padx=(0, 10), pady=(8, 24))
        self.demo_button = ctk.CTkButton(
            self.account_card,
            text="Chọn .mp4",
            height=36,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self._select_demo_video,
        )
        self.demo_button.grid(row=4, column=2, sticky="e", padx=(0, 24), pady=(8, 24))

        self.keyword_card = Card(self, theme)
        self.keyword_card.grid(row=2, column=0, sticky="nsew", padx=32, pady=(0, 32))
        self.keyword_card.grid_columnconfigure(1, weight=1)
        self.keyword_card.grid_rowconfigure(5, weight=1)

        self.keyword_title = ctk.CTkLabel(
            self.keyword_card,
            text="OS TRACKER KEYWORDS",
            font=font(16, "bold"),
            anchor="w",
        )
        self.keyword_title.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(22, 14))

        self.productive_label = ctk.CTkLabel(self.keyword_card, text="Productive", font=font(14), anchor="w")
        self.productive_label.grid(row=1, column=0, sticky="w", padx=24, pady=12)
        self.productive_entry = ctk.CTkEntry(
            self.keyword_card,
            textvariable=self.productive_keywords,
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(14),
        )
        self.productive_entry.grid(row=1, column=1, sticky="ew", padx=(0, 24), pady=12)

        self.distracting_label = ctk.CTkLabel(self.keyword_card, text="Distracting", font=font(14), anchor="w")
        self.distracting_label.grid(row=2, column=0, sticky="w", padx=24, pady=(12, 24))
        self.distracting_entry = ctk.CTkEntry(
            self.keyword_card,
            textvariable=self.distracting_keywords,
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(14),
        )
        self.distracting_entry.grid(row=2, column=1, sticky="ew", padx=(0, 24), pady=12)

        self.threshold_label = ctk.CTkLabel(self.keyword_card, text="AI Threshold", font=font(14), anchor="w")
        self.threshold_label.grid(row=3, column=0, sticky="w", padx=24, pady=12)
        threshold_row = ctk.CTkFrame(self.keyword_card, fg_color="transparent", border_width=0)
        threshold_row.grid(row=3, column=1, sticky="ew", padx=(0, 24), pady=12)
        threshold_row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.threshold_entry = self._small_entry(threshold_row, self.engagement_threshold, 0)
        self.smoothing_entry = self._small_entry(threshold_row, self.smoothing_window, 1)
        self.os_ai_entry = self._small_entry(threshold_row, self.os_ai_threshold, 2)
        self.os_override_entry = self._small_entry(threshold_row, self.os_override_threshold, 3)

        self.countdown_label = ctk.CTkLabel(self.keyword_card, text="Hardcore Countdown", font=font(14), anchor="w")
        self.countdown_label.grid(row=4, column=0, sticky="w", padx=24, pady=(12, 24))
        self.countdown_entry = ctk.CTkEntry(
            self.keyword_card,
            textvariable=self.hardcore_countdown_seconds,
            height=38,
            width=120,
            corner_radius=8,
            border_width=0,
            font=font(14),
        )
        self.countdown_entry.grid(row=4, column=1, sticky="w", padx=(0, 24), pady=(12, 24))

        action_row = ctk.CTkFrame(self.keyword_card, fg_color="transparent", border_width=0)
        action_row.grid(row=5, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 22))
        action_row.grid_columnconfigure(0, weight=1)
        self.save_status = ctk.CTkLabel(action_row, text="", font=font(13), anchor="w")
        self.save_status.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.save_button = ctk.CTkButton(
            action_row,
            text="LƯU CÀI ĐẶT",
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self._save_clicked,
        )
        self.save_button.grid(row=0, column=1, sticky="e")
        self.apply_theme()

    def tracker_config(self) -> dict[str, object]:
        return {
            "camera_index": self.camera_index.get(),
            "mentor_email": self.mentor_email.get(),
            "demo_video_path": self.demo_video_path.get(),
            "productive_keywords": self.productive_keywords.get(),
            "distracting_keywords": self.distracting_keywords.get(),
            "engagement_threshold": self.engagement_threshold.get(),
            "smoothing_window": self.smoothing_window.get(),
            "os_ai_threshold": self.os_ai_threshold.get(),
            "os_override_threshold": self.os_override_threshold.get(),
            "hardcore_countdown_seconds": self.hardcore_countdown_seconds.get(),
            "theme_mode": self.theme_var.get(),
        }

    def apply_settings(self, settings: dict[str, object]) -> None:
        self.mentor_email.set(str(settings.get("mentor_email") or ""))
        self.camera_index.set(str(settings.get("camera_index", 0)))
        self.demo_video_path.set(str(settings.get("demo_video_path") or ""))
        self._refresh_demo_label()
        self.engagement_threshold.set(str(settings.get("engagement_threshold", 0.54)))
        self.smoothing_window.set(str(settings.get("smoothing_window", 5)))
        self.os_ai_threshold.set(str(settings.get("os_ai_threshold", 0.45)))
        self.os_override_threshold.set(str(settings.get("os_override_threshold", 0.60)))
        self.hardcore_countdown_seconds.set(str(settings.get("hardcore_countdown_seconds", 30)))
        self.productive_keywords.set(str(settings.get("productive_keywords") or "vscode, github, pdf, docx, figma"))
        self.distracting_keywords.set(str(settings.get("distracting_keywords") or "facebook, netflix, lol, tiktok"))

    def apply_theme(self) -> None:
        super().apply_theme()
        self.theme_var.set(self.theme.mode)
        self.header.apply_theme()
        for card in [self.account_card, self.keyword_card]:
            card.apply_theme()

        palette = self.theme.palette()
        labels = [
            self.account_title,
            self.theme_label,
            self.light_radio,
            self.dark_radio,
            self.email_label,
            self.camera_label,
            self.demo_label,
            self.keyword_title,
            self.productive_label,
            self.distracting_label,
            self.threshold_label,
            self.countdown_label,
            self.save_status,
        ]
        for label in labels:
            label.configure(text_color=palette["text_primary"])
        for entry in [
            self.email_entry,
            self.camera_entry,
            self.productive_entry,
            self.distracting_entry,
            self.threshold_entry,
            self.smoothing_entry,
            self.os_ai_entry,
            self.os_override_entry,
            self.countdown_entry,
        ]:
            entry.configure(
                fg_color=palette["input"],
                text_color=palette["text_primary"],
                placeholder_text_color=palette["text_secondary"],
            )
        self.demo_path_label.configure(text_color=palette["text_secondary"])
        self.demo_button.configure(
            fg_color=palette["btn_neutral"],
            hover_color=palette["btn_neutral_hover"],
            text_color=palette["text_primary"],
        )
        self.save_button.configure(
            fg_color=palette["accent_focus"],
            hover_color=palette["accent_focus"],
            text_color="#FFFFFF",
        )
        self.save_status.configure(text_color=palette["text_secondary"])

    def _theme_changed(self) -> None:
        self.controller.set_theme(self.theme_var.get())
        self.save_status.configure(text="Theme đã đổi. Bấm lưu để giữ các cài đặt khác.")

    def _small_entry(self, parent, variable: ctk.StringVar, column: int) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=36,
            corner_radius=8,
            border_width=0,
            font=font(13),
        )
        entry.grid(row=0, column=column, sticky="ew", padx=(0, 8))
        return entry

    def _select_demo_video(self) -> None:
        open_video_file_picker(self, self.theme, self.demo_video_path.get(), self._set_demo_video)

    def _set_demo_video(self, selected: str) -> None:
        self.demo_video_path.set(selected)
        self._refresh_demo_label()
        update_settings = getattr(self.controller, "update_settings", None)
        if callable(update_settings):
            update_settings({"demo_video_path": selected})

    def _save_clicked(self) -> None:
        update_settings = getattr(self.controller, "update_settings", None)
        if callable(update_settings):
            update_settings(self.tracker_config())
            self.save_status.configure(text="Đã lưu cài đặt.")

    def _refresh_demo_label(self) -> None:
        path = self.demo_video_path.get().strip()
        self.demo_path_label.configure(text=Path(path).name if path else "Chưa chọn video")
