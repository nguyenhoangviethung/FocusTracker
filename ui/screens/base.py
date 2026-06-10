from __future__ import annotations

import customtkinter as ctk

from ui.theme import ThemeManager, font


class ThemedPage(ctk.CTkFrame):
    def __init__(self, parent, controller, theme: ThemeManager) -> None:
        super().__init__(parent, corner_radius=0, border_width=0)
        self.controller = controller
        self.theme = theme

    def apply_theme(self) -> None:
        self.configure(fg_color=self.theme.color("bg_app"))


class PageTitle(ctk.CTkFrame):
    def __init__(self, parent, theme: ThemeManager, title: str, subtitle: str) -> None:
        super().__init__(parent, fg_color="transparent", border_width=0)
        self.theme = theme
        self.title_label = ctk.CTkLabel(self, text=title, font=font(28, "bold"), anchor="w")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ctk.CTkLabel(self, text=subtitle, font=font(14), anchor="w")
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.apply_theme()

    def apply_theme(self) -> None:
        self.title_label.configure(text_color=self.theme.color("text_primary"))
        self.subtitle_label.configure(text_color=self.theme.color("text_secondary"))


class Card(ctk.CTkFrame):
    def __init__(self, parent, theme: ThemeManager) -> None:
        super().__init__(parent, corner_radius=12, border_width=0)
        self.theme = theme
        self.apply_theme()

    def apply_theme(self) -> None:
        self.configure(fg_color=self.theme.color("bg_card"))
