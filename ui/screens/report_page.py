from __future__ import annotations
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QScrollArea,
    QWidget,
    QPushButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui.screens.base import ThemedPage, PageTitle, Card
from ui.theme import ThemeManager, font
from utils.session_storage import load_session_history

class ReportPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)
        
        self.header = PageTitle("Session Report", "Session summary and local history.")
        layout.addWidget(self.header)
        
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(18)
        layout.addLayout(metrics_layout)
        
        self.focus_val = self._metric_card(metrics_layout, "Focus Score", "0.0%")
        self.dur_val = self._metric_card(metrics_layout, "Duration", "0 mins")
        self.dist_val = self._metric_card(metrics_layout, "Distractions", "0 times")
        metrics_layout.setStretch(0, 1)
        metrics_layout.setStretch(1, 1)
        metrics_layout.setStretch(2, 1)
        
        body_layout = QHBoxLayout()
        body_layout.setSpacing(18)
        layout.addLayout(body_layout)
        body_layout.setStretch(0, 2)
        body_layout.setStretch(1, 1)
        
        self.details_card = Card()
        self.details_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body_layout.addWidget(self.details_card, stretch=2)
        
        self.status_label = QLabel("No session data available.")
        self.status_label.setFont(font(14, bold=True))
        self.report_label = QLabel("Report status: pending")
        
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(260)
        self.summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.details_card.layout.addWidget(self.status_label)
        self.details_card.layout.addWidget(self.report_label)
        self.details_card.layout.addWidget(self.summary)
        
        self.history_card = Card()
        self.history_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body_layout.addWidget(self.history_card, stretch=1)
        
        h_title = QLabel("Recent History")
        h_title.setFont(font(14, bold=True))
        self.history_card.layout.addWidget(h_title)
        
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.history_scroll.setStyleSheet("background: transparent;")
        self.history_container = QWidget()
        self.history_container.setStyleSheet("background: transparent;")
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0,0,0,0)
        self.history_layout.setSpacing(8)
        self.history_scroll.setWidget(self.history_container)
        self.history_card.layout.addWidget(self.history_scroll)
        
        self._set_summary_text(
            "No new session data.\n\n"
            "When the session ends, FocusFlow saves history.json and marks the report as completed."
        )
        self._render_history()

    def _metric_card(self, parent_layout, title, value) -> QLabel:
        card = Card()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        parent_layout.addWidget(card)
        t = QLabel(title)
        t.setFont(font(13))
        v = QLabel(value)
        v.setFont(font(24, bold=True))
        card.layout.addWidget(t)
        card.layout.addWidget(v)
        return v

    def _set_summary_text(self, text: str):
        self.summary.setPlainText(text)

    def show_session(self, record: dict, processing: bool = False) -> None:
        focus = float(record.get("average_focus", 0.0))
        dur = int(record.get("duration_seconds", 0))
        foc = int(record.get("focused_seconds", 0))
        dist = int(record.get("distraction_count", 0))
        comp = bool(record.get("completed", False))
        m_scores = [float(s) for s in record.get("minute_focus_scores", [])]
        report_status = str(record.get("report_status") or ("completed" if not processing else "processing")).strip()
        report_completed_at = str(record.get("report_completed_at") or "").strip()
        
        self.focus_val.setText(f"{focus * 100:.1f}%")
        self.dur_val.setText(f"{dur // 60} mins")
        self.dist_val.setText(f"{dist} times")
        
        stext = "Finalizing report..." if processing else "Report is ready"
        self.status_label.setText(f"{stext} | {'Completed' if comp else 'Ended early'} | Focused for {foc // 60} mins")
        if report_completed_at:
            self.report_label.setText(f"Report status: {report_status} at {report_completed_at[:19].replace('T', ' ')}")
        else:
            self.report_label.setText(f"Report status: {report_status}")

        tl = "\n".join(f"Min {i + 1:02d}: {s * 100:.1f}%" for i, s in enumerate(m_scores)) or "Not enough per-minute data."
        self._set_summary_text(f"Timeline:\n{tl}")
        self._render_history()

    def _render_history(self) -> None:
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        history = load_session_history()[:8]
        if not history:
            self.history_layout.addWidget(QLabel("No sessions found."))
            self.history_layout.addStretch()
            return
            
        for rec in history:
            c = QWidget()
            c.setObjectName("bg_app")
            cl = QVBoxLayout(c)
            focus = float(rec.get("average_focus", 0.0)) * 100
            dmins = int(rec.get("duration_seconds", 0)) // 60
            ts = str(rec.get("timestamp", ""))[:16].replace("T", " ")
            
            t = QLabel(f"{focus:.1f}% | {dmins} mins")
            t.setFont(font(13, bold=True))
            cl.addWidget(t)
            
            s = QLabel(ts)
            cl.addWidget(s)
            
            b = QPushButton("Open")
            b.clicked.connect(lambda checked, r=rec: self.show_session(r, False))
            cl.addWidget(b)
            self.history_layout.addWidget(c)
            
        self.history_layout.addStretch()

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme(self.theme)
        self.report_label.setStyleSheet(f"color: {self.theme.color('text_secondary')};")

    def refresh(self):
        """Called by app_window.navigate() when switching to this page."""
        import time
        now = time.monotonic()
        # Debounce: skip if last load was less than 5 seconds ago
        if hasattr(self, '_last_history_load') and (now - self._last_history_load) < 5.0:
            return
        self._last_history_load = now
        self._load_history()

    def _load_history(self):
        import os
        
        app = self.property("app_reference")
        if not app: return
        username = app.settings.get("auth_username")
        user_id = app.settings.get("auth_user_id", "")
        if not username: return
        api_url = app.settings.get("cloud_api_url") or "https://focusflow-api-smp7iybg5q-as.a.run.app"
        api_key = os.getenv("FOCUSFLOW_API_KEY", "focusflow-demo-key-2025")

        # Cancel any running worker
        if hasattr(self, '_history_worker') and self._history_worker is not None:
            if self._history_worker.isRunning():
                return  # Don't start another request while one is pending

        self._history_worker = _HistoryWorker(username, user_id, api_url, api_key)
        self._history_worker.history_ready.connect(self._update_history_ui)
        self._history_worker.history_error.connect(self._show_history_error)
        self._history_worker.start()

    def _show_history_error(self, msg: str):
        pass

    def _update_history_ui(self, sessions: list):
        # Format the sessions to match local format
        local_history = []
        for rec in sessions:
            summary = rec.get("summary") or {}
            mapped = {
                "timestamp": rec.get("started_at") or rec.get("timestamp") or "",
                "average_focus": summary.get("average_focus") or rec.get("average_focus") or 0.0,
                "duration_seconds": summary.get("duration_seconds") or rec.get("duration_seconds") or 0,
                "focused_seconds": summary.get("focused_seconds") or rec.get("focused_seconds") or 0,
                "distraction_count": summary.get("distraction_count") or rec.get("distraction_count") or 0,
                "completed": summary.get("completed") if "completed" in summary else rec.get("completed", False),
                "minute_focus_scores": summary.get("minute_focus_scores") or rec.get("minute_focus_scores") or [],
                "report_status": rec.get("report_status") or "completed",
                "report_completed_at": rec.get("report_completed_at") or "",
            }
            local_history.append(mapped)

        from utils.session_storage import save_session_history
        save_session_history(local_history)
        
        self._render_history()

        # If there is at least one session, open/show the most recent one automatically!
        if local_history and self.status_label.text() == "No session data available.":
            self.show_session(local_history[0], False)


class _HistoryWorker(QThread):
    """Background worker that fetches user session history from the cloud API."""
    history_ready = pyqtSignal(list)
    history_error = pyqtSignal(str)

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
            result = client.get_user_sessions(self._username, self._user_id)
            self.history_ready.emit(result)
        except Exception as exc:
            self.history_error.emit(str(exc))

