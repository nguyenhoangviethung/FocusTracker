from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ui.screens.base import Card, PageTitle, ThemedPage
from ui.theme import ThemeManager, font
from utils.session_storage import load_session_history


class ReportPage(ThemedPage):
    def __init__(self, parent, controller, theme: ThemeManager) -> None:
        super().__init__(parent, controller, theme)
        self.grid_columnconfigure((0, 1, 2), weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header = PageTitle(
            self,
            theme,
            "Báo cáo phiên học",
            "Tổng kết phiên, AI Coach và trạng thái gửi mentor report.",
        )
        self.header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=32, pady=(28, 18))

        self.focus_card = self._metric_card("Điểm tập trung", "0.0%", 0)
        self.duration_card = self._metric_card("Thời lượng", "0 phút", 1)
        self.distraction_card = self._metric_card("Xao nhãng", "0 lần", 2)

        self.body_card = Card(self, theme)
        self.body_card.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=32, pady=(0, 32))
        self.body_card.grid_columnconfigure(0, weight=1)
        self.body_card.grid_columnconfigure(1, minsize=280, weight=0)
        self.body_card.grid_rowconfigure(2, weight=1)

        self.status_label = ctk.CTkLabel(self.body_card, text="Chưa có dữ liệu phiên.", font=font(14), anchor="w")
        self.status_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(22, 8))

        self.email_label = ctk.CTkLabel(self.body_card, text="Email mentor: chưa gửi", font=font(13), anchor="w")
        self.email_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=24, pady=(0, 10))

        self.summary = ctk.CTkTextbox(
            self.body_card,
            height=260,
            corner_radius=8,
            border_width=0,
            font=font(14),
            wrap="word",
        )
        self.summary.grid(row=2, column=0, sticky="nsew", padx=(24, 12), pady=(0, 24))

        self.history_panel = ctk.CTkScrollableFrame(
            self.body_card,
            corner_radius=8,
            border_width=0,
            label_text="Lịch sử gần đây",
            label_font=font(14, "bold"),
        )
        self.history_panel.grid(row=2, column=1, sticky="nsew", padx=(12, 24), pady=(0, 24))
        self.history_panel.grid_columnconfigure(0, weight=1)
        self._history_rows: list[ctk.CTkFrame | ctk.CTkLabel] = []
        self._set_summary_text(
            "Chưa có dữ liệu phiên mới.\n\n"
            "Khi kết thúc phiên, FocusFlow sẽ lưu history.json, tạo coaching bằng OpenAI "
            "và gửi email nếu bạn bật mentor report."
        )
        self._render_history()
        self.apply_theme()

    def show_session(self, session_record: dict[str, Any], processing: bool = False) -> None:
        focus = float(session_record.get("average_focus", 0.0))
        duration_seconds = int(session_record.get("duration_seconds", 0))
        focused_seconds = int(session_record.get("focused_seconds", 0))
        distractions = int(session_record.get("distraction_count", 0))
        completed = bool(session_record.get("completed", False))
        minute_scores = [float(score) for score in session_record.get("minute_focus_scores", [])]
        feedback = str(session_record.get("ai_feedback") or "").strip()
        email_status = session_record.get("email_status") if isinstance(session_record.get("email_status"), dict) else {}

        self.focus_value.configure(text=f"{focus * 100:.1f}%")
        self.duration_value.configure(text=f"{duration_seconds // 60} phút")
        self.distraction_value.configure(text=f"{distractions} lần")

        state_text = "Đang tạo AI Coach..." if processing else "Báo cáo đã sẵn sàng"
        self.status_label.configure(
            text=(
                f"{state_text} | "
                f"{'Hoàn thành' if completed else 'Kết thúc sớm'} | "
                f"Tập trung {focused_seconds // 60} phút"
            )
        )

        if email_status:
            self.email_label.configure(text=f"Email mentor: {email_status.get('message', 'Không rõ trạng thái')}")
        else:
            self.email_label.configure(text="Email mentor: đang chờ xử lý" if processing else "Email mentor: không bật")

        timeline = "\n".join(
            f"Phút {index + 1:02d}: {score * 100:.1f}%"
            for index, score in enumerate(minute_scores)
        ) or "Chưa đủ dữ liệu theo phút."
        coach_text = feedback or "AI Coach đang tạo phản hồi 3 câu..."
        self._set_summary_text(f"AI Coach:\n{coach_text}\n\nTimeline:\n{timeline}")
        self._render_history()

    def apply_settings(self, settings: dict[str, object]) -> None:
        self._render_history()

    def apply_theme(self) -> None:
        super().apply_theme()
        self.header.apply_theme()
        palette = self.theme.palette()
        for card in [self.focus_card, self.duration_card, self.distraction_card, self.body_card]:
            card.apply_theme()
        for label in [
            self.focus_title,
            self.duration_title,
            self.distraction_title,
            self.focus_value,
            self.duration_value,
            self.distraction_value,
            self.status_label,
        ]:
            label.configure(text_color=palette["text_primary"])
        self.email_label.configure(text_color=palette["text_secondary"])
        self.summary.configure(fg_color=palette["input"], text_color=palette["text_primary"])
        self.history_panel.configure(fg_color=palette["input"], label_text_color=palette["text_primary"])
        self._render_history()

    def _metric_card(self, title: str, value: str, column: int) -> Card:
        card = Card(self, self.theme)
        card.grid(row=1, column=column, sticky="ew", padx=(32 if column == 0 else 8, 32 if column == 2 else 8), pady=(0, 18))
        card.grid_columnconfigure(0, weight=1)
        title_label = ctk.CTkLabel(card, text=title, font=font(13), anchor="w")
        title_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        value_label = ctk.CTkLabel(card, text=value, font=font(24, "bold"), anchor="w")
        value_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        setattr(self, f"{_slug(title)}_title", title_label)
        setattr(self, f"{_slug(title)}_value", value_label)
        return card

    def _set_summary_text(self, text: str) -> None:
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.configure(state="disabled")

    def _render_history(self) -> None:
        for row in self._history_rows:
            row.destroy()
        self._history_rows.clear()

        palette = self.theme.palette()
        history = load_session_history()[:8]
        if not history:
            empty = ctk.CTkLabel(
                self.history_panel,
                text="Chưa có phiên nào.",
                font=font(13),
                text_color=palette["text_secondary"],
                anchor="w",
            )
            empty.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
            self._history_rows.append(empty)
            return

        for index, record in enumerate(history):
            card = ctk.CTkFrame(self.history_panel, corner_radius=8, border_width=0, fg_color=palette["bg_card"])
            card.grid(row=index, column=0, sticky="ew", padx=8, pady=6)
            card.grid_columnconfigure(0, weight=1)
            focus = float(record.get("average_focus", 0.0)) * 100.0
            duration_minutes = int(record.get("duration_seconds", 0)) // 60
            timestamp = str(record.get("timestamp") or "")[:16].replace("T", " ")
            title = ctk.CTkLabel(
                card,
                text=f"{focus:.1f}% | {duration_minutes} phút",
                font=font(13, "bold"),
                text_color=palette["text_primary"],
                anchor="w",
            )
            title.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
            subtitle = ctk.CTkLabel(
                card,
                text=timestamp,
                font=font(12),
                text_color=palette["text_secondary"],
                anchor="w",
            )
            subtitle.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
            open_button = ctk.CTkButton(
                card,
                text="Mở",
                width=58,
                height=28,
                corner_radius=8,
                border_width=0,
                fg_color=palette["btn_neutral"],
                hover_color=palette["btn_neutral_hover"],
                text_color=palette["text_primary"],
                font=font(12, "bold"),
                command=lambda selected=record: self.show_session(selected, processing=False),
            )
            open_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=10, pady=8)
            self._history_rows.append(card)


def _slug(value: str) -> str:
    mapping = {
        "Điểm tập trung": "focus",
        "Thời lượng": "duration",
        "Xao nhãng": "distraction",
    }
    return mapping[value]
