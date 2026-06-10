### 📋 BẢNG ĐẶC TẢ CÁC PHASE PHÁT TRIỂN (DEVELOPMENT PHASES)

| Phase | Tên Phase | Mục tiêu chính | Các Use Cases liên quan | Kết quả đầu ra (Deliverables) |
| --- | --- | --- | --- | --- |
| **P1** | **UI Foundation** | Chuẩn hóa desktop UI bằng `CustomTkinter` để tránh pixel/inconsistent theme trên Ubuntu | Giao diện cơ bản | `main.py`, `ui/app_window.py`, Theme Manager, Routing logic. |
| **P2** | **Core Monitoring** | Chạy ngầm Camera, đọc Window Title và suy luận late-fusion model | UC1, UC2, UC3, UC10 | Module `tracker.py`, `cv2` loop, logic fusion. |
| **P3** | **Kỷ luật & OS Control** | Can thiệp hệ thống (Hardcore) | UC6, UC8 | `os_tracker.py` (psutil), `settings.json`. |
| **P4** | **AI & Báo cáo** | Kết nối late-fusion model, AI Coach & Email | UC4, UC5, UC7 | `history.json`, OpenAI API, `smtplib`. |
| **P5** | **Polish & Demo** | Tối ưu trải nghiệm & Import Video | UC9, Demo Mode | `AIVisionPage`, tối ưu performance, build exe. |

---

### 🛠 Chi tiết thực thi từng Phase (Cho Agent)

#### Phase 1: Giao diện nền tảng

* **Chi tiết:** Dựng cấu trúc `CustomTkinter`. Sidebar chiếm 200px. Main frame chứa 4 trang.
* **Quyết định UI:** Chọn `CustomTkinter` thay vì `ttkbootstrap`; không mix toolkit để tránh lỗi render/pixel trên Ubuntu. Nếu UI bị mờ, ưu tiên chỉnh CTk scaling/font/image pipeline trước khi đổi toolkit.
* **Trọng tâm:** Switch đổi Theme (Light/Dark) phải hoạt động tức thời trên toàn app.

#### Phase 2: Động cơ chính (Trái tim của App)

* **Chi tiết:** Bạn sẽ cần 2 Thread tách biệt:
* `Thread A`: Quay phim, chạy MediaPipe, đẩy kết quả vào `FeatureSequenceBuffer`, sau đó suy luận ensemble GRU + TCN + XGBoost.
* `Thread B`: Quét tiêu đề cửa sổ, so sánh từ khóa.


* **Trọng tâm:** Code `fusion_logic` (Hàm quyết định cuối cùng) đặt ở `main.py`; model runtime nằm ở `tracking/inference.py`.

#### Phase 3: Kỷ luật & Tùy biến

* **Chi tiết:** Đưa tính năng `Hardcore Mode` vào. Sử dụng `psutil` để liệt kê các tiến trình. Nếu người dùng mở app trong "Distracting List", hệ thống đếm ngược 30 giây rồi thực hiện `process.terminate()`.
* **Trọng tâm:** Đảm bảo quyền truy cập (Admin mode) khi khởi chạy ứng dụng để có quyền kill process.

#### Phase 4: Báo cáo & AI Coach

* **Chi tiết:** Xử lý file `history.json`. Mỗi khi hết phiên, ghi dữ liệu (Tổng thời gian, Số lần xao nhãng) vào đây.
* **Trọng tâm:** Hàm `send_report_email(mentor_email, summary_data)` dùng `email.mime` để tạo một email định dạng HTML đẹp mắt (có màu xanh/đỏ báo cáo tập trung).

#### Phase 5: Demo Mode & Performance

* **Chi tiết:** UC10 là chìa khóa. Thêm một `CTkButton` trong Settings/Home có chức năng `filedialog.askopenfilename()`. Truyền đường dẫn file đó vào `cv2.VideoCapture(path)`.
* **Trọng tâm:** Tối ưu hóa việc xóa (cleanup) tài nguyên khi người dùng bấm "Kết thúc phiên" để máy tính trở lại trạng thái nhàn rỗi.

---

### 🧭 Quy ước bảo trì hiện tại

* Entrypoint duy nhất: `python main.py`.
* Không dùng lại các màn hình cũ kiểu `dashboard/session_screen/report_screen`; flow mới là `HomePage -> ActiveSessionPage -> ReportPage`, cộng `SettingsPage` và `AIVisionPage`.
* Tài liệu model production đã được kéo về `GUIDE.md`; khi đổi artifact, cập nhật `models/late_fusion/` và `GUIDE.md` cùng lúc.
* Runtime không phụ thuộc PyTorch; chỉ dùng ONNXRuntime + XGBoost cho inference trong app.
