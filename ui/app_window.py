from __future__ import annotations

import customtkinter as ctk

from ui.screens.dashboard import DashboardScreen
from ui.screens.focus_guardian_screen import FocusGuardianScreen


class FocusFlowApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FocusFlow AI")
        self.geometry("1320x820")
        self.minsize(1100, 720)
        self.configure(fg_color="#08111d")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.dashboard_screen = DashboardScreen(container, controller=self)
        self.session_screen = FocusGuardianScreen(container, controller=self)

        for screen in (self.dashboard_screen, self.session_screen):
            screen.grid(row=0, column=0, sticky="nsew")

        self.show_dashboard()

    def show_dashboard(self) -> None:
        self.session_screen.reset_ui()
        self.dashboard_screen.tkraise()

    def start_new_session(self) -> None:
        self.show_dashboard()

    def start_focus_session(self, minutes: int | str) -> None:
        minutes = self._normalize_minutes(minutes)
        self.session_screen.prepare_session(minutes)
        self.session_screen.tkraise()
        self.session_screen.start_session()

    def on_session_finished(self, minute_scores: list[float], average_score: float, completed: bool) -> None:
        self.session_screen.finalize_session(
            minute_scores=minute_scores,
            average_score=average_score,
            completed=completed,
        )

    def _on_close(self) -> None:
        self.session_screen.shutdown()
        self.destroy()

    def _normalize_minutes(self, minutes: int | str) -> int:
        try:
            normalized = int(float(str(minutes).strip()))
        except ValueError:
            normalized = 25

        return max(1, min(180, normalized))
