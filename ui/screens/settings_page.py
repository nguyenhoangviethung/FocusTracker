from __future__ import annotations
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QWidget,
    QComboBox,
    QCheckBox,
    QPushButton,
    QListView,
)
from PyQt6.QtCore import Qt

from ui.screens.base import ThemedPage, PageTitle, Card
from ui.theme import ThemeManager, font

class SettingsPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        self.header = PageTitle("Settings", "Configure your focus preferences, notifications, and security.")
        layout.addWidget(self.header)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(24)
        
        # 1. Appearance & Preferences
        self.acc_card = Card()
        scroll_layout.addWidget(self.acc_card)
        t1 = QLabel("Appearance & Device Preferences")
        t1.setFont(font(16, bold=True))
        self.acc_card.layout.addWidget(t1)
        
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme Mode:"))
        self.theme_group = QButtonGroup(self)
        self.rb_light = QRadioButton("Light")
        self.rb_dark = QRadioButton("Dark")
        self.theme_group.addButton(self.rb_light)
        self.theme_group.addButton(self.rb_dark)
        theme_layout.addWidget(self.rb_light)
        theme_layout.addWidget(self.rb_dark)
        theme_layout.addStretch()
        self.acc_card.layout.addLayout(theme_layout)
        
        self.rb_light.clicked.connect(lambda: self._set_theme("Light"))
        self.rb_dark.clicked.connect(lambda: self._set_theme("Dark"))

        autohide_layout = QHBoxLayout()
        self.chk_autohide = QCheckBox("Auto-hide camera preview when starting session")
        autohide_layout.addWidget(self.chk_autohide)
        self.acc_card.layout.addLayout(autohide_layout)

        landmarks_layout = QHBoxLayout()
        self.chk_landmarks = QCheckBox("Show facial landmarks on camera preview")
        landmarks_layout.addWidget(self.chk_landmarks)
        self.acc_card.layout.addLayout(landmarks_layout)

        camera_layout = QHBoxLayout()
        camera_layout.addWidget(QLabel("Webcam Device:"))
        self.camera_combo = QComboBox()
        self.camera_combo.addItems(["Webcam 0 (Default)", "Webcam 1", "Webcam 2", "Webcam 3"])
        self.camera_combo.setFixedWidth(200)
        self._prepare_combo(self.camera_combo)
        camera_layout.addWidget(self.camera_combo)
        camera_layout.addStretch()
        self.acc_card.layout.addLayout(camera_layout)
        
        # 2. Focus & Work Goals
        self.focus_card = Card()
        scroll_layout.addWidget(self.focus_card)
        t_focus = QLabel("Focus & Work Goals")
        t_focus.setFont(font(16, bold=True))
        self.focus_card.layout.addWidget(t_focus)

        goal_layout = QHBoxLayout()
        goal_layout.addWidget(QLabel("Daily Focus Goal:"))
        self.goal_combo = QComboBox()
        self.goal_combo.addItems(["30 Mins", "60 Mins", "120 Mins", "180 Mins", "240 Mins", "300 Mins"])
        self._prepare_combo(self.goal_combo)
        goal_layout.addWidget(self.goal_combo)
        self.focus_card.layout.addLayout(goal_layout)

        session_layout = QHBoxLayout()
        session_layout.addWidget(QLabel("Default Pomodoro Duration:"))
        self.session_combo = QComboBox()
        self.session_combo.addItems(["15 Mins", "25 Mins", "45 Mins", "60 Mins", "90 Mins"])
        self._prepare_combo(self.session_combo)
        session_layout.addWidget(self.session_combo)
        self.focus_card.layout.addLayout(session_layout)

        inference_layout = QHBoxLayout()
        inference_layout.addWidget(QLabel("Inference Mode:"))
        self.inference_combo = QComboBox()
        self.inference_combo.addItem("Edge (Local)", "local")
        self.inference_combo.addItem("Cloud", "cloud")
        self.inference_combo.addItem("Edge + Cloud Sync", "hybrid")
        self._prepare_combo(self.inference_combo)
        inference_layout.addWidget(self.inference_combo)
        inference_layout.addStretch()
        self.focus_card.layout.addLayout(inference_layout)
        
        # 3. Notifications & Sound Alerts
        self.alerts_card = Card()
        scroll_layout.addWidget(self.alerts_card)
        t_alerts = QLabel("Notifications & Sound Alerts")
        t_alerts.setFont(font(16, bold=True))
        self.alerts_card.layout.addWidget(t_alerts)

        self.chk_complete = QCheckBox("Play sound when session completes")
        self.chk_distract = QCheckBox("Play warning sound when distraction is detected")
        self.alerts_card.layout.addWidget(self.chk_complete)
        self.alerts_card.layout.addWidget(self.chk_distract)
        
        # 4. Security Card
        self.pwd_card = Card()
        scroll_layout.addWidget(self.pwd_card)
        t_pwd = QLabel("Security")
        t_pwd.setFont(font(16, bold=True))
        self.pwd_card.layout.addWidget(t_pwd)

        old_pwd_layout = QHBoxLayout()
        old_pwd_layout.addWidget(QLabel("Current Password:"))
        self.old_pwd = QLineEdit()
        self.old_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        old_pwd_layout.addWidget(self.old_pwd)
        self.pwd_card.layout.addLayout(old_pwd_layout)

        new_pwd_layout = QHBoxLayout()
        new_pwd_layout.addWidget(QLabel("New Password:"))
        self.new_pwd = QLineEdit()
        self.new_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        new_pwd_layout.addWidget(self.new_pwd)
        self.pwd_card.layout.addLayout(new_pwd_layout)

        self.change_pwd_btn = QPushButton("Change Password")
        self.change_pwd_btn.clicked.connect(self._change_password)
        btn_pwd_layout = QHBoxLayout()
        btn_pwd_layout.addStretch()
        btn_pwd_layout.addWidget(self.change_pwd_btn)
        self.pwd_card.layout.addLayout(btn_pwd_layout)
        
        # Save Button
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("accent_focus")
        self.save_btn.clicked.connect(self._save)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        
        scroll_layout.addLayout(btn_layout)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    def _set_theme(self, mode: str):
        app = self.property("app_reference")
        if app:
            app.set_theme(mode)

    @staticmethod
    def _prepare_combo(combo: QComboBox) -> None:
        combo.setView(QListView())

    def _apply_combo_theme(self) -> None:
        combo_style = self.theme.combo_box_stylesheet()
        popup_style = self.theme.combo_popup_stylesheet()
        for combo in (self.camera_combo, self.goal_combo, self.session_combo, self.inference_combo):
            combo.setStyleSheet(combo_style)
            combo.view().setStyleSheet(popup_style)

    def _save(self):
        app = self.property("app_reference")
        if app:
            app.update_settings(self.tracker_config())
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Success", "Settings saved successfully.")

    def _change_password(self):
        import os
        from PyQt6.QtWidgets import QMessageBox
        from edge.auth_client import AuthClient, AuthRequestError
        
        app = self.property("app_reference")
        if not app:
            return
            
        username = app.settings.get("auth_username")
        if not username:
            QMessageBox.warning(self, "Error", "You are not logged in with a password account.")
            return
            
        old_pwd = self.old_pwd.text()
        new_pwd = self.new_pwd.text()
        
        if not old_pwd or not new_pwd:
            QMessageBox.warning(self, "Validation Error", "Please fill in both current and new passwords.")
            return
            
        api_url = app.settings.get("cloud_api_url", "https://focusflow-api-smp7iybg5q-as.a.run.app")
        api_key = os.getenv("FOCUSFLOW_API_KEY", "focusflow-demo-key-2025")
        
        try:
            client = AuthClient(api_url, api_key)
            client.change_password(username, old_pwd, new_pwd)
            QMessageBox.information(self, "Success", "Your password has been changed successfully.")
            self.old_pwd.clear()
            self.new_pwd.clear()
        except AuthRequestError as exc:
            QMessageBox.warning(self, "Change Password Failed", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {exc}")

    def tracker_config(self) -> dict:
        return {
            "daily_focus_goal_minutes": int(self.goal_combo.currentText().split()[0]),
            "session_minutes": int(self.session_combo.currentText().split()[0]),
            "sound_session_complete": self.chk_complete.isChecked(),
            "sound_distraction_alert": self.chk_distract.isChecked(),
            "auto_hide_camera": self.chk_autohide.isChecked(),
            "show_landmarks": self.chk_landmarks.isChecked(),
            "camera_index": self.camera_combo.currentIndex(),
            "inference_mode": str(self.inference_combo.currentData() or "local"),
        }

    def apply_settings(self, settings: dict) -> None:
        if settings.get("theme_mode") == "Light":
            self.rb_light.setChecked(True)
        else:
            self.rb_dark.setChecked(True)
            
        goal = settings.get("daily_focus_goal_minutes", 120)
        self.goal_combo.setCurrentText(f"{goal} Mins")
        
        session_def = settings.get("session_minutes", 25)
        self.session_combo.setCurrentText(f"{session_def} Mins")
        inference_mode = str(settings.get("inference_mode") or "local").lower()
        mode_index = self.inference_combo.findData(inference_mode)
        self.inference_combo.setCurrentIndex(max(0, mode_index))
        
        self.chk_complete.setChecked(settings.get("sound_session_complete", True))
        self.chk_distract.setChecked(settings.get("sound_distraction_alert", False))
        self.chk_autohide.setChecked(settings.get("auto_hide_camera", False))

        self.chk_landmarks.setChecked(settings.get("show_landmarks", True))
        camera_idx = settings.get("camera_index", 0)
        self.camera_combo.setCurrentIndex(max(0, min(self.camera_combo.count() - 1, camera_idx)))

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme(self.theme)
        self._apply_combo_theme()
