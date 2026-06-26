# Architecture Guide

## 1. Mục tiêu hệ thống

FocusFlow AI là hệ thống edge-to-cloud chỉ dùng tín hiệu thị giác:

- Desktop đọc webcam và chạy MediaPipe.
- Desktop không gửi ảnh hoặc video lên cloud.
- Desktop gửi chuỗi đặc trưng khuôn mặt `(30, 168)` theo schema `depth_robust_v2`.
- Cloud enrich thành `(30, 504)` bằng raw + velocity + std.
- Cloud chạy model 4-class DeepForest đã calibration.
- Firestore lưu lifecycle và summary của session.
- Report completion chỉ ghi trạng thái tổng kết, không còn AI coach hay email mentor.

Hệ thống không còn OS tracking, keyword heuristic, theo dõi bàn phím/chuột hoặc
Hardcore Mode.

## 2. Luồng dữ liệu

```text
Webcam frame
  -> MediaPipe Face Landmarker
  -> 168 raw facial features (geometry, canonical depth landmarks, blendshapes, transform)
  -> sliding window 30 frames
  -> raw sequence (30, 168)
  -> WebSocket TLS
  -> Cloud Run API
  -> enrich raw + velocity + std
  -> enriched sequence (30, 504)
  -> basic aggregate values (3529)
  -> layer1 ExtraTrees + layer1 RandomForest + layer2 cascade
  -> class-logit bias + temperature calibration
  -> argmax over 4 calibrated class probabilities
  -> class 2/3 = FOCUSED, class 0/1 = DISTRACTED
```

Khi không tìm thấy mặt, face-presence guard trả `NO_FACE` và không tin model
score.

## 3. Contract của model

Artifact runtime nằm trong `models/deep_forest_product_4class/`.

```text
sequence length:       30
raw feature dim:       168
enriched feature dim:  504
tabular feature dim:   3529
components:            layer1 ExtraTrees + RandomForest, layer2 cascade
temperature:           1.25
class biases:          [1.5, 2.5, 0.0, 0.5]
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
- `tracking/detector.py`: frame thành feature vector depth-robust 168 chiều.
- `tracking/buffer.py`: sliding window và enrich chuẩn.
- `tracking/inference.py`: calibrated DeepForest adapter dùng bởi cloud inference.
- `tracking/tracker.py`: camera worker và cloud-only orchestration.
- `edge/cloud_client.py`: REST lifecycle và WebSocket transport.
- `ui/component_metrics.py`: normalize component telemetry `layer1_extra_trees`,
  `layer1_random_forest`, và `layer2_cascade` cho UI.

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

## 5. Inference runtime

Production sử dụng một luồng `cloud-only`:

- Desktop xử lý frame và trích xuất vector 168 chiều tại edge.
- Desktop gửi cửa sổ đặc trưng qua WebSocket, không gửi ảnh hoặc video.
- Cloud enrich chuỗi thành 504 đặc trưng mỗi frame và chạy calibrated
  DeepForest.
- Khi mất kết nối, desktop báo `Reconnecting` và retry bằng backoff; không sinh
  dự đoán local giả.
- Runtime production dùng `DeepForestInferencer`; các script binary legacy là
  công cụ thí nghiệm riêng, không tham gia pipeline production.

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
- Khi login hoặc mạng chưa sẵn sàng, desktop không bắt đầu suy luận; UI phải
  hiển thị lỗi kết nối/xác thực rõ ràng để người dùng thử lại.
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
