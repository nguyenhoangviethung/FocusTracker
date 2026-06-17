from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QFileDialog,
    QSizePolicy,
    QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui.screens.base import ThemedPage, PageTitle, Card
from ui.theme import ThemeManager, font

class HomePage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # Header Layout mimicking Dashboard
        header_layout = QHBoxLayout()
        self.header = PageTitle("Hello User", "Start a new session and track focus locally or through the cloud.")
        
        premium_badge = QLabel("★ PREMIUM")
        premium_badge.setStyleSheet("background-color: #333; color: #FFD700; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;")
        
        header_layout.addWidget(self.header)
        header_layout.addWidget(premium_badge, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Summary Gradient Cards mimicking Dashboard
        self.summary_card = Card()
        self.summary_card.setStyleSheet("""
            QFrame#bg_card {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2E8CFF, stop:1 #1E5EEB);
                border-radius: 16px;
            }
            QLabel { color: white; }
        """)
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(24)
        
        self.stat_labels = {}
        for val, lbl in [("-", "Focus Time"), ("-", "Sessions"), ("-", "Avg Score"), ("-", "Day Streak")]:
            col = QVBoxLayout()
            val_lbl = QLabel(val)
            val_lbl.setFont(font(36, bold=True))
            self.stat_labels[lbl] = val_lbl
            desc_lbl = QLabel(lbl)
            desc_lbl.setFont(font(12))
            desc_lbl.setStyleSheet("color: rgba(255,255,255,0.8);")
            col.addWidget(val_lbl)
            col.addWidget(desc_lbl)
            summary_layout.addLayout(col)
            
        self.summary_card.layout.addLayout(summary_layout)
        layout.addWidget(self.summary_card)

        # Setup Area
        setup_layout = QHBoxLayout()
        setup_layout.setSpacing(24)

        self.setup_card = Card()
        title_label = QLabel("Pomodoro Setup")
        title_label.setFont(font(16, bold=True))
        self.setup_card.layout.addWidget(title_label)
        
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

        self.source_label = QLabel("Selected source: local webcam")
        self.mode_label = QLabel("Inference mode: hybrid (cloud + local fallback)")
        self.source_label.setWordWrap(True)
        self.mode_label.setWordWrap(True)
        self.setup_card.layout.addWidget(self.source_label)
        self.setup_card.layout.addWidget(self.mode_label)
        
        self.start_btn = QPushButton("START SESSION")
        self.start_btn.setObjectName("accent_focus")
        self.start_btn.setMinimumHeight(48)
        self.start_btn.setFont(font(16, bold=True))
        self.start_btn.clicked.connect(self._on_start)
        self.setup_card.layout.addSpacing(16)
        self.setup_card.layout.addWidget(self.start_btn)
        
        setup_layout.addWidget(self.setup_card)

        # User Activity
        self.recent_card = Card()
        recent_title = QLabel("Recent Activity")
        recent_title.setFont(font(16, bold=True))
        self.recent_card.layout.addWidget(recent_title)
        
        self.recent_content = QVBoxLayout()
        self.recent_card.layout.addLayout(self.recent_content)
        self.recent_card.layout.addStretch()
        
        setup_layout.addWidget(self.recent_card)
        setup_layout.setStretch(0, 2)
        setup_layout.setStretch(1, 1)

        layout.addLayout(setup_layout)
        layout.addStretch()

    def _select_video(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mp4 *.avi)")
        if file:
            self.vid_path = file
            self.vid_btn.setText(Path(file).name)
            self.source_label.setText(f"Selected source: {Path(file).name}")

    def _on_start(self):
        val = self.dur_combo.currentText().split()[0]
        config = {
            "pomodoro_minutes": int(val),
            "demo_video_path": self.vid_path
        }
        app = self.property("app_reference")
        if app:
            app.start_session(config)
            
    def apply_settings(self, settings: dict) -> None:
        mode = str(settings.get("inference_mode", "hybrid"))
        suffix = " (cloud + local fallback)" if mode == "hybrid" else ""
        self.mode_label.setText(f"Inference mode: {mode}{suffix}")

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme(self.theme)

    def refresh(self):
        """Called by app_window.navigate() when switching to this page."""
        import time
        now = time.monotonic()
        # Debounce: skip if last load was less than 5 seconds ago
        if hasattr(self, '_last_stats_load') and (now - self._last_stats_load) < 5.0:
            return
        self._last_stats_load = now
        self._load_stats()
        
    def _load_stats(self):
        import os
        
        app = self.property("app_reference")
        if not app: return
        username = app.settings.get("auth_username")
        user_id = app.settings.get("auth_user_id", "")
        if not username: return
        api_url = app.settings.get("cloud_api_url") or "https://focusflow-api-smp7iybg5q-as.a.run.app"
        api_key = os.getenv("FOCUSFLOW_API_KEY", "focusflow-demo-key-2025")

        # Cancel any running worker
        if hasattr(self, '_stats_worker') and self._stats_worker is not None:
            if self._stats_worker.isRunning():
                return  # Don't start another request while one is pending

        self._stats_worker = _StatsWorker(username, user_id, api_url, api_key)
        self._stats_worker.stats_ready.connect(self._update_stats_ui)
        self._stats_worker.stats_error.connect(self._show_stats_error)
        self._stats_worker.start()

    def _show_stats_error(self, msg: str):
        """Show placeholder values when stats can't be loaded."""
        for lbl in self.stat_labels.values():
            if lbl.text() == "-":
                pass  # keep placeholder
                
    def _update_stats_ui(self, stats: dict):
        self.stat_labels["Focus Time"].setText(str(stats.get("total_focus_hours", "0h")))
        self.stat_labels["Sessions"].setText(str(stats.get("total_sessions", "0")))
        self.stat_labels["Avg Score"].setText(str(stats.get("average_score", "0%")))
        self.stat_labels["Day Streak"].setText(str(stats.get("current_streak", "0")))
        
        # Clear recent content
        while self.recent_content.count():
            item = self.recent_content.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        recent = stats.get("recent_activity", [])
        if not recent:
            lbl = QLabel("No recent activity.")
            lbl.setStyleSheet("color: #64748B;")
            self.recent_content.addWidget(lbl)
            return
            
        for act in recent:
            r_row = QHBoxLayout()
            r_name = QLabel(act.get("label", ""))
            r_name.setFont(font(12, bold=True))
            r_size = QLabel(act.get("description", ""))
            r_size.setStyleSheet("color: #64748B;")
            r_row.addWidget(r_name)
            r_row.addStretch()
            r_row.addWidget(r_size)
            
            row_widget = QWidget()
            row_widget.setLayout(r_row)
            self.recent_content.addWidget(row_widget)


class _StatsWorker(QThread):
    """Background worker that fetches user stats from the cloud API."""
    stats_ready = pyqtSignal(dict)
    stats_error = pyqtSignal(str)

    def __init__(self, username: str, user_id: str, api_url: str, api_key: str):
        super().__init__()
        self._username = username
        self._user_id = user_id
        self._api_url = api_url
        self._api_key = api_key

    def run(self):
        from edge.auth_client import AuthClient
        try:
            client = AuthClient(self._api_url, self._api_key)
            result = client.get_user_stats(self._username, self._user_id)
            self.stats_ready.emit(result)
        except Exception as exc:
            self.stats_error.emit(str(exc))
