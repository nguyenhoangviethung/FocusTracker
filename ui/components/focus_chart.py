from __future__ import annotations

from collections import deque
import tkinter as tk

import customtkinter as ctk


class FocusTrendChart(ctk.CTkFrame):
    def __init__(self, parent, max_points: int = 180, **kwargs) -> None:
        super().__init__(parent, corner_radius=14, fg_color="#101a2a", **kwargs)
        self._scores: deque[float] = deque(maxlen=max_points)

        self.canvas = tk.Canvas(self, bg="#101a2a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas.bind("<Configure>", lambda _event: self._redraw())

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

        # Vẽ lưới ngang để quan sát xu hướng điểm tập trung.
        guide_color = "#223049"
        for index, value in enumerate([0.0, 0.5, 1.0]):
            y = height - int(value * (height - 24)) - 12
            self.canvas.create_line(8, y, width - 8, y, fill=guide_color, dash=(2, 3))
            self.canvas.create_text(12, y - 8, text=f"{int(value * 100)}%", fill="#8191ad", anchor="w")

        if len(self._scores) < 2:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="Chờ dữ liệu focus...",
                fill="#7f90ad",
                font=("Segoe UI", 12),
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

        self.canvas.create_line(*points, fill="#37d69b", width=2, smooth=True)
