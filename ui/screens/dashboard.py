from __future__ import annotations

import customtkinter as ctk


class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent, fg_color="#0f1724")
        self.controller = controller
        self.minutes_var = ctk.StringVar(value="25")

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="nsew", padx=40, pady=(38, 18))

        ctk.CTkLabel(
            header,
            text="FocusFlow AI",
            font=ctk.CTkFont(family="Segoe UI", size=48, weight="bold"),
            text_color="#f5f7fb",
        ).pack(anchor="center")

        ctk.CTkLabel(
            header,
            text="Theo dõi mức độ tập trung theo thời gian thực",
            font=ctk.CTkFont(family="Segoe UI", size=18),
            text_color="#9ab0cf",
        ).pack(anchor="center", pady=(8, 0))

        card = ctk.CTkFrame(self, corner_radius=20, fg_color="#162237")
        card.grid(row=1, column=0, padx=40, pady=10, sticky="n")

        ctk.CTkLabel(
            card,
            text="Thiết lập phiên Pomodoro",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color="#f5f7fb",
        ).pack(padx=40, pady=(26, 8))

        ctk.CTkLabel(
            card,
            text="Thời lượng (phút)",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color="#a7bbd8",
        ).pack(pady=(6, 6))

        ctk.CTkOptionMenu(
            card,
            values=["25", "30", "45", "50"],
            variable=self.minutes_var,
            width=180,
            corner_radius=10,
            fg_color="#203454",
            button_color="#2e4a73",
            button_hover_color="#3c5f90",
        ).pack(pady=(2, 20))

        ctk.CTkButton(
            card,
            text="Bắt đầu phiên tập trung",
            width=260,
            height=44,
            corner_radius=12,
            fg_color="#2db07f",
            hover_color="#229f71",
            text_color="#081810",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            command=self._on_start_clicked,
        ).pack(pady=(4, 18))

        ctk.CTkLabel(
            card,
            text="Mẹo: giữ khuôn mặt trong khung hình camera để đo chính xác hơn.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#8aa0c0",
        ).pack(pady=(0, 24), padx=20)

    def _on_start_clicked(self) -> None:
        minutes = int(self.minutes_var.get())
        self.controller.start_focus_session(minutes)
