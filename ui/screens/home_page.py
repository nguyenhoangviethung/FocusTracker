from __future__ import annotations
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QFileDialog
from PyQt6.QtCore import Qt

from ui.screens.base import ThemedPage, PageTitle, Card
from ui.theme import ThemeManager, font

class HomePage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        self.header = PageTitle("Ready to Focus?", "Start a new session and let AI manage your distractions.")
        layout.addWidget(self.header)
        
        self.setup_card = Card()
        layout.addWidget(self.setup_card)
        
        title_label = QLabel("Pomodoro Setup")
        title_label.setFont(font(16, bold=True))
        self.setup_card.layout.addWidget(title_label)
        
        # Duration
        dur_layout = QHBoxLayout()
        dur_label = QLabel("Duration:")
        dur_label.setFont(font(14))
        self.dur_combo = QComboBox()
        self.dur_combo.addItems(["15 Mins", "25 Mins", "45 Mins", "60 Mins", "90 Mins"])
        self.dur_combo.setCurrentText("25 Mins")
        self.dur_combo.setFixedWidth(150)
        dur_layout.addWidget(dur_label)
        dur_layout.addStretch()
        dur_layout.addWidget(self.dur_combo)
        self.setup_card.layout.addLayout(dur_layout)
        
        # Hardcore Mode
        hc_layout = QHBoxLayout()
        hc_label = QLabel("Hardcore Mode (Auto-kill distractions):")
        hc_label.setFont(font(14))
        self.hc_check = QCheckBox()
        hc_layout.addWidget(hc_label)
        hc_layout.addStretch()
        hc_layout.addWidget(self.hc_check)
        self.setup_card.layout.addLayout(hc_layout)
        
        # Mentor Report
        mr_layout = QHBoxLayout()
        mr_label = QLabel("Send Mentor Report:")
        mr_label.setFont(font(14))
        self.mr_check = QCheckBox()
        mr_layout.addWidget(mr_label)
        mr_layout.addStretch()
        mr_layout.addWidget(self.mr_check)
        self.setup_card.layout.addLayout(mr_layout)
        
        # Demo Video
        vid_layout = QHBoxLayout()
        vid_label = QLabel("Demo Mode Video:")
        vid_label.setFont(font(14))
        self.vid_btn = QPushButton("Select .mp4 File")
        self.vid_btn.clicked.connect(self._select_video)
        self.vid_path = ""
        vid_layout.addWidget(vid_label)
        vid_layout.addStretch()
        vid_layout.addWidget(self.vid_btn)
        self.setup_card.layout.addLayout(vid_layout)
        
        # Start button
        self.start_btn = QPushButton("START SESSION")
        self.start_btn.setObjectName("accent_focus")
        self.start_btn.setMinimumHeight(48)
        self.start_btn.setFont(font(16, bold=True))
        self.start_btn.clicked.connect(self._on_start)
        self.setup_card.layout.addSpacing(16)
        self.setup_card.layout.addWidget(self.start_btn)
        
        layout.addStretch()

    def _select_video(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mp4 *.avi)")
        if file:
            self.vid_path = file
            self.vid_btn.setText(file.split('/')[-1])

    def _on_start(self):
        val = self.dur_combo.currentText().split()[0]
        config = {
            "pomodoro_minutes": int(val),
            "hardcore_enabled": self.hc_check.isChecked(),
            "mentor_report_enabled": self.mr_check.isChecked(),
            "demo_video_path": self.vid_path
        }
        app = self.property("app_reference")
        if app:
            app.start_session(config)
            
    def apply_settings(self, settings: dict) -> None:
        self.hc_check.setChecked(bool(settings.get("hardcore_enabled", False)))
        self.mr_check.setChecked(bool(settings.get("mentor_report_enabled", False)))
        
    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme(self.theme)
