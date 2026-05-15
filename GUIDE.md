# FocusFlow AI - Guide

Tài liệu này hướng dẫn cách chạy, kiểm tra và đóng gói ứng dụng FocusFlow AI trong môi trường `miniconda3/envs/thesis`.

## 1. Chuẩn bị môi trường

### 1.1 Kích hoạt môi trường Conda

```bash
source /home/bear/miniconda3/etc/profile.d/conda.sh
conda activate thesis
```

Nếu máy bạn đã cấu hình sẵn `conda` trong shell, có thể chỉ cần:

```bash
conda activate thesis
```

### 1.2 Cài dependencies

Từ thư mục gốc của dự án:

```bash
pip install -r requirements.txt
```

Nếu bạn cần export lại model từ checkpoint PyTorch sang ONNX, cài thêm bộ công cụ export:

```bash
pip install -r scripts/requirements_export.txt
```

### 1.3 Cấu hình API key cho AI Coach

Tạo file `.env` ở thư mục gốc nếu muốn dùng phần AI Coach sau phiên:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
```

Nếu không có API key, ứng dụng vẫn chạy được, nhưng phần báo cáo AI sẽ dùng nội dung thay thế.

## 2. Chạy ứng dụng chính

Khởi chạy giao diện desktop bằng:

```bash
python main.py
```

Luồng sử dụng cơ bản:

1. Màn hình Dashboard hiện ra.
2. Chọn thời lượng Pomodoro.
3. Bấm nút bắt đầu phiên.
4. Ứng dụng mở camera, chạy tracking nền và hiển thị focus score theo thời gian thực.
5. Kết thúc phiên để xem báo cáo và phản hồi AI.

## 3. Kiểm tra logic camera + ONNX

Trước khi dùng giao diện, bạn nên test nhanh pipeline camera, MediaPipe và ONNX:

### 3.1 Export ONNX model

```bash
python scripts/export_to_onnx.py
```

Lệnh này tạo file `models/engagement_gru.onnx` từ checkpoint PyTorch trong `train_2/engagement_gru.pt`.

### 3.2 Chạy test tracker

```bash
python test_tracker.py
```

Trong cửa sổ OpenCV:

- `WARMING_UP` nghĩa là buffer chưa đủ 60 frame.
- Khi đủ dữ liệu, trạng thái sẽ chuyển sang `ENGAGED` hoặc `DISTRACTED`.
- Nhấn `q` để thoát.

## 4. Chạy kiểm tra logic trong môi trường `thesis`

Nếu bạn muốn xác nhận nhanh rằng môi trường Python đang đúng và module chính import được, có thể chạy một lệnh kiểm tra nhẹ:

```bash
python -c "from tracking.buffer import FeatureSequenceBuffer; from tracking.inference import ONNXEngagementInferencer; print('OK')"
```

Nếu muốn kiểm tra riêng phần UI khởi tạo được hay không:

```bash
python -c "import customtkinter as ctk; from ui.app_window import FocusFlowApp; print('UI OK')"
```

## 5. Đóng gói ứng dụng

### 5.1 Build bằng script

```bash
bash scripts/build_exe.sh
```

### 5.2 Build bằng PyInstaller trực tiếp

```bash
pyinstaller focusflow_app.spec --clean
```

Kết quả build thường nằm trong thư mục `dist/`.

## 6. Dữ liệu và file quan trọng

- `models/engagement_gru.onnx`: model ONNX dùng ở runtime.
- `train_2/engagement_gru.pt`: checkpoint gốc để export lại model.
- `data/history.json`: lịch sử các phiên đã hoàn thành.
- `.env`: nơi lưu `OPENAI_API_KEY`.

## 7. Ghi chú vận hành

- Ứng dụng được thiết kế để chạy nền, ưu tiên CPU thấp.
- Camera, MediaPipe và ONNX chạy ở background thread, không chặn giao diện.
- Nếu camera không mở được, hãy kiểm tra quyền truy cập webcam và số index camera.
- Nếu thiếu model ONNX, hãy chạy lại `python scripts/export_to_onnx.py`.

## 8. Xử lý lỗi thường gặp

### Không mở được camera

- Kiểm tra webcam có đang bị ứng dụng khác chiếm dụng không.
- Thử đổi camera index trong `test_tracker.py`.

### Thiếu `engagement_gru.onnx`

- Chạy:

```bash
python scripts/export_to_onnx.py
```

### Thiếu OpenAI API key

- Tạo file `.env` ở thư mục gốc và thêm `OPENAI_API_KEY`.

### Lỗi import thư viện

- Xác nhận bạn đang ở môi trường `thesis`:

```bash
conda activate thesis
python -c "import sys; print(sys.executable)"
```

## 9. Trình tự khuyến nghị

Nếu bạn mới clone project, hãy làm theo thứ tự này:

1. Kích hoạt `thesis`.
2. Cài dependencies.
3. Tạo `.env` nếu cần AI Coach.
4. Export ONNX model.
5. Chạy `test_tracker.py` để kiểm tra camera + inference.
6. Chạy `main.py` để dùng toàn bộ ứng dụng.

## 10. Tóm tắt ngắn

- Dùng `python main.py` để chạy app.
- Dùng `python test_tracker.py` để kiểm tra logic camera và ONNX.
- Dùng `bash scripts/build_exe.sh` để đóng gói.
- Luôn chạy trong môi trường `miniconda3/envs/thesis` nếu bạn muốn đúng phụ thuộc của dự án.
