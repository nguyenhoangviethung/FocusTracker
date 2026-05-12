from __future__ import annotations

import threading

import customtkinter as ctk

from core_ai.ai_coach import AICoach
from ui.screens.dashboard import DashboardScreen
from ui.screens.report_screen import ReportScreen
from ui.screens.session_screen import SessionScreen


class FocusFlowApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FocusFlow AI")
        self.geometry("1320x820")
        self.minsize(1100, 720)
        self.configure(fg_color="#0b1320")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.ai_coach = AICoach(model="gpt-4o-mini")

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.dashboard_screen = DashboardScreen(container, controller=self)
        self.session_screen = SessionScreen(container, controller=self)
        self.report_screen = ReportScreen(container, controller=self)

        for screen in (self.dashboard_screen, self.session_screen, self.report_screen):
            screen.grid(row=0, column=0, sticky="nsew")

        self.show_dashboard()

    def show_dashboard(self) -> None:
        self.session_screen.reset_ui()
        self.dashboard_screen.tkraise()

    def start_new_session(self) -> None:
        self.show_dashboard()

    def start_focus_session(self, minutes: int) -> None:
        self.session_screen.prepare_session(minutes)
        self.session_screen.tkraise()
        self.session_screen.start_session()

    def on_session_finished(self, minute_scores: list[float], average_score: float, completed: bool) -> None:
        _ = completed
        self.report_screen.show_loading(minute_scores, average_score)
        self.report_screen.tkraise()

        worker = threading.Thread(
            target=self._generate_report_in_background,
            args=(minute_scores, average_score),
            daemon=True,
        )
        worker.start()

    def _generate_report_in_background(self, minute_scores: list[float], average_score: float) -> None:
        feedback = self.ai_coach.generate_feedback(minute_scores)
        self.ai_coach.save_session(
            minute_focus_scores=minute_scores,
            average_focus=average_score,
            ai_feedback=feedback,
        )

        self.after(
            0,
            lambda: self.report_screen.set_report(
                minute_scores=minute_scores,
                average_score=average_score,
                feedback=feedback,
            ),
        )

    def _on_close(self) -> None:
        self.session_screen.shutdown()
        self.destroy()
