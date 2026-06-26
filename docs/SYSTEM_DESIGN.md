# FocusFlow AI: Đặc tả thiết kế hệ thống

Tài liệu này mô tả kiến trúc đang được triển khai của FocusFlow AI. Sơ đồ có
thể chỉnh sửa và bản PDF dùng cho luận văn nằm tại [`docs/uml`](uml/README.md).

## 1. Mục tiêu thiết kế

Hệ thống cần nhận diện bốn mức engagement từ webcam, phản hồi gần thời gian
thực trên CPU và không truyền ảnh khuôn mặt ra khỏi thiết bị. Kiến trúc được
tách thành hai biên triển khai:

- **Edge desktop:** giao diện PyQt6, OpenCV, MediaPipe, bộ đệm 30 khung hình và
  client REST/WebSocket.
- **Cloud backend:** FastAPI trên Cloud Run, calibrated DeepForest, Firestore và
  Pub/Sub.

Thiết kế hiện tại là **cloud-only inference**. Khi mất mạng, client hiển thị
trạng thái kết nối lại và không sinh dự đoán cục bộ giả. Các artifact ONNX trong
repo là legacy và không thuộc luồng production.

## 2. Các quyết định kiến trúc

| Quyết định | Lý do |
| --- | --- |
| Trích xuất đặc trưng tại edge | Giảm dữ liệu truyền và giữ ảnh ở thiết bị |
| Hợp nhất API và inference trong một Cloud Run service | Giảm network hop và đơn giản hóa demo |
| Dùng contract Pydantic dùng chung | Tránh lệch schema giữa desktop và server |
| Repository pattern cho Firestore | Cho phép test bằng in-memory adapter |
| Hàng đợi bounded, latest-value | Không để UI/network bị backlog vô hạn |
| Chỉ lưu live snapshot và summary | Tránh chi phí ghi Firestore ở tần suất camera |
| Argmax bốn lớp | Khớp artifact được huấn luyện; không dùng threshold nhị phân |

## 3. Tác nhân và use case

Ba tác nhân của hệ thống là người học, người giám sát và quản trị viên. Người
học đăng nhập, cấu hình, bắt đầu, tạm dừng, kết thúc phiên và xem báo cáo. Người
giám sát xem dashboard tổng hợp; quản trị viên quản lý phiên và quan sát trạng
thái hệ thống. Chi tiết thể hiện trong
[`01_use_case.mmd`](uml/01_use_case.mmd).

## 4. Cấu trúc thành phần

Kiến trúc áp dụng phân lớp nhẹ:

1. **Presentation/transport:** PyQt6 và FastAPI routes.
2. **Application:** tracker orchestration, cloud inference engine, repository
   ports và event publisher port.
3. **Domain/model:** contract, biến đổi đặc trưng và DeepForest.
4. **Infrastructure:** OpenCV/MediaPipe, HTTP/WebSocket, Firestore, Pub/Sub và
   local storage.

UI không truy cập Firestore và model trực tiếp. Edge chỉ giao tiếp với cloud qua
`shared/contracts.py`. Component diagram nằm tại
[`02_component.mmd`](uml/02_component.mmd).

## 5. Luồng suy luận

Mỗi frame được MediaPipe chuyển thành vector `depth_robust_v2` 168 chiều. Bộ
đệm tạo chuỗi `(30,168)`; tracker gửi tối đa một gói mỗi giây qua WebSocket.
Server kiểm tra API key, phiên, thứ tự gói và shape, sau đó làm giàu thành
`(30,504)`. Model adapter tạo vector thống kê basic 3529 chiều, chạy cascade
ExtraTrees + RandomForest hai tầng, rồi áp dụng temperature `1.25` và class
logit bias `[1.5, 2.5, 0.0, 0.5]` trước argmax bốn lớp.
`focus_score` chỉ phục vụ đồ thị và thống kê. Sequence diagram nằm tại
[`04_inference_sequence.mmd`](uml/04_inference_sequence.mmd).

## 6. Vòng đời phiên

Client chuyển qua các trạng thái `Idle`, `Starting`, `WarmingUp`, `Connecting`,
`TrackingCloud`, `Reconnecting`, `Paused`, `Completing`, `Report` và `Error`.
Không có trạng thái `TrackingLocal` trong phiên bản hiện tại. Chi tiết nằm tại
[`05_session_state.mmd`](uml/05_session_state.mmd).

## 7. API và protocol v1

| Method | Endpoint | Trách nhiệm |
| --- | --- | --- |
| `POST` | `/v1/sessions` | Tạo phiên |
| `GET` | `/v1/sessions/{id}` | Đọc trạng thái phiên |
| `POST` | `/v1/sessions/{id}/complete` | Hoàn tất idempotent và phát sự kiện |
| `WS` | `/v1/ws/sessions/{id}` | Telemetry và inference gần thời gian thực |
| `POST` | `/v1/inference` | Suy luận đồng bộ không trạng thái |
| `GET` | `/healthz`, `/readyz` | Liveness và readiness |

`TelemetryPacket.raw_feature_sequence` phải có shape `(30,168)`. Mỗi phản hồi
giữ nguyên `message_id` để client tương quan request/response. Ảnh, landmark
đầy đủ, tiêu đề cửa sổ và hoạt động bàn phím/chuột không thuộc protocol.

## 8. Dữ liệu

`focusflow_users` chứa cả tài khoản password và Google. `focusflow_sessions`
chứa metadata vòng đời, live snapshot giới hạn và summary cuối phiên. Quan hệ
giữa contract và entity được mô tả tại
[`06_domain_model.mmd`](uml/06_domain_model.mmd).

## 9. Thuộc tính chất lượng

- **Privacy:** ảnh chỉ tồn tại trong bộ nhớ edge; feature telemetry vẫn là dữ
  liệu suy ra từ sinh trắc học và phải có TLS, retention policy và consent.
- **Availability:** reconnect có exponential backoff và jitter.
- **Scalability:** Cloud Run stateless, model load một lần mỗi instance.
- **Testability:** repository và event publisher có in-memory adapter.
- **Consistency:** một hàm canonical `enrich_raw_sequence()` cho local tests và
  cloud inference.
- **Observability:** phân biệt client-loop, model-inference và cloud-roundtrip
  latency.

## 10. Giới hạn hiện tại

- Chưa có suy luận local khi mất mạng.
- Raw-video end-to-end phải được benchmark theo `docs/EVALUATION_PROTOCOL.md`;
  không dùng model-side latency thay thế trải nghiệm người dùng.
- Chưa có generalization study subject-disjoint ngoài DAiSEE.
- API key là xác thực ứng dụng cho giai đoạn luận văn, chưa thay thế hệ thống
  identity production hoàn chỉnh.
- Dashboard là công cụ giám sát demo, không phải LMS đa tenant hoàn chỉnh.
