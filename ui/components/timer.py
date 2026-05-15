from __future__ import annotations

import customtkinter as ctk


def format_seconds(total_seconds: int) -> str:
    total = max(0, int(total_seconds))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class TimerChip(ctk.CTkFrame):
    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, corner_radius=14, fg_color="#1a2638", **kwargs)
        self._value_label = ctk.CTkLabel(
            self,
            text="00:00",
            font=ctk.CTkFont(family="Segoe UI", size=34, weight="bold"),
            text_color="#f5f7fb",
        )
        self._value_label.pack(padx=18, pady=12)

    def set_seconds(self, seconds: int) -> None:
        self._value_label.configure(text=format_seconds(seconds))
