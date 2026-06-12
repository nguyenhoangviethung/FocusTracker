from __future__ import annotations

import os
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from edge.auth_client import AuthClient
from ui.theme import ThemeManager, font
from utils.logger import get_logger


logger = get_logger("auth_dialog")


class AuthDialog(QDialog):
    authenticated = pyqtSignal(dict)

    def __init__(self, theme: ThemeManager | None, settings: dict[str, str]) -> None:
        super().__init__()
        self.theme = theme or ThemeManager("Dark")
        self.settings = settings
        self._profile: dict | None = None

        self.setWindowTitle("FocusFlow Sign In")
        self.setModal(True)
        self.resize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Sign in to FocusFlow")
        title.setFont(font(22, bold=True))
        subtitle = QLabel("Use username/password or Google sign-in to tag sessions with a stable user identity.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("text_secondary")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.password_tab = QWidget()
        self.google_tab = QWidget()
        self.tabs.addTab(self.password_tab, "Username / Password")
        self.tabs.addTab(self.google_tab, "Google OAuth")

        self._build_password_tab()
        self._build_google_tab()

        footer = QHBoxLayout()
        self.continue_btn = QPushButton("Continue Offline")
        self.continue_btn.clicked.connect(self.reject)
        footer.addStretch()
        footer.addWidget(self.continue_btn)
        layout.addLayout(footer)

        self.apply_theme()

    def _build_password_tab(self) -> None:
        layout = QVBoxLayout(self.password_tab)
        form = QFormLayout()

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("student01")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("••••••••")
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("Optional display name")

        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        form.addRow("Display name", self.display_name_edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.register_btn = QPushButton("Create account")
        self.login_btn = QPushButton("Sign in")
        self.register_btn.clicked.connect(self._register_password)
        self.login_btn.clicked.connect(self._login_password)
        btn_row.addWidget(self.register_btn)
        btn_row.addWidget(self.login_btn)
        layout.addLayout(btn_row)

        self.password_status = QLabel("")
        self.password_status.setWordWrap(True)
        layout.addWidget(self.password_status)
        layout.addStretch()

    def _build_google_tab(self) -> None:
        layout = QVBoxLayout(self.google_tab)
        hint = QLabel(
            "This uses the desktop OAuth client values loaded from .env. "
            "A browser window will open and the callback lands on localhost."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.google_btn = QPushButton("Sign in with Google")
        self.google_btn.setObjectName("accent_focus")
        self.google_btn.clicked.connect(self._login_google)
        layout.addWidget(self.google_btn)

        self.google_status = QLabel("")
        self.google_status.setWordWrap(True)
        layout.addWidget(self.google_status)
        layout.addStretch()

    def _client(self) -> AuthClient:
        api_url = str(
            os.getenv("FOCUSFLOW_CLOUD_API_URL", "")
            or self.settings.get("cloud_api_url")
            or "http://127.0.0.1:8080"
        )
        api_key = str(
            os.getenv("FOCUSFLOW_CLOUD_API_KEY", "")
            or self.settings.get("cloud_api_key")
        )
        return AuthClient(api_url=api_url, api_key=api_key)

    def _oauth_scopes(self) -> tuple[str, ...]:
        raw = str(os.getenv("FOCUSFLOW_GOOGLE_OAUTH_SCOPES", "openid email profile"))
        return tuple(item for item in raw.split() if item)

    def _apply_profile(self, profile: dict) -> None:
        self._profile = profile
        self.authenticated.emit(profile)
        self.accept()

    def _run_request(self, fn, status_label: QLabel) -> None:
        status_label.setText("Working...")
        try:
            profile = fn()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Authentication failed")
            status_label.setText(f"Login failed: {exc}")
            QMessageBox.critical(self, "Login failed", str(exc))
            return
        self._apply_profile(profile.model_dump(mode="json"))

    def _register_password(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        display_name = self.display_name_edit.text().strip() or None
        if not username or not password:
            self.password_status.setText("Username and password are required.")
            return
        self._run_request(
            lambda: self._client().register_password(username, password, display_name),
            self.password_status,
        )

    def _login_password(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self.password_status.setText("Username and password are required.")
            return
        self._run_request(
            lambda: self._client().login_password(username, password),
            self.password_status,
        )

    def _login_google(self) -> None:
        client = self._client()
        logger.info("Starting Google OAuth login against %s", client.api_url)
        self._run_request(
            lambda: client.login_google(self._oauth_scopes()),
            self.google_status,
        )

    def profile(self) -> dict[str, str] | None:
        return self._profile

    def apply_theme(self) -> None:
        self.setStyleSheet(self.theme.get_stylesheet())
