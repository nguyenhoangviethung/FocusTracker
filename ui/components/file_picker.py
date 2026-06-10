from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

from ui.theme import ThemeManager, font


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class VideoFilePicker(ctk.CTkToplevel):
    """A CustomTkinter file picker to avoid the old pixelated Tk dialog on Linux."""

    def __init__(
        self,
        parent,
        theme: ThemeManager,
        initial_path: str | Path,
        on_select: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self._on_select = on_select
        self._current_dir = self._resolve_initial_dir(initial_path)
        self._selected_file: Path | None = None
        self._rows: list[ctk.CTkButton] = []

        self.title("Chọn video demo")
        self.geometry("760x520")
        self.minsize(680, 460)
        self.transient(parent.winfo_toplevel())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header = ctk.CTkFrame(self, corner_radius=0, border_width=0)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)

        self.title_label = ctk.CTkLabel(self.header, text="Chọn video demo", font=font(22, "bold"), anchor="w")
        self.title_label.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=(20, 6))

        self.path_label = ctk.CTkLabel(self.header, text="", font=font(13), anchor="w")
        self.path_label.grid(row=1, column=0, columnspan=3, sticky="ew", padx=24, pady=(0, 14))

        self.up_button = ctk.CTkButton(
            self.header,
            text="Lên thư mục",
            width=120,
            height=36,
            corner_radius=10,
            border_width=0,
            font=font(13, "bold"),
            command=self._go_up,
        )
        self.up_button.grid(row=2, column=0, sticky="w", padx=(24, 8), pady=(0, 18))

        self.home_button = ctk.CTkButton(
            self.header,
            text="Home",
            width=90,
            height=36,
            corner_radius=10,
            border_width=0,
            font=font(13, "bold"),
            command=self._go_home,
        )
        self.home_button.grid(row=2, column=1, sticky="w", padx=8, pady=(0, 18))

        self.file_name = ctk.StringVar(value="")
        self.file_entry = ctk.CTkEntry(
            self,
            textvariable=self.file_name,
            height=38,
            corner_radius=10,
            border_width=0,
            font=font(13),
            placeholder_text="Chọn file .mp4/.mov/.avi...",
        )
        self.file_entry.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))

        self.list_frame = ctk.CTkScrollableFrame(self, corner_radius=14, border_width=0)
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 16))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.actions = ctk.CTkFrame(self, corner_radius=0, border_width=0)
        self.actions.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 24))
        self.actions.grid_columnconfigure(0, weight=1)

        self.hint_label = ctk.CTkLabel(self.actions, text="Chỉ hiển thị thư mục và file video.", font=font(12), anchor="w")
        self.hint_label.grid(row=0, column=0, sticky="ew")

        self.cancel_button = ctk.CTkButton(
            self.actions,
            text="Hủy",
            width=96,
            height=38,
            corner_radius=10,
            border_width=0,
            font=font(13, "bold"),
            command=self.destroy,
        )
        self.cancel_button.grid(row=0, column=1, sticky="e", padx=(12, 8))

        self.select_button = ctk.CTkButton(
            self.actions,
            text="Chọn video",
            width=128,
            height=38,
            corner_radius=10,
            border_width=0,
            font=font(13, "bold"),
            command=self._confirm,
        )
        self.select_button.grid(row=0, column=2, sticky="e")

        self._apply_theme()
        self._refresh()
        self.after(50, self._activate_modal)

    @staticmethod
    def _resolve_initial_dir(initial_path: str | Path) -> Path:
        path = Path(initial_path).expanduser() if str(initial_path).strip() else Path.home()
        if path.is_file():
            return path.parent
        if path.exists():
            return path
        return Path.home()

    def _apply_theme(self) -> None:
        palette = self.theme.palette()
        self.configure(fg_color=palette["bg_app"])
        self.header.configure(fg_color=palette["bg_card"])
        self.actions.configure(fg_color=palette["bg_app"])
        self.list_frame.configure(fg_color=palette["bg_card"])
        self.title_label.configure(text_color=palette["text_primary"])
        self.path_label.configure(text_color=palette["text_secondary"])
        self.hint_label.configure(text_color=palette["text_secondary"])
        self.file_entry.configure(
            fg_color=palette["input"],
            text_color=palette["text_primary"],
            placeholder_text_color=palette["text_secondary"],
        )
        for button in [self.up_button, self.home_button, self.cancel_button]:
            button.configure(
                fg_color=palette["btn_neutral"],
                hover_color=palette["btn_neutral_hover"],
                text_color=palette["text_primary"],
            )
        self.select_button.configure(
            fg_color=palette["accent_focus"],
            hover_color=palette["accent_focus"],
            text_color="#FFFFFF",
        )

    def _refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        self.path_label.configure(text=str(self._current_dir))
        entries = self._list_entries(self._current_dir)
        if not entries:
            empty = ctk.CTkButton(
                self.list_frame,
                text="Không có video trong thư mục này",
                height=42,
                corner_radius=10,
                border_width=0,
                anchor="w",
                state="disabled",
                font=font(13),
            )
            empty.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
            self._rows.append(empty)
            return

        palette = self.theme.palette()
        for index, path in enumerate(entries):
            is_dir = path.is_dir()
            label = f"{'[DIR]' if is_dir else '[VID]'}  {path.name}"
            row = ctk.CTkButton(
                self.list_frame,
                text=label,
                height=42,
                corner_radius=10,
                border_width=0,
                anchor="w",
                font=font(13, "bold" if is_dir else "normal"),
                fg_color="transparent",
                hover_color=palette["sidebar_hover"],
                text_color=palette["text_primary"],
                command=lambda selected=path: self._open_or_select(selected),
            )
            row.grid(row=index, column=0, sticky="ew", padx=10, pady=4)
            self._rows.append(row)

    @staticmethod
    def _list_entries(directory: Path) -> list[Path]:
        try:
            children = list(directory.iterdir())
        except OSError:
            return []
        visible = [path for path in children if not path.name.startswith(".")]
        dirs = sorted([path for path in visible if path.is_dir()], key=lambda path: path.name.lower())
        videos = sorted(
            [path for path in visible if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS],
            key=lambda path: path.name.lower(),
        )
        return dirs + videos

    def _open_or_select(self, path: Path) -> None:
        if path.is_dir():
            self._current_dir = path
            self._selected_file = None
            self.file_name.set("")
            self._refresh()
            return
        self._selected_file = path
        self.file_name.set(path.name)

    def _go_up(self) -> None:
        parent = self._current_dir.parent
        if parent != self._current_dir:
            self._current_dir = parent
            self._selected_file = None
            self.file_name.set("")
            self._refresh()

    def _go_home(self) -> None:
        self._current_dir = Path.home()
        self._selected_file = None
        self.file_name.set("")
        self._refresh()

    def _confirm(self) -> None:
        selected = self._selected_file
        if selected is None:
            candidate = self._current_dir / self.file_name.get().strip()
            selected = candidate if candidate.is_file() else None
        if selected is None or selected.suffix.lower() not in VIDEO_EXTENSIONS:
            self.hint_label.configure(text="Hãy chọn một file video hợp lệ.")
            return
        self._on_select(str(selected))
        self.destroy()

    def _activate_modal(self) -> None:
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            # Some Linux window managers need one more event-loop tick before
            # a transient toplevel can own the grab.
            self.after(100, self._retry_grab)

    def _retry_grab(self) -> None:
        try:
            self.grab_set()
        except Exception:
            pass


def open_video_file_picker(parent, theme: ThemeManager, initial_path: str, on_select: Callable[[str], None]) -> None:
    picker = VideoFilePicker(parent, theme, initial_path, on_select)
    picker.focus()
