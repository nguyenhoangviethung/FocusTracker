# Architecture Guide

## 1. Mục tiêu hệ thống

FocusFlow AI là hệ thống edge-to-cloud chỉ dùng tín hiệu thị giác:

- Desktop đọc webcam và chạy MediaPipe.
- Desktop không gửi ảnh hoặc video lên cloud.
- Desktop gửi chuỗi đặc trưng khuôn mặt `(30, 30)`.
- Cloud enrich thành `(30, 90)`.
- Cloud chạy ensemble GRU + TCN + XGBoost.
- Firestore lưu lifecycle và summary của session.
- Report completion chỉ ghi trạng thái tổng kết, không còn AI coach hay email mentor.

Hệ thống không còn OS tracking, keyword heuristic, theo dõi bàn phím/chuột hoặc
Hardcore Mode.

## 2. Luồng dữ liệu

```text
Webcam frame
  -> MediaPipe Face Landmarker
  -> 30 raw facial features
  -> sliding window 30 frames
  -> raw sequence (30, 30)
  -> WebSocket TLS
  -> Cloud Run API
  -> enrich raw + velocity + std
  -> enriched sequence (30, 90)
  -> GRU ONNX
  -> TCN ONNX
  -> XGBoost
  -> late-fusion score
  -> FOCUSED / DISTRACTED
```

Khi không tìm thấy mặt, face-presence guard trả `NO_FACE` và không tin model
score.

## 3. Contract của model

Artifact runtime nằm trong `models/late_fusion/`.

```text
sequence length:       30
raw feature dim:       30
enriched feature dim:  90
GRU weight:            0.30
TCN weight:            0.30
XGBoost weight:        0.40
threshold:             0.54
```

Hàm chuẩn duy nhất để enrich dữ liệu:

```python
tracking.buffer.enrich_raw_sequence(raw_sequence)
```

Không tự viết một phép enrich khác trong server hoặc client.

## 4. Trách nhiệm từng vùng source

### Desktop

- `main.py`: entrypoint duy nhất.
- `ui/`: PyQt6 pages và components.
- `tracking/detector.py`: frame thành feature vector 30 chiều.
- `tracking/buffer.py`: sliding window và enrich chuẩn.
- `tracking/inference.py`: local fallback inference.
- `tracking/tracker.py`: camera worker, local/cloud/hybrid orchestration.
- `edge/cloud_client.py`: REST lifecycle và WebSocket transport.

### Shared

- `shared/contracts.py`: Pydantic schema version `1.0`.

Client và server phải dùng chung contract này. Khi breaking change, tạo protocol
version mới thay vì sửa âm thầm.

### Cloud API

- `server/app.py`: FastAPI lifespan và dependency initialization.
- `server/api/routes.py`: health, session, inference, WebSocket.
- `server/core/inference.py`: raw sequence thành model response.
- `server/repositories/sessions.py`: memory repository và Firestore repository.
- `server/services/event_publisher.py`: logging/Pub/Sub adapter.

## 5. Inference modes

### `local`

- Model chạy trên desktop.
- Không cần cloud.
- Dùng để phát triển và fallback.

### `cloud`

- Desktop chỉ extract feature.
- Cloud quyết định focus.
- Cần URL, API key và kết nối mạng.

### `hybrid`

- Desktop ưu tiên response cloud.
- Khi cloud chưa sẵn sàng, local model vẫn quyết định.
- Đây là mode phù hợp nhất cho demo luận văn.

## 6. Session lifecycle

1. Desktop gọi `POST /v1/sessions`.
2. Server tạo document session và trả `session_id`.
3. Desktop mở WebSocket theo `session_id`.
4. Desktop gửi telemetry packet.
5. Server trả inference response có cùng `message_id`.
6. Desktop gọi endpoint complete với summary.
7. Server lưu summary.
8. Server publish `session.completed`.
9. Server ghi report completion metadata.

## 7. Dữ liệu được và không được lưu

Được lưu:

- session ID;
- device ID;
- timestamps;
- duration/focused seconds;
- average focus;
- distraction transition count;
- focus streak;
- model version;
- report completion metadata.

Không lưu:

- webcam frame;
- video;
- facial landmarks đầy đủ;
- mọi raw feature sequence theo từng frame;
- window title, PID, keystroke hoặc mouse activity.

## 8. Nguyên tắc scale

- Cloud Run instance stateless.
- Firestore là durable session state.
- WebSocket mất kết nối phải reconnect.
- Queue desktop có giới hạn; bỏ sample cũ khi network chậm.
- Inference blocking chạy qua threadpool, không khóa asyncio.
- Model load một lần trong lifespan của mỗi Cloud Run instance.
- API là Cloud Run service duy nhất trong slice hiện tại.
- Chỉ tách inference service riêng sau khi benchmark chứng minh cần thiết.
