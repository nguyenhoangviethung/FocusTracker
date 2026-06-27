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
        self._threshold = 0.5
        self.setMinimumHeight(150)
        self._scores: deque[float] = deque(maxlen=max_points)

    def apply_theme(self, palette: dict) -> None:
        self._palette = palette
        self.update()

    def set_threshold(self, value: float) -> None:
        self._threshold = max(0.0, min(1.0, float(value)))
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
        
        padding = 16
        left = padding
        right = w - padding
        top = padding
        bottom = h - padding
        
        span_x = max(1, right - left)
        span_y = max(1, bottom - top)
        
        # Grid lines
        pen = QPen(guide_color, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        for value in [0.0, 0.5, 1.0]:
            y = bottom - int(value * span_y)
            painter.drawLine(left, y, right, y)
            painter.setPen(QPen(QColor(self._palette["text_secondary"])))
            painter.setFont(font(10))
            painter.drawText(left + 4, y - 4, f"{int(value * 100)}%")
            painter.setPen(pen)

        # Visual guide for P(high). It is not the 4-class decision rule.
        warn_pen = QPen(QColor(self._palette["accent_warn"]), 1, Qt.PenStyle.DashLine)
        painter.setPen(warn_pen)
        threshold_y = bottom - int(self._threshold * span_y)
        painter.drawLine(left, threshold_y, right, threshold_y)
        
        painter.setPen(QColor(self._palette["accent_warn"]))
        painter.setFont(font(9))
        painter.drawText(right - 72, threshold_y - 4, f"Guide: {int(self._threshold * 100)}%")

        if len(self._scores) < 2:
            painter.setPen(QColor(self._palette["text_secondary"]))
            painter.setFont(font(12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for focus data...")
            return

        # Gather points
        max_capacity = self._scores.maxlen if self._scores.maxlen else 180
        step = span_x / max(1, max_capacity - 1)
        points = []
        for idx, score in enumerate(self._scores):
            x = right - (len(self._scores) - 1 - idx) * step
            y = bottom - score * span_y
            points.append((x, y))

        # Build spline path
        path = QPainterPath()
        if points:
            path.moveTo(points[0][0], points[0][1])
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i+1]
                dx = (p2[0] - p1[0]) / 2.0
                path.cubicTo(p1[0] + dx, p1[1], p2[0] - dx, p2[1], p2[0], p2[1])

            # Draw gradient area fill
            from PyQt6.QtGui import QLinearGradient
            fill_path = QPainterPath(path)
            fill_path.lineTo(points[-1][0], bottom)
            fill_path.lineTo(points[0][0], bottom)
            fill_path.closeSubpath()

            gradient = QLinearGradient(0, top, 0, bottom)
            focus_color = QColor(self._palette.get("accent_focus", "#1E5EEB"))
            color_top = QColor(focus_color.red(), focus_color.green(), focus_color.blue(), 60)
            color_bottom = QColor(focus_color.red(), focus_color.green(), focus_color.blue(), 0)
            gradient.setColorAt(0.0, color_top)
            gradient.setColorAt(1.0, color_bottom)
            painter.fillPath(fill_path, gradient)

        # Draw the line
        line_pen = QPen(QColor(self._palette.get("accent_focus", "#1E5EEB")), 2)
        painter.setPen(line_pen)
        painter.drawPath(path)
