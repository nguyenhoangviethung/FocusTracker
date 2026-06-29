from __future__ import annotations
from typing import Callable
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QPalette, QColor

class ThemeManager:
    _PALETTES = {
        "Light": {
            "bg_app": "#F4F7FB",
            "bg_sidebar": "#FFFFFF",
            "bg_card": "#FFFFFF",
            "bg_surface": "#F8FBFF",
            "text_primary": "#0F172A",
            "text_secondary": "#64748B",
            "accent_focus": "#2563EB",
            "accent_focus_soft": "#DBEAFE",
            "accent_warn": "#E11D48",
            "btn_neutral": "#F1F5F9",
            "btn_neutral_hover": "#E2E8F0",
            "sidebar_hover": "#EEF4FF",
            "input": "#FFFFFF",
            "border": "#DCE3EE",
            "border_soft": "#E8EEF6",
        },
        "Dark": {
            "bg_app": "#0B1220",
            "bg_sidebar": "#111827",
            "bg_card": "#121A2A",
            "bg_surface": "#0F172A",
            "text_primary": "#F8FAFC",
            "text_secondary": "#94A3B8",
            "accent_focus": "#3B82F6",
            "accent_focus_soft": "#1D4ED8",
            "accent_warn": "#FB7185",
            "btn_neutral": "#1F2937",
            "btn_neutral_hover": "#273244",
            "sidebar_hover": "#172033",
            "input": "#0F172A",
            "border": "#223046",
            "border_soft": "#1F2A3F",
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
                font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
            }}
            QMainWindow, QDialog, #bg_app {{
                background-color: {p['bg_app']};
            }}
            #bg_sidebar {{
                background-color: {p['bg_sidebar']};
                border-right: 1px solid {p['border']};
            }}
            #bg_card {{
                background-color: {p['bg_card']};
                border-radius: 18px;
                border: 1px solid {p['border_soft']};
            }}
            QLabel#text_secondary {{
                color: {p['text_secondary']};
            }}
            QPushButton {{
                background-color: {p['btn_neutral']};
                color: {p['text_primary']};
                border: none;
                border-radius: 12px;
                padding: 10px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {p['btn_neutral_hover']};
            }}
            QPushButton#accent_focus {{
                background-color: {p['accent_focus']};
                color: white;
            }}
            QPushButton#accent_focus:hover {{
                background-color: {p['accent_focus_soft']};
            }}
            QPushButton#accent_warn {{
                background-color: {p['accent_warn']};
                color: white;
            }}
            QPushButton#accent_warn:hover {{
                background-color: {p['accent_warn']};
            }}
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
                background-color: {p['input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 12px;
                padding: 10px 12px;
                selection-background-color: {p['accent_focus']};
                selection-color: white;
            }}
            QComboBox {{
                padding-right: 28px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox:on {{
                border-color: {p['accent_focus']};
            }}
            QTabWidget::pane {{
                border: 1px solid {p['border']};
                border-radius: 14px;
                background-color: {p['bg_card']};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {p['text_secondary']};
                padding: 10px 16px;
                border: 1px solid transparent;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {p['accent_focus']};
                border-bottom: 2px solid {p['accent_focus']};
            }}
            QTabBar::tab:hover {{
                color: {p['text_primary']};
            }}
            QComboBox::down-arrow {{
                image: none; /* Can add a custom arrow image if needed */
            }}
            QComboBox QAbstractItemView, QComboBox QListView {{
                background-color: {p['input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 12px;
                padding: 4px;
                outline: 0;
                selection-background-color: {p['accent_focus']};
                selection-color: white;
            }}
            QComboBox QAbstractItemView::item, QComboBox QListView::item {{
                min-height: 28px;
                padding: 6px 8px;
                border-radius: 8px;
            }}
            QComboBox QAbstractItemView::item:hover, QComboBox QListView::item:hover {{
                background-color: {p['btn_neutral_hover']};
                color: {p['text_primary']};
            }}
            QComboBox QAbstractItemView::item:selected, QComboBox QListView::item:selected {{
                background-color: {p['accent_focus']};
                color: white;
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

    def combo_box_stylesheet(self) -> str:
        p = self.palette()
        return f"""
            QComboBox {{
                background-color: {p['input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 12px;
                padding: 10px 12px;
                padding-right: 28px;
                selection-background-color: {p['accent_focus']};
                selection-color: white;
            }}
            QComboBox:on {{
                border-color: {p['accent_focus']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox:hover {{
                border-color: {p['accent_focus']};
            }}
            QComboBox::down-arrow {{
                image: none;
            }}
        """

    def combo_popup_stylesheet(self) -> str:
        p = self.palette()
        return f"""
            QListView {{
                background-color: {p['input']};
                color: {p['text_primary']};
                border: 1px solid {p['border']};
                border-radius: 12px;
                padding: 4px;
                outline: 0;
                selection-background-color: {p['accent_focus']};
                selection-color: white;
            }}
            QListView::item {{
                min-height: 28px;
                padding: 6px 8px;
                border-radius: 8px;
            }}
            QListView::item:hover {{
                background-color: {p['btn_neutral_hover']};
                color: {p['text_primary']};
            }}
            QListView::item:selected {{
                background-color: {p['accent_focus']};
                color: white;
            }}
        """

def font(size: int, bold: bool = False) -> QFont:
    f = QFont("Inter", size)
    f.setBold(bold)
    return f
