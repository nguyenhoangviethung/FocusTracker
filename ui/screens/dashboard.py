from __future__ import annotations

import customtkinter as ctk


class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, controller) -> None:
        super().__init__(parent, fg_color="#08111d")
        self.controller = controller
        self.minutes_var = ctk.StringVar(value="25")
        self.error_var = ctk.StringVar(value="")

        self._min_minutes = 1
        self._max_minutes = 180

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, corner_radius=28, fg_color="#0c1726")
        shell.grid(row=0, column=0, sticky="nsew", padx=24, pady=22)
        shell.grid_columnconfigure(0, weight=3)
        shell.grid_columnconfigure(1, weight=2)
        shell.grid_rowconfigure(0, weight=1)

        hero = ctk.CTkFrame(shell, corner_radius=28, fg_color="#0d1827")
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        hero.grid_columnconfigure(0, weight=1)
        hero.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            hero,
            text="FocusFlow AI",
            font=ctk.CTkFont(family="Segoe UI", size=48, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, sticky="w", padx=32, pady=(34, 10))

        ctk.CTkLabel(
            hero,
            text="Giao diện giám sát tập trung theo thời gian thực",
            font=ctk.CTkFont(family="Segoe UI", size=18),
            text_color="#9db2cf",
        ).grid(row=1, column=0, sticky="w", padx=32, pady=(0, 14))

        feature_card = ctk.CTkFrame(hero, corner_radius=24, fg_color="#132133")
        feature_card.grid(row=2, column=0, sticky="nsew", padx=32, pady=(0, 32))
        feature_card.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            feature_card,
            text="Luồng theo dõi đang bật",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#f4f7fb",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(18, 10))

        chips = (
            ("Camera + FaceMesh", "Trích xuất 30 đặc trưng mỗi khung hình"),
            ("ONNX Runtime", "Suy luận GRU nhẹ, không dùng PyTorch trong app"),
            ("OS Tracker", "Gắn thêm tín hiệu cửa sổ và ứng dụng đang active"),
            ("Queue an toàn", "UI và worker tách riêng, không khóa giao diện"),
        )

        for index, (title, description) in enumerate(chips):
            row = 1 + index // 2
            column = index % 2
            chip = ctk.CTkFrame(feature_card, corner_radius=18, fg_color="#0d1726")
            chip.grid(row=row, column=column, sticky="nsew", padx=12, pady=10)
            chip.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                chip,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color="#eaf2ff",
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))

            ctk.CTkLabel(
                chip,
                text=description,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color="#8ea3c1",
                wraplength=300,
                justify="left",
            ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 14))

        config = ctk.CTkFrame(shell, corner_radius=28, fg_color="#121e31")
        config.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        config.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            config,
            text="Thiết lập phiên",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#f4f7fb",
        ).pack(anchor="w", padx=28, pady=(28, 8))

        ctk.CTkLabel(
            config,
            text="Chọn số phút và bắt đầu màn hình giám sát giống bố cục ASCII bạn yêu cầu.",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color="#9cb1cf",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(0, 18))

        self.minutes_entry = ctk.CTkEntry(
            config,
            textvariable=self.minutes_var,
            width=150,
            height=42,
            corner_radius=12,
            placeholder_text="25",
            fg_color="#0c1524",
            border_color="#385175",
            text_color="#f4f7fb",
            font=ctk.CTkFont(family="Segoe UI", size=15),
        )
        self.minutes_entry.pack(anchor="w", padx=28, pady=(2, 10))

        self.minutes_slider = ctk.CTkSlider(
            config,
            from_=self._min_minutes,
            to=self._max_minutes,
            number_of_steps=self._max_minutes - self._min_minutes,
            command=self._on_slider_changed,
            progress_color="#3d5f91",
            button_color="#5c82b8",
            button_hover_color="#7397ca",
        )
        self.minutes_slider.pack(fill="x", padx=28, pady=(4, 8))
        self.minutes_slider.set(25)

        presets = ctk.CTkFrame(config, fg_color="transparent")
        presets.pack(anchor="w", padx=28, pady=(6, 10))

        for label, value in (("15", 15), ("25", 25), ("45", 45), ("60", 60)):
            ctk.CTkButton(
                presets,
                text=f"{label} phút",
                width=84,
                height=34,
                corner_radius=10,
                fg_color="#203451",
                hover_color="#2d4a73",
                command=lambda chosen=value: self._set_minutes(chosen),
            ).pack(side="left", padx=6)

        self.error_label = ctk.CTkLabel(
            config,
            textvariable=self.error_var,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#f39cb0",
            wraplength=360,
        )
        self.error_label.pack(anchor="w", padx=28, pady=(6, 12))

        ctk.CTkButton(
            config,
            text="Bắt đầu màn giám sát",
            width=260,
            height=46,
            corner_radius=14,
            fg_color="#2db07f",
            hover_color="#23996e",
            text_color="#081810",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            command=self._on_start_clicked,
        ).pack(anchor="w", padx=28, pady=(6, 18))

        ctk.CTkLabel(
            config,
            text="Mẹo: giữ khuôn mặt ở giữa khung camera để mô hình và FaceMesh ổn định hơn.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#8ea3c1",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(0, 28))

        self.minutes_var.trace_add("write", lambda *_args: self._sync_slider_from_entry())

    def _on_start_clicked(self) -> None:
        minutes = self._parse_minutes()
        if minutes is None:
            return

        self.error_var.set("")
        self.controller.start_focus_session(minutes)

    def _set_minutes(self, minutes: int) -> None:
        clamped = self._clamp_minutes(minutes)
        self.minutes_var.set(str(clamped))
        self.minutes_slider.set(clamped)
        self.error_var.set("")

    def _sync_slider_from_entry(self) -> None:
        parsed = self._parse_minutes(show_error=False)
        if parsed is None:
            return
        self.minutes_slider.set(parsed)

    def _on_slider_changed(self, value: float) -> None:
        minutes = self._clamp_minutes(int(round(float(value))))
        if self.minutes_var.get().strip() != str(minutes):
            self.minutes_var.set(str(minutes))
        self.error_var.set("")

    def _parse_minutes(self, show_error: bool = True) -> int | None:
        raw_value = self.minutes_var.get().strip()
        try:
            minutes = int(float(raw_value))
        except ValueError:
            if show_error:
                self.error_var.set("Vui lòng nhập số phút hợp lệ, ví dụ 25.")
            return None

        if minutes < self._min_minutes or minutes > self._max_minutes:
            if show_error:
                self.error_var.set(f"Số phút phải nằm trong khoảng {self._min_minutes}-{self._max_minutes}.")
            return None

        return minutes

    def _clamp_minutes(self, minutes: int) -> int:
        return max(self._min_minutes, min(self._max_minutes, int(minutes)))
