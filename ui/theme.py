from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
import subprocess
from tkinter import font as tkfont
import customtkinter as ctk


ThemeMode = str
APP_FONT_FAMILY = "Noto Sans"
MONO_FONT_FAMILY = "DejaVu Sans Mono"


class ThemeManager:
    """Centralized semantic colors and instant appearance switching."""

    _PALETTES: dict[str, dict[str, str]] = {
        "Light": {
            "bg_app": "#F3F4F6",
            "bg_sidebar": "#FFFFFF",
            "bg_card": "#FFFFFF",
            "text_primary": "#1F2937",
            "text_secondary": "#6B7280",
            "accent_focus": "#10B981",
            "accent_warn": "#EF4444",
            "btn_neutral": "#E5E7EB",
            "btn_neutral_hover": "#D1D5DB",
            "sidebar_hover": "#F3F4F6",
            "input": "#F9FAFB",
        },
        "Dark": {
            "bg_app": "#0F0F0F",
            "bg_sidebar": "#141414",
            "bg_card": "#1A1A1A",
            "text_primary": "#FFFFFF",
            "text_secondary": "#888888",
            "accent_focus": "#2ECC71",
            "accent_warn": "#E74C3C",
            "btn_neutral": "#333333",
            "btn_neutral_hover": "#404040",
            "sidebar_hover": "#1F1F1F",
            "input": "#222222",
        },
    }

    def __init__(self, initial_mode: ThemeMode = "Dark") -> None:
        self.mode = self._normalize_mode(initial_mode)
        self._listeners: list[Callable[[], None]] = []
        ctk.set_widget_scaling(1.08)
        ctk.set_window_scaling(1.0)
        ctk.set_appearance_mode(self.mode)
        ctk.set_default_color_theme("green")

    def color(self, token: str) -> str:
        return self._PALETTES[self.mode][token]

    def palette(self) -> dict[str, str]:
        return dict(self._PALETTES[self.mode])

    def set_mode(self, mode: ThemeMode) -> None:
        next_mode = self._normalize_mode(mode)
        if next_mode == self.mode:
            return
        self.mode = next_mode
        ctk.set_appearance_mode(next_mode)
        for listener in list(self._listeners):
            listener()

    def toggle(self) -> None:
        self.set_mode("Light" if self.mode == "Dark" else "Dark")

    def register(self, listener: Callable[[], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    @staticmethod
    def _normalize_mode(mode: ThemeMode) -> ThemeMode:
        return "Light" if str(mode).strip().lower() == "light" else "Dark"


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=resolved_app_font(), size=size, weight=weight)


def mono_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=resolved_mono_font(), size=size, weight=weight)


def configure_tk_fonts(root: ctk.CTk) -> None:
    """Force Tk fallback fonts away from bitmap-looking defaults on Linux."""
    try:
        root.tk.call("tk", "scaling", 1.12)
    except Exception:
        pass

    family = resolved_app_font()
    for name, size, weight in [
        ("TkDefaultFont", 10, "normal"),
        ("TkTextFont", 10, "normal"),
        ("TkMenuFont", 10, "normal"),
        ("TkHeadingFont", 11, "bold"),
        ("TkCaptionFont", 10, "normal"),
        ("TkSmallCaptionFont", 9, "normal"),
        ("TkIconFont", 10, "normal"),
        ("TkTooltipFont", 9, "normal"),
    ]:
        try:
            tkfont.nametofont(name).configure(family=family, size=size, weight=weight)
        except Exception:
            continue


def resolved_app_font() -> str:
    return _resolve_font_family(("Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans", "Arial"), APP_FONT_FAMILY)


def resolved_mono_font() -> str:
    return _resolve_font_family(("Noto Sans Mono", "DejaVu Sans Mono", "Ubuntu Mono", "Liberation Mono"), MONO_FONT_FAMILY)


@lru_cache(maxsize=8)
def _resolve_font_family(candidates: tuple[str, ...], fallback: str) -> str:
    for candidate in candidates:
        try:
            output = subprocess.run(
                ["fc-match", "-f", "%{family}", candidate],
                check=False,
                capture_output=True,
                text=True,
                timeout=0.4,
            ).stdout.strip()
        except Exception:
            output = ""
        if output:
            return output.split(",")[0].strip() or candidate
    return fallback
