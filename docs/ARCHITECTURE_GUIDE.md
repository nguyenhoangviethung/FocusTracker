# Architecture Guide

## 1. Mục tiêu hệ thống

FocusFlow AI là hệ thống edge-to-cloud chỉ dùng tín hiệu thị giác:

- Desktop đọc webcam và chạy MediaPipe.
- Desktop không gửi ảnh hoặc video lên cloud.
- Desktop gửi chuỗi đặc trưng khuôn mặt `(30, 30)`.
- Cloud enrich thành `(30, 90)`.
- Cloud chạy model 4-class `fixed_triple_xgb_fusion`.
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
  -> tsfresh-like tabular features (2161)
  -> final_xgb + boost_xgb + targeted_xgb
  -> weighted probability fusion + class bias + temperature
  -> argmax over 4 calibrated class probabilities
  -> class 2/3 = FOCUSED, class 0/1 = DISTRACTED
```

Khi không tìm thấy mặt, face-presence guard trả `NO_FACE` và không tin model
score.

## 3. Contract của model

Artifact runtime nằm trong `models/product_4class_fixed_triple_xgb/`.

```text
sequence length:       30
raw feature dim:       30
enriched feature dim:  90
tabular feature dim:   2161
final_xgb weight:      0.84
boost_xgb weight:      0.14
targeted_xgb weight:   0.02
bias_power:            0.42
temperature:           1.15
decision rule:         argmax_4class
class labels:          very_low, low, medium, high
```

Hàm chuẩn duy nhất để enrich dữ liệu:

```python
tracking.buffer.enrich_raw_sequence(raw_sequence)
```

Không tự viết một phép enrich khác trong server hoặc client.

`focus_score` trong UI/API là telemetry liên tục `P(medium) + P(high)`, dùng
cho signal và trend chart. Nó không phải threshold decision. Quyết định model
đến từ `prediction_4class = argmax(probabilities_4class)`.

## 4. Trách nhiệm từng vùng source

### Desktop

- `main.py`: entrypoint duy nhất.
- `ui/`: PyQt6 pages và components.
- `tracking/detector.py`: frame thành feature vector 30 chiều.
- `tracking/buffer.py`: sliding window và enrich chuẩn.
- `tracking/inference.py`: local fallback inference.
- `tracking/tracker.py`: camera worker, local/cloud/hybrid orchestration.
- `edge/cloud_client.py`: REST lifecycle và WebSocket transport.
- `ui/component_metrics.py`: normalize component telemetry cho UI, gồm cả
  fallback từ key legacy `gru/tcn/xgboost` sang `final_xgb/boost_xgb/targeted_xgb`.

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

## 6.1. Identity and auth

- Desktop có 2 cách đăng nhập: username/password và Google OAuth.
- Password được hash bằng PBKDF2-SHA256 trước khi lưu.
- Google login dùng installed-app OAuth, desktop nhận `id_token` rồi gửi lên
  server để xác minh và upsert user profile.
- User profile được lưu vào Firestore trong transaction, cùng các index
  username / Google subject để tránh trùng lặp.
- Login chỉ tạo danh tính người dùng; API key vẫn là lớp bảo vệ cho Cloud Run
  trong giai đoạn thesis.

## 7. Identity

FocusFlow dùng Google OAuth2 ở desktop chỉ để định danh người dùng, không phải
để thay thế `X-API-Key` của ứng dụng.

- Google sign-in là luồng installed-app / loopback redirect.
- `user_id` trong session có thể lấy từ Google subject hoặc email.
- Nếu login chưa sẵn sàng hoặc mạng lỗi, desktop vẫn có thể chạy local hoặc
  hybrid mà không cần identity hoàn chỉnh.
- Không dùng service-account key trên desktop.

## 8. Dữ liệu được và không được lưu

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

## 9. Nguyên tắc scale

- Cloud Run instance stateless.
- Firestore là durable session state.
- WebSocket mất kết nối phải reconnect.
- Queue desktop có giới hạn; bỏ sample cũ khi network chậm.
- Inference blocking chạy qua threadpool, không khóa asyncio.
- Model load một lần trong lifespan của mỗi Cloud Run instance.
- API là Cloud Run service duy nhất trong slice hiện tại.
- Chỉ tách inference service riêng sau khi benchmark chứng minh cần thiết.
