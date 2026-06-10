from __future__ import annotations
from typing import Any, Callable
import threading
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from PyQt6.QtCore import pyqtSignal

from core_ai import generate_focus_coaching, send_report_email
from ui.theme import ThemeManager
from ui.components.navigation import SidebarNavigation
from ui.screens.home_page import HomePage
from ui.screens.settings_page import SettingsPage
from ui.screens.report_page import ReportPage
from ui.screens.active_session_page import ActiveSessionPage
from ui.screens.ai_vision_page import AIVisionPage
from utils.settings_store import load_settings, save_settings
from utils.session_storage import save_session_statistics, update_session_record

class FocusFlowApp(QMainWindow):
    report_completed = pyqtSignal(dict)

    def __init__(self, fusion_logic: Callable | None = None) -> None:
        super().__init__()
        self.setWindowTitle("FocusFlow AI")
        self.resize(1200, 760)
        self.setMinimumSize(980, 640)

        self.settings = load_settings()
        self.theme = ThemeManager(str(self.settings.get("theme_mode", "Dark")))
        self.theme.register(self.apply_theme)
        self.fusion_logic = fusion_logic
        self._current_route = "home"

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = SidebarNavigation(self.theme, self.theme.toggle)
        self.sidebar.route_selected.connect(self.navigate)
        layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.pages = {
            "home": HomePage(self.theme),
            "report": ReportPage(self.theme),
            "settings": SettingsPage(self.theme),
            "vision": AIVisionPage(self.theme),
            "active_session": ActiveSessionPage(self.theme),
        }

        for page in self.pages.values():
            self.stack.addWidget(page)
            page.setProperty("app_reference", self)

        self.report_completed.connect(self._show_completed_report)
        self._apply_settings_to_pages()
        self.apply_theme()
        self.navigate("home")

    def navigate(self, route: str) -> None:
        if self._current_route == "vision" and route != "vision":
            if hasattr(self.pages["vision"], "shutdown"):
                self.pages["vision"].shutdown()

        self._current_route = route
        self.stack.setCurrentWidget(self.pages[route])
        self.sidebar.set_active(route)

    def start_session(self, config: dict) -> None:
        settings_config = getattr(self.pages["settings"], "tracker_config", None)
        if callable(settings_config):
            merged = {**settings_config(), **config}
            if not str(config.get("demo_video_path", "")).strip():
                merged["demo_video_path"] = settings_config().get("demo_video_path", "")
            config = merged

        self.settings = save_settings({**self.settings, **config, "theme_mode": self.theme.mode})
        self._apply_settings_to_pages()
        
        session_page = self.pages["active_session"]
        if hasattr(session_page, "begin"):
            session_page.begin(config)
        self.navigate("active_session")

    def update_settings(self, payload: dict) -> None:
        self.settings = save_settings({**self.settings, **payload, "theme_mode": self.theme.mode})
        self._apply_settings_to_pages()

    def finish_session(self, summary: dict) -> None:
        record = save_session_statistics(
            minute_scores=[float(s) for s in summary.get("minute_scores", [])],
            average_score=float(summary.get("average_score", 0.0)),
            completed=bool(summary.get("completed", False)),
            total_seconds=int(summary.get("total_seconds", 0)),
            focused_seconds=int(summary.get("focused_seconds", 0)),
            distraction_count=int(summary.get("distraction_count", 0)),
            focus_streak_seconds=float(summary.get("focus_streak_seconds", 0.0)),
        )
        record.update({
            "mentor_email": str(summary.get("mentor_email") or ""),
            "mentor_report_enabled": bool(summary.get("mentor_report_enabled", False)),
            "hardcore_enabled": bool(summary.get("hardcore_enabled", False)),
        })
        
        report_page = self.pages["report"]
        if hasattr(report_page, "show_session"):
            report_page.show_session(record, processing=True)
        self.navigate("report")

        threading.Thread(target=self._complete_session_report, args=(record,), daemon=True).start()

    def _complete_session_report(self, record: dict) -> None:
        feedback = generate_focus_coaching(record)
        enriched = {**record, "ai_feedback": feedback}
        
        email_status = {"sent": False, "status": "skipped", "message": "Mentor report is disabled."}
        if record.get("mentor_report_enabled"):
            email_status = send_report_email(record.get("mentor_email", ""), enriched)
            
        updated = update_session_record(record.get("timestamp"), {
            "ai_feedback": feedback,
            "email_status": email_status,
        }) or {**enriched, "email_status": email_status}
        
        self.report_completed.emit(updated)

    def _show_completed_report(self, record: dict) -> None:
        report_page = self.pages["report"]
        if hasattr(report_page, "show_session"):
            report_page.show_session(record, processing=False)

    def _apply_settings_to_pages(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "apply_settings"):
                page.apply_settings(self.settings)

    def apply_theme(self) -> None:
        self.setStyleSheet(self.theme.get_stylesheet())
        self.sidebar.apply_theme()
        for page in self.pages.values():
            if hasattr(page, "apply_theme"):
                page.apply_theme()

    def closeEvent(self, event) -> None:
        session_page = self.pages["active_session"]
        if hasattr(session_page, "stop_timer"): session_page.stop_timer()
        if hasattr(session_page, "stop_tracker"): session_page.stop_tracker()
        if hasattr(self.pages["vision"], "shutdown"): self.pages["vision"].shutdown()
        event.accept()
