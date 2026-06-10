from __future__ import annotations

from collections.abc import Callable
import customtkinter as ctk

from ui.theme import ThemeManager, font


class SidebarNavigation(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        theme: ThemeManager,
        on_select: Callable[[str], None],
        on_toggle_theme: Callable[[], None],
    ) -> None:
        super().__init__(parent, width=200, corner_radius=0, border_width=0)
        self.grid_propagate(False)
        self.theme = theme
        self._on_select = on_select
        self._on_toggle_theme = on_toggle_theme
        self._active_key = "home"
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._labels: list[ctk.CTkLabel] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(8, weight=1)

        self.logo_label = ctk.CTkLabel(self, text="FocusFlow", font=font(24, "bold"), anchor="w")
        self.logo_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 2))
        self._labels.append(self.logo_label)

        self.subtitle_label = ctk.CTkLabel(self, text="AI Pomodoro", font=font(12), anchor="w")
        self.subtitle_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 24))
        self._labels.append(self.subtitle_label)

        items = [
            ("home", "Home"),
            ("report", "Report"),
            ("settings", "Settings"),
            ("vision", "Vision"),
        ]
        for row, (key, label) in enumerate(items, start=2):
            button = ctk.CTkButton(
                self,
                text=label,
                height=42,
                anchor="w",
                corner_radius=8,
                border_width=0,
                font=font(14, "bold"),
                command=lambda selected=key: self._select(selected),
            )
            button.grid(row=row, column=0, sticky="ew", padx=12, pady=5)
            self._buttons[key] = button

        self.theme_button = ctk.CTkButton(
            self,
            text="Dark Mode",
            height=38,
            corner_radius=8,
            border_width=0,
            font=font(13, "bold"),
            command=self._on_toggle_theme,
        )
        self.theme_button.grid(row=9, column=0, sticky="ew", padx=12, pady=(10, 18))
        self.apply_theme()

    def set_active(self, key: str) -> None:
        self._active_key = key if key in self._buttons else "home"
        self.apply_theme()

    def apply_theme(self) -> None:
        palette = self.theme.palette()
        self.configure(fg_color=palette["bg_sidebar"])
        self.logo_label.configure(text_color=palette["text_primary"])
        self.subtitle_label.configure(text_color=palette["text_secondary"])

        for key, button in self._buttons.items():
            is_active = key == self._active_key
            button.configure(
                fg_color=palette["accent_focus"] if is_active else "transparent",
                hover_color=palette["accent_focus"] if is_active else palette["sidebar_hover"],
                text_color="#FFFFFF" if is_active else palette["text_primary"],
            )

        self.theme_button.configure(
            text="Light Mode" if self.theme.mode == "Dark" else "Dark Mode",
            fg_color=palette["btn_neutral"],
            hover_color=palette["btn_neutral_hover"],
            text_color=palette["text_primary"],
        )

    def _select(self, key: str) -> None:
        self.set_active(key)
        self._on_select(key)
