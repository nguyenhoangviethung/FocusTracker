from __future__ import annotations
from collections.abc import Callable
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import ThemeManager, font

class SidebarNavigation(QFrame):
    route_selected = pyqtSignal(str)

    def __init__(self, theme: ThemeManager, on_toggle_theme: Callable[[], None]) -> None:
        super().__init__()
        self.theme = theme
        self.on_toggle_theme = on_toggle_theme
        self.setObjectName("bg_sidebar")
        self.setFixedWidth(220)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(8)

        self.logo = QLabel("FocusFlow")
        self.logo.setFont(font(20, bold=True))
        
        self.subtitle = QLabel("AI Pomodoro")
        self.subtitle.setFont(font(12))
        self.user_label = QLabel("Not signed in")
        self.user_label.setWordWrap(True)
        self.user_label.setFont(font(11))
        
        layout.addWidget(self.logo)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.user_label)
        layout.addSpacing(24)

        self._buttons = {}
        items = [
            ("home", "Home"),
            ("active_session", "Active"),
            ("vision", "Vision"),
            ("report", "Report"),
            ("settings", "Settings"),
        ]

        for key, label in items:
            btn = QPushButton(label)
            btn.setFont(font(13, bold=True))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_click(k))
            layout.addWidget(btn)
            self._buttons[key] = btn

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.theme_btn = QPushButton("Dark Mode")
        self.theme_btn.setFont(font(13, bold=True))
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.on_toggle_theme)
        layout.addWidget(self.theme_btn)

        self.set_active("home")

    def _on_click(self, key: str) -> None:
        self.set_active(key)
        self.route_selected.emit(key)

    def set_active(self, active_key: str) -> None:
        self.active_key = active_key
        self.apply_theme()

    def apply_theme(self) -> None:
        p = self.theme.palette()
        self.setStyleSheet(f"""
            QFrame#bg_sidebar {{
                background-color: {p['bg_sidebar']};
                border-right: 1px solid {p['border']};
            }}
        """)
        self.logo.setStyleSheet(f"color: {p['text_primary']};")
        self.subtitle.setStyleSheet(f"color: {p['text_secondary']};")
        self.user_label.setStyleSheet(f"color: {p['text_secondary']};")
        
        for key, btn in self._buttons.items():
            if key == self.active_key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {p['accent_focus']};
                        color: white;
                        text-align: left;
                        padding-left: 16px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {p['text_primary']};
                        text-align: left;
                        padding-left: 16px;
                    }}
                    QPushButton:hover {{
                        background-color: {p['sidebar_hover']};
                    }}
                """)
        
        self.theme_btn.setText("Light Mode" if self.theme.mode == "Dark" else "Dark Mode")
        self.theme_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {p['btn_neutral']};
                color: {p['text_primary']};
            }}
            QPushButton:hover {{
                background-color: {p['btn_neutral_hover']};
            }}
        """)

    def set_user_identity(self, display_name: str | None, username: str | None, provider: str | None) -> None:
        parts = [part for part in [display_name or username, provider] if part]
        if not parts:
            self.user_label.setText("Not signed in")
            return
        self.user_label.setText(" | ".join(parts))
