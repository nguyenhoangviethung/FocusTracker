# FocusFlow AI: hướng dẫn phản biện luận văn

Tài liệu này chỉ mô tả kiến trúc đang chạy. Bộ UML chính thức nằm trong
[`docs/uml`](uml/README.md).

## 1. Phần nghiên cứu

Mô hình triển khai là Fixed Triple-XGBoost gồm `final_xgb`, `boost_xgb` và
`targeted_xgb`. Ba vector xác suất bốn lớp được hợp nhất với trọng số
`0.84/0.14/0.02`, sau đó áp dụng class bias và temperature calibration.

Các chỉ số của artifact tái lập:

- Accuracy: 76.01%;
- Balanced Accuracy: 79.98%;
- Macro-F1: 77.34%;
- model-side CPU latency trung bình: 11.42 ms.

Đóng góp chính nằm ở preprocessing: 30 đặc trưng mỗi frame, làm giàu thành 90
đặc trưng mỗi timestep và tổng hợp 2161 thống kê cho XGBoost. Đây không phải
một thuật toán boosting mới.

### Câu hỏi thường gặp

**Vì sao huấn luyện bốn lớp nhưng giao diện hiển thị focus score?**

Quyết định model vẫn là `argmax` trên bốn lớp. `focus_score = P(medium) +
P(high)` chỉ là telemetry liên tục cho đồ thị và summary, không thay thế quyết
định bốn lớp bằng threshold nhị phân.

**Dữ liệu khuôn mặt khác nhau được xử lý thế nào?**

EAR/MAR dùng tỷ lệ hình học; chuỗi có sai phân và độ lệch chuẩn để giữ chuyển
động tương đối. Các biện pháp này giảm nhưng không loại bỏ domain shift. Hiệu
chuẩn theo người dùng là hướng phát triển, chưa phải chức năng hiện tại.

## 2. Phần ứng dụng

Hệ thống có kiến trúc edge-to-cloud:

- edge giữ ảnh webcam, chạy MediaPipe và gửi chuỗi `(30,30)`;
- Cloud Run xác thực, làm giàu `(30,90)` và chạy Triple-XGBoost;
- Firestore lưu user/session snapshot và summary;
- Pub/Sub nhận sự kiện `session.completed`.

### Câu hỏi thường gặp

**Hệ thống có gửi video lên cloud không?**

Không. Chỉ chuỗi đặc trưng số được gửi. Tuy vậy, đây vẫn là dữ liệu suy ra từ
sinh trắc học và phải được bảo vệ bằng TLS, kiểm soát truy cập và retention.

**Khi mất mạng hệ thống có suy luận local không?**

Không ở phiên bản hiện tại. Client báo `reconnecting`, giữ queue bounded và thử
lại bằng exponential backoff với jitter. Không được tuyên bố có hybrid fallback
ONNX khi code chưa triển khai chức năng đó.

**Tải mạng có phải 30 request/giây không?**

Không. Camera có thể xử lý nhiều frame mỗi giây để cập nhật cửa sổ, nhưng
`CLOUD_TELEMETRY_INTERVAL_SECONDS=1.0` giới hạn gửi telemetry tối đa 1 Hz.

**Vì sao API và inference nằm cùng Cloud Run service?**

Quy mô luận văn chưa chứng minh model là bottleneck cần tách service. Một service
giảm network hop và đơn giản vận hành. Chỉ tách sau khi load test chỉ ra nhu cầu
scale độc lập.

**API key có đủ cho production không?**

API key phù hợp lớp bảo vệ ứng dụng trong demo nhưng không thay thế danh tính
người dùng và authorization đầy đủ. Hướng phát triển là token ngắn hạn và IAM
phân quyền theo tenant.

## 3. Bộ sơ đồ nên đưa vào luận văn

1. Use-case diagram cho người học, giám sát và quản trị viên.
2. Component diagram thể hiện dependency boundary.
3. Deployment diagram cho edge, Cloud Run, Firestore và Pub/Sub.
4. Sequence diagram cho một vòng inference WebSocket.
5. State machine cho vòng đời phiên desktop.
6. Domain model cho user, session, telemetry và response.

Không cần đưa cả sáu sơ đồ vào phần thân nếu giới hạn trang. Component,
deployment và sequence là ba hình quan trọng nhất; use case và domain model có
thể chuyển xuống phụ lục.
