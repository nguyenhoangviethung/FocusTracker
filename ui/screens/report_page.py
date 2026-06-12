from __future__ import annotations
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QScrollArea, QWidget, QPushButton
from PyQt6.QtCore import Qt

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
        
        body_layout = QHBoxLayout()
        body_layout.setSpacing(18)
        layout.addLayout(body_layout)
        
        self.details_card = Card()
        body_layout.addWidget(self.details_card, stretch=2)
        
        self.status_label = QLabel("No session data available.")
        self.status_label.setFont(font(14, bold=True))
        self.report_label = QLabel("Report status: pending")
        
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(260)
        
        self.details_card.layout.addWidget(self.status_label)
        self.details_card.layout.addWidget(self.report_label)
        self.details_card.layout.addWidget(self.summary)
        
        self.history_card = Card()
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
