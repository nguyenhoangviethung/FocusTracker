from __future__ import annotations
from collections.abc import Callable
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import ThemeManager, font

class SidebarNavigation(QFrame):
    route_selected = pyqtSignal(str)
    logout_requested = pyqtSignal()

    def __init__(self, theme: ThemeManager, on_toggle_theme: Callable[[], None]) -> None:
        super().__init__()
        self.theme = theme
        self.on_toggle_theme = on_toggle_theme
        self.setObjectName("bg_sidebar")
        self.setFixedWidth(246)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 20)
        layout.setSpacing(10)

        self.logo = QLabel("FocusFlow")
        self.logo.setFont(font(22, bold=True))
        self.logo.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.user_label = QLabel("Not signed in")
        self.user_label.setWordWrap(True)
        self.user_label.setFont(font(11))
        self.user_label.setMaximumWidth(200)
        
        layout.addWidget(self.logo)
        layout.addWidget(self.user_label)
        layout.addSpacing(18)

        self.new_btn = QPushButton("+ New Session")
        self.new_btn.setFont(font(13, bold=True))
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.clicked.connect(lambda: self._on_click("home"))
        self.new_btn.setObjectName("accent_focus")
        self.new_btn.setMinimumHeight(42)
        
        new_btn_layout = QHBoxLayout()
        new_btn_layout.setContentsMargins(0,0,0,0)
        new_btn_layout.addWidget(self.new_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(new_btn_layout)
        layout.addSpacing(18)

        self._buttons = {}
        items = [
            ("home", "Dashboard"),
            ("active_session", "Live Session"),
            ("vision", "Vision Settings"),
            ("report", "History"),
            ("settings", "App Settings"),
        ]

        for key, label in items:
            btn = QPushButton(label)
            btn.setFont(font(13, bold=True))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_click(k))
            btn.setMinimumHeight(42)
            layout.addWidget(btn)
            self._buttons[key] = btn

        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.system_card = QFrame()
        self.system_card.setObjectName("bg_card")
        sc_layout = QVBoxLayout(self.system_card)
        sc_layout.setContentsMargins(16, 16, 16, 16)
        sc_layout.setSpacing(6)
        self.sc_title = QLabel("System Status")
        self.sc_title.setFont(font(12, bold=True))
        self.sc_desc = QLabel("Ready for inference\nNo active session")
        self.sc_desc.setFont(font(11))
        self.sc_desc.setWordWrap(True)
        sc_layout.addWidget(self.sc_title)
        sc_layout.addWidget(self.sc_desc)
        layout.addWidget(self.system_card)
        layout.addSpacing(14)

        self.theme_btn = QPushButton("Toggle Theme")
        self.theme_btn.setFont(font(13, bold=True))
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.on_toggle_theme)
        self.theme_btn.setMinimumHeight(42)
        layout.addWidget(self.theme_btn)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setFont(font(13, bold=True))
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.setMinimumHeight(42)
        self.logout_btn.clicked.connect(self.logout_requested.emit)
        layout.addWidget(self.logout_btn)

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
        self.user_label.setStyleSheet(f"color: {p['text_secondary']};")
        self.system_card.setStyleSheet(f"QFrame#bg_card {{ background-color: {p['bg_surface']}; border-radius: 16px; border: 1px solid {p['border_soft']}; }}")
        self.sc_title.setStyleSheet(f"color: {p['text_primary']};")
        self.sc_desc.setStyleSheet(f"color: {p['text_secondary']};")
        
        for key, btn in self._buttons.items():
            if key == self.active_key:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {p['sidebar_hover']};
                        color: {p['accent_focus']};
                        text-align: left;
                        padding-left: 16px;
                        border: 1px solid {p['border_soft']};
                        border-radius: 12px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {p['text_secondary']};
                        text-align: left;
                        padding-left: 16px;
                        border: 1px solid transparent;
                        border-radius: 12px;
                    }}
                    QPushButton:hover {{
                        color: {p['text_primary']};
                        background-color: {p['sidebar_hover']};
                    }}
                """)
        
        self.theme_btn.setText("Light Mode" if self.theme.mode == "Dark" else "Dark Mode")
        self.theme_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {p['btn_neutral']};
                color: {p['text_primary']};
                text-align: center;
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
