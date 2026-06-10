from __future__ import annotations
from collections import deque
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtCore import Qt
from ui.theme import font

class FocusTrendChart(QWidget):
    def __init__(self, max_points: int = 180, palette: dict | None = None) -> None:
        super().__init__()
        self._palette = palette or {
            "input": "#101a2a",
            "text_secondary": "#8191ad",
            "accent_focus": "#37d69b",
            "accent_warn": "#E74C3C",
        }
        self.setMinimumHeight(150)
        self._scores: deque[float] = deque(maxlen=max_points)

    def apply_theme(self, palette: dict) -> None:
        self._palette = palette
        self.update()

    def clear(self) -> None:
        self._scores.clear()
        self.update()

    def add_score(self, score: float) -> None:
        self._scores.append(max(0.0, min(1.0, float(score))))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(self._palette["input"]))
        
        w, h = self.width(), self.height()
        guide_color = QColor(self._palette["text_secondary"])
        guide_color.setAlpha(50)
        
        # Grid lines
        pen = QPen(guide_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        for value in [0.0, 0.5, 1.0]:
            y = h - int(value * (h - 24)) - 12
            painter.drawLine(8, y, w - 8, y)
            painter.setPen(QPen(QColor(self._palette["text_secondary"])))
            painter.setFont(font(10))
            painter.drawText(12, y - 4, f"{int(value * 100)}%")
            painter.setPen(pen)

        # Threshold
        warn_pen = QPen(QColor(self._palette["accent_warn"]), 1, Qt.PenStyle.DashLine)
        painter.setPen(warn_pen)
        threshold_y = h - int(0.54 * (h - 24)) - 12
        painter.drawLine(8, threshold_y, w - 8, threshold_y)

        if len(self._scores) < 2:
            painter.setPen(QColor(self._palette["text_secondary"]))
            painter.setFont(font(12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for focus data...")
            return

        left, right = 14, w - 14
        top, bottom = 14, h - 14
        span_x, span_y = max(1, right - left), max(1, bottom - top)

        path = QPainterPath()
        for idx, score in enumerate(self._scores):
            x = left + (idx / max(1, len(self._scores) - 1)) * span_x
            y = bottom - score * span_y
            if idx == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        line_pen = QPen(QColor(self._palette["accent_focus"]), 2)
        painter.setPen(line_pen)
        painter.drawPath(path)
