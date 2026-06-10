from __future__ import annotations
from typing import Callable
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QPalette, QColor

class ThemeManager:
    _PALETTES = {
        "Light": {
            "bg_app": "#E5E7EB",
            "bg_sidebar": "#F9FAFB",
            "bg_card": "#FFFFFF",
            "text_primary": "#111827",
            "text_secondary": "#4B5563",
            "accent_focus": "#10B981",
            "accent_warn": "#EF4444",
            "btn_neutral": "#D1D5DB",
            "btn_neutral_hover": "#9CA3AF",
            "sidebar_hover": "#E5E7EB",
            "input": "#FFFFFF",
            "border": "#9CA3AF",
        },
        "Dark": {
            "bg_app": "#0F0F0F",
            "bg_sidebar": "#141414",
            "bg_card": "#1A1A1A",
            "text_primary": "#FFFFFF",
            "text_secondary": "#888888",
            "accent_focus": "#2ECC71",
            "accent_warn": "#E74C3C",
            "btn_neutral": "#333333",
            "btn_neutral_hover": "#404040",
            "sidebar_hover": "#1F1F1F",
            "input": "#222222",
            "border": "#333333",
        },
    }

    def __init__(self, initial_mode: str = "Dark") -> None:
        self.mode = "Light" if initial_mode.lower() == "light" else "Dark"
        self._listeners: list[Callable[[], None]] = []

    def color(self, token: str) -> str:
        return self._PALETTES[self.mode][token]

    def palette(self) -> dict[str, str]:
        return dict(self._PALETTES[self.mode])

    def toggle(self) -> None:
        self.mode = "Light" if self.mode == "Dark" else "Dark"
        self._notify()

    def set_mode(self, mode: str) -> None:
        self.mode = "Light" if mode.lower() == "light" else "Dark"
        self._notify()

    def register(self, listener: Callable[[], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def get_stylesheet(self) -> str:
        p = self.palette()
        return f"""
            QWidget {{
                color: {p['text_primary']};
                font-family: 'Inter', 'Segoe UI', sans-serif;
            }}
            QMainWindow, #bg_app {{
                background-color: {p['bg_app']};
            }}
            #bg_sidebar {{
                background-color: {p['bg_sidebar']};
                border-right: 1px solid {p['border']};
            }}
            #bg_card {{
                background-color: {p['bg_card']};
                border-radius: 12px;
                border: 1px solid {p['border']};
            }}
            QPushButton {{
                background-color: {p['btn_neutral']};
                color: {p['text_primary']};
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['btn_neutral_hover']};
            }}
            QPushButton#accent_focus {{
                background-color: {p['accent_focus']};
                color: white;
            }}
            QPushButton#accent_focus:hover {{
                background-color: #059669; /* Darker green */
            }}
            QPushButton#accent_warn {{
                background-color: {p['accent_warn']};
                color: white;
            }}
            QPushButton#accent_warn:hover {{
                background-color: #DC2626; /* Darker red */
            }}
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
                background-color: {p['input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 8px;
                padding: 8px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none; /* Can add a custom arrow image if needed */
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['bg_card']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                selection-background-color: {p['btn_neutral']};
            }}
            QCheckBox, QRadioButton {{
                color: {p['text_primary']};
                spacing: 8px;
            }}
            QCheckBox::indicator, QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {p['border']};
                background-color: {p['input']};
            }}
            QRadioButton::indicator {{
                border-radius: 9px;
            }}
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
                background-color: {p['accent_focus']};
                border: 1px solid {p['accent_focus']};
            }}
            QProgressBar {{
                background-color: {p['input']};
                border-radius: 4px;
                text-align: center;
                color: transparent;
            }}
            QProgressBar::chunk {{
                background-color: {p['accent_focus']};
                border-radius: 4px;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {p['border']};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
        """

def font(size: int, bold: bool = False) -> QFont:
    f = QFont("Inter", size)
    f.setBold(bold)
    return f
