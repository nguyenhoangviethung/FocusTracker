from __future__ import annotations

import customtkinter as ctk


class ReportScreen(ctk.CTkFrame):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent, fg_color="#0f1724")
        self.controller = controller

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text="Báo Cáo Sau Phiên",
            font=ctk.CTkFont(family="Segoe UI", size=36, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, pady=(28, 8), padx=24, sticky="n")

        self.summary_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=16),
            text_color="#9eb4d4",
        )
        self.summary_label.grid(row=1, column=0, pady=(0, 10), padx=24)

        card = ctk.CTkFrame(self, fg_color="#162237", corner_radius=16)
        card.grid(row=2, column=0, sticky="nsew", padx=30, pady=(6, 14))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Nhận xét từ AI Coach",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, padx=18, pady=(14, 8), sticky="w")

        self.feedback_text = ctk.CTkTextbox(
            card,
            corner_radius=12,
            fg_color="#0f1a2c",
            text_color="#d7e1f2",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            wrap="word",
        )
        self.feedback_text.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 14))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, pady=(0, 24))

        ctk.CTkButton(
            actions,
            text="Bắt đầu phiên mới",
            width=180,
            command=self.controller.start_new_session,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            actions,
            text="Quay lại màn hình chính",
            width=200,
            fg_color="#2a3b5e",
            hover_color="#334b73",
            command=self.controller.show_dashboard,
        ).pack(side="left", padx=8)

    def show_loading(self, minute_scores: list[float], average_score: float) -> None:
        self.summary_label.configure(
            text=(
                f"Số phút ghi nhận: {len(minute_scores)} | "
                f"Điểm tập trung trung bình: {average_score * 100:.1f}%"
            )
        )
        self.feedback_text.delete("1.0", "end")
        self.feedback_text.insert("1.0", "Đang tạo phản hồi AI...")

    def set_report(self, minute_scores: list[float], average_score: float, feedback: str) -> None:
        formatted_scores = ", ".join(f"{score * 100:.1f}%" for score in minute_scores)
        self.summary_label.configure(
            text=(
                f"Số phút ghi nhận: {len(minute_scores)} | "
                f"TB: {average_score * 100:.1f}% | "
                f"Điểm từng phút: [{formatted_scores}]"
            )
        )
        self.feedback_text.delete("1.0", "end")
        self.feedback_text.insert("1.0", feedback)
