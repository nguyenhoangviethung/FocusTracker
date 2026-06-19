from __future__ import annotations
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QTextEdit,
    QScrollArea,
    QWidget,
    QPushButton,
    QListView,
    QSizePolicy,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from ui.screens.base import ThemedPage, PageTitle, Card
from ui.components.focus_chart import FocusTrendChart
from ui.theme import ThemeManager, font
from utils.session_storage import delete_session_record, is_meaningful_session_record, load_session_history

class ReportPage(ThemedPage):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__(theme)
        self._history_records: list[dict] = []
        self._active_session_timestamp: str = ""
        self._selected_history_timestamps: set[str] = set()
        self._history_item_checkboxes: dict[str, QCheckBox] = {}
        
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
        body_layout.setStretch(0, 3)
        body_layout.setStretch(1, 2)

        self.left_column = QWidget()
        self.left_column_layout = QVBoxLayout(self.left_column)
        self.left_column_layout.setContentsMargins(0, 0, 0, 0)
        self.left_column_layout.setSpacing(18)
        body_layout.addWidget(self.left_column, stretch=2)

        self.timeline_card = Card()
        self.timeline_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.timeline_label = QLabel("Focus Timeline")
        self.timeline_label.setFont(font(14, bold=True))
        self.focus_chart = FocusTrendChart(max_points=120, palette=self.theme.palette())
        self.focus_chart.setMinimumHeight(90)
        self.focus_chart.setMaximumHeight(110)
        self.timeline_summary = QTextEdit()
        self.timeline_summary.setReadOnly(True)
        self.timeline_summary.setMaximumHeight(74)
        self.timeline_summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.timeline_card.layout.addWidget(self.timeline_label)
        self.timeline_card.layout.addWidget(self.focus_chart)
        self.timeline_card.layout.addWidget(self.timeline_summary)
        self.left_column_layout.addWidget(self.timeline_card)
        
        self.details_card = Card()
        self.details_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.details_card.setMinimumHeight(260)
        
        self.status_label = QLabel("No session data available.")
        self.status_label.setFont(font(14, bold=True))
        self.report_label = QLabel("Report status: pending")
        
        self.details_card.layout.addWidget(self.status_label)
        self.details_card.layout.addWidget(self.report_label)
        self.details_card.layout.addStretch()
        self.left_column_layout.addWidget(self.details_card, stretch=1)
        
        self.history_card = Card()
        self.history_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.history_card.setMinimumWidth(340)
        body_layout.addWidget(self.history_card, stretch=1)
        
        h_title = QLabel("Recent History")
        h_title.setFont(font(14, bold=True))
        self.history_card.layout.addWidget(h_title)

        self._build_history_filters()
        
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
        self.history_card.layout.addWidget(self.history_scroll, 1)
        
        self._set_summary_text(
            "No new session data.\n\n"
            "When the session ends, FocusFlow saves history.json and marks the report as completed."
        )
        self._refresh_history_source(load_session_history())

    def _reset_report_details(self) -> None:
        self._active_session_timestamp = ""
        self.status_label.setText("No session data available.")
        self.report_label.setText("Report status: pending")
        self.focus_val.setText("0.0%")
        self.dur_val.setText("0 mins")
        self.dist_val.setText("0 times")
        self._set_summary_text(
            "No new session data.\n\n"
            "When the session ends, FocusFlow saves history.json and marks the report as completed."
        )
        self.focus_chart.clear()

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
        self.timeline_summary.setPlainText(text)

    def _build_history_filters(self) -> None:
        self.history_filters_label = QLabel("Filters")
        self.history_filters_label.setFont(font(13, bold=True))
        self.history_card.layout.addWidget(self.history_filters_label)

        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Search timestamp, status, session id")
        self.history_search.textChanged.connect(lambda *_: self._render_history())

        self.history_status_filter = self._make_filter_combo(
            ["All statuses", "completed", "pending"]
        )
        self.history_status_filter.currentTextChanged.connect(lambda *_: self._render_history())

        self.history_focus_filter = self._make_filter_combo(
            ["All focus", ">= 50%", ">= 70%", ">= 80%"]
        )
        self.history_focus_filter.currentTextChanged.connect(lambda *_: self._render_history())

        self.history_duration_filter = self._make_filter_combo(
            ["All durations", ">= 5 mins", ">= 15 mins", ">= 30 mins"]
        )
        self.history_duration_filter.currentTextChanged.connect(lambda *_: self._render_history())

        self.history_reset_btn = QPushButton("Reset Filters")
        self.history_reset_btn.clicked.connect(self._reset_history_filters)
        self.history_select_all = QCheckBox("Select All")
        self.history_select_all.stateChanged.connect(self._toggle_select_all_visible_history)
        self.history_clear_selection_btn = QPushButton("Clear Selection")
        self.history_clear_selection_btn.clicked.connect(self._clear_history_selection)
        self.history_delete_selected_btn = QPushButton("Delete Selected")
        self.history_delete_selected_btn.setObjectName("accent_warn")
        self.history_delete_selected_btn.clicked.connect(self._delete_selected_history)

        self.history_filter_row_1 = QHBoxLayout()
        self.history_filter_row_1.addWidget(self.history_status_filter)
        self.history_filter_row_1.addStretch()

        self.history_filter_row_2 = QHBoxLayout()
        self.history_filter_row_2.addWidget(self.history_focus_filter)
        self.history_filter_row_2.addWidget(self.history_duration_filter)

        self.history_card.layout.addWidget(self.history_search)
        self.history_card.layout.addLayout(self.history_filter_row_1)
        self.history_card.layout.addLayout(self.history_filter_row_2)
        self.history_action_row = QHBoxLayout()
        self.history_action_row.addWidget(self.history_select_all)
        self.history_action_row.addWidget(self.history_clear_selection_btn)
        self.history_action_row.addWidget(self.history_delete_selected_btn)
        self.history_card.layout.addLayout(self.history_action_row)
        self.history_card.layout.addWidget(self.history_reset_btn)

    def _make_filter_combo(self, items: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setView(QListView())
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return combo

    def _selected_focus_threshold(self) -> int:
        text = self.history_focus_filter.currentText()
        if "80" in text:
            return 80
        if "70" in text:
            return 70
        if "50" in text:
            return 50
        return 0

    def _selected_duration_threshold(self) -> int:
        text = self.history_duration_filter.currentText()
        if "30" in text:
            return 30
        if "15" in text:
            return 15
        if "5" in text:
            return 5
        return 0

    @staticmethod
    def _record_status(record: dict) -> str:
        status = str(record.get("report_status") or "").strip().lower()
        if status:
            return "pending" if status == "processing" else status
        return "completed" if bool(record.get("completed", False)) else "pending"

    def _reset_history_filters(self) -> None:
        self.history_search.blockSignals(True)
        self.history_status_filter.blockSignals(True)
        self.history_focus_filter.blockSignals(True)
        self.history_duration_filter.blockSignals(True)
        try:
            self.history_search.clear()
            self.history_status_filter.setCurrentIndex(0)
            self.history_focus_filter.setCurrentIndex(0)
            self.history_duration_filter.setCurrentIndex(0)
        finally:
            self.history_search.blockSignals(False)
            self.history_status_filter.blockSignals(False)
            self.history_focus_filter.blockSignals(False)
            self.history_duration_filter.blockSignals(False)
        self._render_history()

    def _clear_history_selection(self) -> None:
        self._selected_history_timestamps.clear()
        for checkbox in self._history_item_checkboxes.values():
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
        self.history_select_all.blockSignals(True)
        self.history_select_all.setChecked(False)
        self.history_select_all.blockSignals(False)

    def _toggle_select_all_visible_history(self, state: int) -> None:
        if not self.history_select_all.isChecked():
            self._clear_history_selection()
            return
        visible = [rec for rec in self._history_records if self._history_matches_filters(rec)]
        visible_timestamps = {str(rec.get("timestamp") or "").strip() for rec in visible if str(rec.get("timestamp") or "").strip()}
        self._selected_history_timestamps.update(visible_timestamps)
        for timestamp, checkbox in self._history_item_checkboxes.items():
            if timestamp in visible_timestamps:
                checkbox.blockSignals(True)
                checkbox.setChecked(True)
                checkbox.blockSignals(False)
        self._sync_select_all_checkbox()

    def _toggle_history_selection(self, timestamp: str, state: int) -> None:
        if not timestamp:
            return
        if state == Qt.CheckState.Checked.value:
            self._selected_history_timestamps.add(timestamp)
        else:
            self._selected_history_timestamps.discard(timestamp)
        self._sync_select_all_checkbox()

    def _sync_select_all_checkbox(self) -> None:
        visible = [rec for rec in self._history_records if self._history_matches_filters(rec)]
        visible_timestamps = {
            str(rec.get("timestamp") or "").strip()
            for rec in visible
            if str(rec.get("timestamp") or "").strip()
        }
        all_selected = bool(visible_timestamps) and visible_timestamps.issubset(self._selected_history_timestamps)
        self.history_select_all.blockSignals(True)
        self.history_select_all.setChecked(all_selected)
        self.history_select_all.blockSignals(False)

    def _delete_selected_history(self) -> None:
        selected = [rec for rec in self._history_records if str(rec.get("timestamp") or "").strip() in self._selected_history_timestamps]
        if not selected:
            QMessageBox.information(self, "Delete Sessions", "No sessions selected.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Sessions",
            f"Delete {len(selected)} selected session(s) from history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed_timestamps: set[str] = set()
        for rec in selected:
            timestamp = str(rec.get("timestamp") or "").strip()
            if not timestamp:
                continue
            if delete_session_record(timestamp):
                removed_timestamps.add(timestamp)
        if not removed_timestamps:
            QMessageBox.warning(self, "Delete Sessions", "Could not delete the selected session(s).")
            return
        self._selected_history_timestamps.difference_update(removed_timestamps)
        active_timestamp = self._active_session_timestamp
        self._clear_history_selection()
        self._refresh_history_source(load_session_history())
        if active_timestamp in removed_timestamps:
            self._reset_report_details()

    def _history_matches_filters(self, record: dict) -> bool:
        query = self.history_search.text().strip().lower()
        if query:
            haystack = " ".join(
                [
                    str(record.get("timestamp") or ""),
                    str(record.get("status") or ""),
                    str(record.get("report_status") or ""),
                    str(record.get("inference_mode") or ""),
                    str(record.get("cloud_session_id") or ""),
                    str(record.get("session_id") or ""),
                    str(record.get("average_focus") or ""),
                    str(record.get("duration_seconds") or ""),
                ]
            ).lower()
            if query not in haystack:
                return False

        status_filter = self.history_status_filter.currentText().strip().lower()
        record_status = self._record_status(record)
        if status_filter != "all statuses" and record_status != status_filter:
            return False

        focus_threshold = self._selected_focus_threshold()
        if focus_threshold > 0 and float(record.get("average_focus", 0.0)) * 100.0 < focus_threshold:
            return False

        duration_threshold = self._selected_duration_threshold()
        if duration_threshold > 0 and int(record.get("duration_seconds", 0)) // 60 < duration_threshold:
            return False

        return True

    def _render_timeline(self, minute_scores: list[float]) -> None:
        self.focus_chart.clear()
        for score in minute_scores:
            self.focus_chart.add_score(float(score))

    def _refresh_history_source(self, records: list[dict]) -> None:
        self._history_records = [rec for rec in records if is_meaningful_session_record(rec)]
        self._render_history()

    def _delete_history_record(self, record: dict) -> None:
        timestamp = str(record.get("timestamp") or "").strip()
        if not timestamp:
            return
        answer = QMessageBox.question(
            self,
            "Delete Session",
            "Delete this session from history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not delete_session_record(timestamp):
            QMessageBox.warning(self, "Delete Session", "Could not delete this session.")
            return
        self._selected_history_timestamps.discard(timestamp)
        self._history_item_checkboxes.pop(timestamp, None)
        self._history_records = [rec for rec in self._history_records if str(rec.get("timestamp")) != timestamp]
        if self._active_session_timestamp == timestamp:
            self._reset_report_details()
        self._render_history()

    def show_session(self, record: dict, processing: bool = False) -> None:
        self._active_session_timestamp = str(record.get("timestamp") or "").strip()
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
        
        self.status_label.setText(
            f"{'Finalizing report...' if processing else 'Report is ready'} | Focused for {foc // 60} mins"
        )
        if report_completed_at:
            self.report_label.setText(f"Report status: {report_status} at {report_completed_at[:19].replace('T', ' ')}")
        else:
            self.report_label.setText(f"Report status: {report_status}")

        tl = "\n".join(f"Min {i + 1:02d}: {s * 100:.1f}%" for i, s in enumerate(m_scores)) or "Not enough per-minute data."
        self._set_summary_text(f"Timeline:\n{tl}")
        self._render_timeline(m_scores)
        self._render_history()

    def _render_history(self) -> None:
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        history = [rec for rec in self._history_records if self._history_matches_filters(rec)]
        if not history:
            self._history_item_checkboxes = {}
            self.history_select_all.blockSignals(True)
            self.history_select_all.setChecked(False)
            self.history_select_all.blockSignals(False)
            self.history_layout.addWidget(QLabel("No sessions found for the current filters."))
            self.history_layout.addStretch()
            return

        self._history_item_checkboxes = {}
        visible_timestamps = {
            str(rec.get("timestamp") or "").strip()
            for rec in history
            if str(rec.get("timestamp") or "").strip()
        }
        if hasattr(self, "history_select_all"):
            self.history_select_all.blockSignals(True)
            self.history_select_all.setChecked(
                bool(visible_timestamps) and visible_timestamps.issubset(self._selected_history_timestamps)
            )
            self.history_select_all.blockSignals(False)
            
        for rec in history:
            c = QWidget()
            c.setObjectName("bg_app")
            cl = QVBoxLayout(c)
            focus = float(rec.get("average_focus", 0.0)) * 100
            dmins = int(rec.get("duration_seconds", 0)) // 60
            ts = str(rec.get("timestamp", ""))[:16].replace("T", " ")
            timestamp = str(rec.get("timestamp") or "").strip()
            status = str(rec.get("status") or rec.get("report_status") or "completed").strip().lower()
            mode = str(rec.get("inference_mode") or "cloud").strip().lower()

            select_row = QHBoxLayout()
            select_box = QCheckBox("Select")
            select_box.setChecked(timestamp in self._selected_history_timestamps)
            select_box.stateChanged.connect(
                lambda state, ts=timestamp: self._toggle_history_selection(ts, state)
            )
            self._history_item_checkboxes[timestamp] = select_box
            select_row.addWidget(select_box)
            select_row.addStretch()
            cl.addLayout(select_row)
            
            t = QLabel(f"{focus:.1f}% | {dmins} mins")
            t.setFont(font(13, bold=True))
            cl.addWidget(t)
            
            s = QLabel(ts)
            cl.addWidget(s)
            meta = QLabel(f"{status} | {mode}")
            meta.setStyleSheet(f"color: {self.theme.color('text_secondary')};")
            cl.addWidget(meta)
            
            row = QHBoxLayout()
            open_btn = QPushButton("Open")
            open_btn.clicked.connect(lambda checked, r=rec: self.show_session(r, False))
            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("accent_warn")
            delete_btn.clicked.connect(lambda checked, r=rec: self._delete_history_record(r))
            row.addWidget(open_btn)
            row.addWidget(delete_btn)
            cl.addLayout(row)
            self.history_layout.addWidget(c)
            
        self.history_layout.addStretch()

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme(self.theme)
        self.focus_chart.apply_theme(self.theme.palette())
        self.report_label.setStyleSheet(f"color: {self.theme.color('text_secondary')};")
        self.timeline_label.setStyleSheet(f"color: {self.theme.color('text_secondary')};")
        self.history_filters_label.setStyleSheet(f"color: {self.theme.color('text_secondary')};")
        self.history_search.setStyleSheet(self.theme.combo_box_stylesheet())
        self.history_search.setPlaceholderText("Search timestamp, status, session id")
        for combo in (
            self.history_status_filter,
            self.history_focus_filter,
            self.history_duration_filter,
        ):
            combo.setStyleSheet(self.theme.combo_box_stylesheet())
            combo.view().setStyleSheet(self.theme.combo_popup_stylesheet())

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
            status = str(rec.get("status") or summary.get("status") or rec.get("report_status") or "completed")
            if status == "processing":
                status = "pending"
            mapped = {
                "session_id": rec.get("session_id") or "",
                "timestamp": rec.get("started_at") or rec.get("timestamp") or "",
                "status": status,
                "average_focus": summary.get("average_focus") or rec.get("average_focus") or 0.0,
                "duration_seconds": summary.get("duration_seconds") or rec.get("duration_seconds") or 0,
                "focused_seconds": summary.get("focused_seconds") or rec.get("focused_seconds") or 0,
                "distraction_count": summary.get("distraction_count") or rec.get("distraction_count") or 0,
                "completed": summary.get("completed") if "completed" in summary else rec.get("completed", False),
                "minute_focus_scores": summary.get("minute_focus_scores") or rec.get("minute_focus_scores") or [],
                "report_status": rec.get("report_status") or "completed",
                "report_completed_at": rec.get("report_completed_at") or "",
                "inference_mode": rec.get("inference_mode") or summary.get("inference_mode") or "cloud",
                "cloud_session_id": rec.get("cloud_session_id") or "",
            }
            if is_meaningful_session_record(mapped):
                local_history.append(mapped)

        from utils.session_storage import save_session_history
        save_session_history(local_history)
        self._refresh_history_source(local_history)

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
