from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt6.QtCore import Qt
from ui.theme import ThemeManager, font

class PageTitle(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        self.title_label = QLabel(title)
        self.title_label.setFont(font(24, bold=True))
        
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(font(13))
        self.subtitle_label.setObjectName("text_secondary")
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)

    def apply_theme(self, theme: ThemeManager) -> None:
        p = theme.palette()
        self.title_label.setStyleSheet(f"color: {p['text_primary']};")
        self.subtitle_label.setStyleSheet(f"color: {p['text_secondary']};")

class Card(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("bg_card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(16)

class ThemedPage(QWidget):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.theme = theme
        self.setObjectName("bg_app")

    def apply_theme(self) -> None:
        self.setStyleSheet(self.theme.get_stylesheet())
        
    def apply_settings(self, settings: dict) -> None:
        pass
