from __future__ import annotations

from collections import deque
import tkinter as tk

import customtkinter as ctk

from ui.theme import APP_FONT_FAMILY


class FocusTrendChart(ctk.CTkFrame):
    def __init__(self, parent, max_points: int = 180, palette: dict[str, str] | None = None, **kwargs) -> None:
        self._palette = palette or {
            "input": "#101a2a",
            "text_secondary": "#8191ad",
            "accent_focus": "#37d69b",
            "accent_warn": "#E74C3C",
        }
        super().__init__(parent, corner_radius=14, fg_color=self._palette["input"], **kwargs)
        self._scores: deque[float] = deque(maxlen=max_points)

        self.canvas = tk.Canvas(self, bg=self._palette["input"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas.bind("<Configure>", lambda _event: self._redraw())

    def apply_theme(self, palette: dict[str, str]) -> None:
        self._palette = palette
        self.configure(fg_color=palette["input"])
        self.canvas.configure(bg=palette["input"])
        self._redraw()

    def clear(self) -> None:
        self._scores.clear()
        self._redraw()

    def add_score(self, score: float) -> None:
        clamped = max(0.0, min(1.0, float(score)))
        self._scores.append(clamped)
        self._redraw()

    def _redraw(self) -> None:
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())

        guide_color = "#D1D5DB" if self._palette.get("bg_app") == "#F3F4F6" else "#2A2A2A"
        muted_color = self._palette["text_secondary"]
        for value in [0.0, 0.5, 1.0]:
            y = height - int(value * (height - 24)) - 12
            self.canvas.create_line(8, y, width - 8, y, fill=guide_color, dash=(2, 3))
            self.canvas.create_text(12, y - 8, text=f"{int(value * 100)}%", fill=muted_color, anchor="w")

        threshold_y = height - int(0.54 * (height - 24)) - 12
        self.canvas.create_line(8, threshold_y, width - 8, threshold_y, fill=self._palette["accent_warn"], dash=(4, 4))

        if len(self._scores) < 2:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="Waiting for focus data...",
                fill=muted_color,
                font=(APP_FONT_FAMILY, 12),
            )
            return

        left = 14
        right = width - 14
        top = 14
        bottom = height - 14
        span_x = max(1, right - left)
        span_y = max(1, bottom - top)

        points: list[float] = []
        for idx, score in enumerate(self._scores):
            x = left + (idx / max(1, len(self._scores) - 1)) * span_x
            y = bottom - score * span_y
            points.extend([x, y])

        self.canvas.create_line(*points, fill=self._palette["accent_focus"], width=2, smooth=True)
