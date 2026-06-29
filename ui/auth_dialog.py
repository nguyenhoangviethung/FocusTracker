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
    QFrame,
    QWidget,
)
from PyQt6.QtCore import Qt

from edge.auth_client import AuthClient, AuthRequestError
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
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        hero = QFrame()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 28, 28, 28)
        hero_layout.setSpacing(8)
        hero.setObjectName("bg_card")
        hero_title = QLabel("FocusFlow AI")
        hero_title.setFont(font(28, bold=True))
        hero_subtitle = QLabel("Welcome back. Sign in to keep sessions, reports, and cloud sync in one place.")
        hero_subtitle.setWordWrap(True)
        hero_subtitle.setObjectName("text_secondary")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)
        layout.addWidget(hero)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
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
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Enter your username")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Enter your password")
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("Optional display name")

        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        form.addRow("Display name", self.display_name_edit)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.login_btn = QPushButton("Sign in")
        self.register_btn = QPushButton("Create account")
        self.login_btn.clicked.connect(self._login_password)
        self.register_btn.clicked.connect(self._register_password)
        self.login_btn.setObjectName("accent_focus")
        self.login_btn.setMinimumHeight(44)
        self.register_btn.setMinimumHeight(44)
        btn_row.addWidget(self.login_btn)
        btn_row.addWidget(self.register_btn)
        layout.addLayout(btn_row)

        self.password_status = QLabel("")
        self.password_status.setWordWrap(True)
        layout.addWidget(self.password_status)
        layout.addStretch()

    def _build_google_tab(self) -> None:
        layout = QVBoxLayout(self.google_tab)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(14)
        hint = QLabel(
            "This uses the desktop OAuth client values loaded from `.env`. "
            "A browser window will open and the callback lands on localhost."
        )
        hint.setWordWrap(True)
        hint.setObjectName("text_secondary")
        layout.addWidget(hint)

        self.google_btn = QPushButton("Sign in with Google")
        self.google_btn.setObjectName("accent_focus")
        self.google_btn.clicked.connect(self._login_google)
        self.google_btn.setMinimumHeight(46)
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
        raw = str(
            os.getenv(
                "FOCUSFLOW_GOOGLE_OAUTH_SCOPES",
                "openid https://www.googleapis.com/auth/userinfo.email",
            )
        )
        return tuple(item for item in raw.split() if item)

    def _apply_profile(self, profile: dict) -> None:
        self._profile = profile
        self.authenticated.emit(profile)
        self.accept()

    def _friendly_auth_message(self, exc: Exception) -> str:
        message = str(exc).strip() or "Unknown error"
        lowered = message.lower()
        if isinstance(exc, AuthRequestError):
            if exc.status_code == 422:
                return message
            if exc.status_code == 409:
                return message
            if exc.status_code == 401:
                return "Thông tin đăng nhập không đúng."
            if exc.status_code == 404:
                return "Máy chủ chưa sẵn sàng cho chức năng đăng nhập."
            if exc.status_code >= 500:
                return "Máy chủ đang gặp lỗi tạm thời. Vui lòng thử lại sau."
        if "invalid username or password" in lowered:
            return "Tên đăng nhập hoặc mật khẩu không đúng."
        if "user not found" in lowered:
            return "Tài khoản này chưa tồn tại."
        if "google oauth env is missing" in lowered:
            return "Cấu hình đăng nhập Google chưa sẵn sàng. Vui lòng thử lại sau."
        if "cloud api auth endpoint is missing" in lowered:
            return "Máy chủ chưa sẵn sàng cho đăng nhập. Vui lòng thử lại sau."
        if "internal server error" in lowered:
            return "Máy chủ đang gặp lỗi tạm thời. Vui lòng thử lại sau."
        return "Không thể đăng nhập lúc này. Vui lòng thử lại sau."

    def _run_request(self, fn, status_label: QLabel) -> None:
        status_label.setText("Working...")
        try:
            profile = fn()
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, AuthRequestError):
                logger.warning(
                    "Authentication request rejected with HTTP %s: %s",
                    exc.status_code,
                    exc,
                )
            else:
                logger.error("Authentication failed: %s", exc)
            friendly_message = self._friendly_auth_message(exc)
            status_label.setText(friendly_message)
            QMessageBox.warning(self, "Login failed", friendly_message)
            return
        self._apply_profile(profile.model_dump(mode="json"))

    def _register_password(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        display_name = self.display_name_edit.text().strip() or None
        if not username or not password:
            self.password_status.setText("Username and password are required.")
            return
        if len(password) < 8:
            self.password_status.setText("Mật khẩu phải có ít nhất 8 ký tự.")
            QMessageBox.warning(self, "Login failed", "Mật khẩu phải có ít nhất 8 ký tự.")
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
        if len(password) < 8:
            self.password_status.setText("Mật khẩu phải có ít nhất 8 ký tự.")
            QMessageBox.warning(self, "Login failed", "Mật khẩu phải có ít nhất 8 ký tự.")
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
        p = self.theme.palette()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {p['border']};
                border-radius: 14px;
                background-color: {p['bg_card']};
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {p['text_secondary']};
                padding: 10px 16px;
                margin-right: 4px;
                border: 1px solid {p['border']};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
            QTabBar::tab:selected {{
                color: {p['text_primary']};
                background-color: {p['bg_card']};
                border-bottom-color: {p['bg_card']};
            }}
        """)
