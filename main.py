from __future__ import annotations

import customtkinter as ctk

from ui.app_window import FocusFlowApp


def main() -> None:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = FocusFlowApp()
    app.mainloop()


if __name__ == "__main__":
    main()
