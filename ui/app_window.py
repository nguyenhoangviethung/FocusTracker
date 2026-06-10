from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

import customtkinter as ctk

from core_ai import generate_focus_coaching, send_report_email
from ui.components.navigation import SidebarNavigation
from ui.screens.active_session_page import ActiveSessionPage
from ui.screens.ai_vision_page import AIVisionPage
from ui.screens.home_page import HomePage
from ui.screens.report_page import ReportPage
from ui.screens.settings_page import SettingsPage
from ui.theme import ThemeManager, configure_tk_fonts
from utils.session_storage import save_session_statistics, update_session_record
from utils.settings_store import load_settings, save_settings


class FocusFlowApp(ctk.CTk):
    """CustomTkinter desktop shell with sidebar routing and live tracking pages."""

    def __init__(
        self,
        fusion_logic: Callable[[float, dict[str, Any] | None, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        configure_tk_fonts(self)
        self.title("FocusFlow AI")
        self.geometry("1200x760")
        self.minsize(980, 640)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.settings = load_settings()
        self.theme = ThemeManager(str(self.settings.get("theme_mode", "Dark")))
        self.fusion_logic = fusion_logic
        self._last_session_record: dict[str, Any] | None = None
        self._current_route = "home"
        self.theme.register(self.apply_theme)

        self.grid_columnconfigure(0, minsize=200, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = SidebarNavigation(
            self,
            theme=self.theme,
            on_select=self.navigate,
            on_toggle_theme=self.theme.toggle,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.main_frame = ctk.CTkFrame(self, corner_radius=0, border_width=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.pages: dict[str, ctk.CTkFrame] = {
            "home": HomePage(self.main_frame, self, self.theme),
            "report": ReportPage(self.main_frame, self, self.theme),
            "settings": SettingsPage(self.main_frame, self, self.theme),
            "vision": AIVisionPage(self.main_frame, self, self.theme),
            "active_session": ActiveSessionPage(self.main_frame, self, self.theme),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self._apply_settings_to_pages()
        self.apply_theme()
        self.navigate("home")

    def navigate(self, route: str) -> None:
        page_key = route if route in self.pages else "home"
        if self._current_route == "vision" and page_key != "vision":
            vision_page = self.pages.get("vision")
            shutdown = getattr(vision_page, "shutdown", None)
            if callable(shutdown):
                shutdown()
        self._current_route = page_key
        self.sidebar.set_active(page_key if page_key in {"home", "report", "settings", "vision"} else "home")
        self.pages[page_key].tkraise()

    def start_session(self, config: dict[str, object]) -> None:
        settings_page = self.pages.get("settings")
        settings_config = getattr(settings_page, "tracker_config", None)
        if callable(settings_config):
            settings_values = settings_config()
            merged = {**settings_values, **config}
            if not str(config.get("demo_video_path") or "").strip():
                merged["demo_video_path"] = settings_values.get("demo_video_path", "")
            config = merged
        self.settings = save_settings({**self.settings, **config, "theme_mode": self.theme.mode})
        self._apply_settings_to_pages()
        session_page = self.pages["active_session"]
        if isinstance(session_page, ActiveSessionPage):
            session_page.begin(config)
        self.navigate("active_session")

    def set_theme(self, mode: str) -> None:
        self.theme.set_mode(mode)
        self.settings = save_settings({**self.settings, "theme_mode": self.theme.mode})

    def update_settings(self, payload: dict[str, object]) -> None:
        self.settings = save_settings({**self.settings, **payload, "theme_mode": self.theme.mode})
        self._apply_settings_to_pages()

    def finish_session(self, summary: dict[str, object]) -> None:
        record = save_session_statistics(
            minute_scores=[float(score) for score in summary.get("minute_scores", [])],
            average_score=float(summary.get("average_score", 0.0)),
            completed=bool(summary.get("completed", False)),
            total_seconds=int(summary.get("total_seconds", 0)),
            focused_seconds=int(summary.get("focused_seconds", 0)),
            distraction_count=int(summary.get("distraction_count", 0)),
            focus_streak_seconds=float(summary.get("focus_streak_seconds", 0.0)),
        )
        record.update(
            {
                "mentor_email": str(summary.get("mentor_email") or ""),
                "mentor_report_enabled": bool(summary.get("mentor_report_enabled", False)),
                "hardcore_enabled": bool(summary.get("hardcore_enabled", False)),
            }
        )
        self._last_session_record = record
        report_page = self.pages.get("report")
        show_session = getattr(report_page, "show_session", None)
        if callable(show_session):
            show_session(record, processing=True)
        self.navigate("report")

        worker = threading.Thread(
            target=self._complete_session_report,
            args=(record,),
            name="focusflow-ai-report",
            daemon=True,
        )
        worker.start()

    def apply_theme(self) -> None:
        self.configure(fg_color=self.theme.color("bg_app"))
        self.main_frame.configure(fg_color=self.theme.color("bg_app"))
        self.sidebar.apply_theme()
        for page in self.pages.values():
            apply_theme = getattr(page, "apply_theme", None)
            if callable(apply_theme):
                apply_theme()

    def _on_close(self) -> None:
        session_page = self.pages.get("active_session")
        stop_tracker = getattr(session_page, "stop_tracker", None)
        stop_timer = getattr(session_page, "stop_timer", None)
        if callable(stop_timer):
            stop_timer()
        if callable(stop_tracker):
            stop_tracker()
        vision_page = self.pages.get("vision")
        shutdown = getattr(vision_page, "shutdown", None)
        if callable(shutdown):
            shutdown()
        self.destroy()

    def _apply_settings_to_pages(self) -> None:
        for page in self.pages.values():
            apply_settings = getattr(page, "apply_settings", None)
            if callable(apply_settings):
                apply_settings(self.settings)

    def _complete_session_report(self, record: dict[str, Any]) -> None:
        feedback = generate_focus_coaching(record)
        enriched = {**record, "ai_feedback": feedback}

        email_status = {"sent": False, "status": "skipped", "message": "Không bật gửi mentor report."}
        if bool(record.get("mentor_report_enabled")):
            email_status = send_report_email(str(record.get("mentor_email") or ""), enriched)

        updated = update_session_record(
            str(record.get("timestamp")),
            {
                "ai_feedback": feedback,
                "email_status": email_status,
                "mentor_email": record.get("mentor_email", ""),
                "hardcore_enabled": record.get("hardcore_enabled", False),
            },
        ) or {**enriched, "email_status": email_status}

        self.after(0, self._show_completed_report, updated)

    def _show_completed_report(self, record: dict[str, Any]) -> None:
        self._last_session_record = record
        report_page = self.pages.get("report")
        show_session = getattr(report_page, "show_session", None)
        if callable(show_session):
            show_session(record, processing=False)
