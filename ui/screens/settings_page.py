from __future__ import annotations
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QButtonGroup, QScrollArea, QWidget
from PyQt6.QtCore import Qt

from ui.screens.base import ThemedPage, PageTitle, Card
from ui.theme import ThemeManager, font

class SettingsPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        self.header = PageTitle("Settings", "Configure tracker sensitivities and keyword heuristics.")
        layout.addWidget(self.header)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0,0,0,0)
        scroll_layout.setSpacing(24)
        
        # App & Account
        self.acc_card = Card()
        scroll_layout.addWidget(self.acc_card)
        t1 = QLabel("Appearance & Account")
        t1.setFont(font(16, bold=True))
        self.acc_card.layout.addWidget(t1)
        
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
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
        
        email_layout = QHBoxLayout()
        email_layout.addWidget(QLabel("Mentor Email:"))
        self.email_input = QLineEdit()
        email_layout.addWidget(self.email_input)
        self.acc_card.layout.addLayout(email_layout)
        
        # Keywords
        self.kw_card = Card()
        scroll_layout.addWidget(self.kw_card)
        t2 = QLabel("OS Tracker Keywords")
        t2.setFont(font(16, bold=True))
        self.kw_card.layout.addWidget(t2)
        
        # New Settings Card for AI Vision Config
        self.ai_card = Card()
        scroll_layout.addWidget(self.ai_card)
        t3 = QLabel("AI Vision Configuration")
        t3.setFont(font(16, bold=True))
        self.ai_card.layout.addWidget(t3)
        
        from PyQt6.QtWidgets import QDoubleSpinBox, QPushButton
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Camera Distance Scale (Face Width %):"))
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(0.05, 0.4)
        self.scale_spinbox.setSingleStep(0.01)
        self.scale_spinbox.setDecimals(3)
        scale_layout.addWidget(self.scale_spinbox)
        self.ai_card.layout.addLayout(scale_layout)
        
        self.prod_input = QLineEdit()
        self.prod_input.setPlaceholderText("vscode, github, pdf, docx, figma")
        self.kw_card.layout.addWidget(QLabel("Productive:"))
        self.kw_card.layout.addWidget(self.prod_input)
        
        self.dist_input = QLineEdit()
        self.dist_input.setPlaceholderText("facebook, netflix, lol, tiktok")
        self.kw_card.layout.addWidget(QLabel("Distracting:"))
        self.kw_card.layout.addWidget(self.dist_input)
        
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

    def _save(self):
        app = self.property("app_reference")
        if app:
            app.update_settings(self.tracker_config())

    def tracker_config(self) -> dict:
        return {
            "mentor_email": self.email_input.text(),
            "productive_keywords": self.prod_input.text(),
            "distracting_keywords": self.dist_input.text(),
            "camera_distance_scale": self.scale_spinbox.value(),
        }

    def apply_settings(self, settings: dict) -> None:
        self.email_input.setText(settings.get("mentor_email", ""))
        self.prod_input.setText(settings.get("productive_keywords", "vscode, github, docx, figma"))
        self.dist_input.setText(settings.get("distracting_keywords", "facebook, netflix, tiktok, youtube"))
        self.scale_spinbox.setValue(settings.get("camera_distance_scale", 0.18))
        if settings.get("theme_mode") == "Light":
            self.rb_light.setChecked(True)
        else:
            self.rb_dark.setChecked(True)

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme(self.theme)
