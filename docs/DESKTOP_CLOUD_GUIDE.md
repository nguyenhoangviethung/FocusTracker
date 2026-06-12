# Desktop Cloud Guide

## 1. Cấu hình inference mode

Mở app:

```bash
python main.py
```

Vào Settings.

### Local development

```text
Inference Mode: local
Cloud API URL:  để trống
```

### Cloud production

```text
Inference Mode: cloud
Cloud API URL:  https://YOUR_API_URL
```

### Thesis demo

```text
Inference Mode: hybrid
Cloud API URL:  https://YOUR_API_URL
```

Khuyến nghị dùng `hybrid` khi bảo vệ luận văn.

## 2. Cấu hình API key

Linux/macOS:

```bash
export FOCUSFLOW_CLOUD_API_KEY="<secret>"
python main.py
```

Windows PowerShell:

```powershell
$env:FOCUSFLOW_CLOUD_API_KEY="<secret>"
python main.py
```

API key không được lưu trong `settings.json`.

## 2.1. Cấu hình Google sign-in

Google login chỉ dùng để định danh user, không thay thế API key của Cloud Run.
Username/password login cũng chỉ dùng để định danh và vẫn cần API key app.

Trong `.env` local:

```text
FOCUSFLOW_GOOGLE_OAUTH_CLIENT_ID=1093941638042-h6b0ogrnj6jhe959usdqnjqbh6hlrg92.apps.googleusercontent.com
FOCUSFLOW_GOOGLE_OAUTH_SECRET=<copy from Google Cloud OAuth client>
FOCUSFLOW_GOOGLE_OAUTH_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FOCUSFLOW_GOOGLE_OAUTH_TOKEN_URI=https://oauth2.googleapis.com/token
FOCUSFLOW_GOOGLE_OAUTH_REDIRECT_URIS=http://localhost
FOCUSFLOW_GOOGLE_OAUTH_SCOPES="openid https://www.googleapis.com/auth/userinfo.email"
```

Sau khi đăng nhập:

- `user_id` của session lấy từ Google subject hoặc email;
- user chip hiển thị trên desktop;
- nếu login fail, vẫn có thể chạy `local` hoặc `hybrid`.

## 3. Luồng UI khi chạy cloud

Sau Start Session:

1. Network thread tạo cloud session.
2. UI có thể hiện `session_created`.
3. WebSocket connect.
4. Camera tích lũy 30 frames.
5. Sequence gửi lên cloud.
6. UI source chuyển thành `CLOUD`.
7. Component card hiển thị GRU/TCN/XGBoost.
8. Header hiển thị Google account đã đăng nhập.

## 4. Server dashboard

Khi bạn muốn xem server có đang nhận session hay không, mở dashboard web:

```text
http://127.0.0.1:8080/dashboard
```

Nếu đã deploy lên Cloud Run:

```text
https://YOUR_API_URL/dashboard
```

Dashboard hiển thị:

- trạng thái ready;
- repository backend;
- số session gần nhất;
- active/completed count;
- session gần đây;
- device_id và user_id;
- report status.

Nếu network lỗi:

- UI hiện `reconnecting`;
- network thread dùng exponential backoff;
- `hybrid` tiếp tục dùng local model;
- sample queue chỉ giữ dữ liệu mới, không tăng RAM vô hạn.

## 5. Pause và Resume

Pause:

- release camera;
- clear sequence buffer;
- reset local model smoothing;
- không ghi thêm second sample.

Resume:

- mở camera lại;
- thu lại đủ 30 frames;
- tiếp tục cloud session hiện tại nếu socket reconnect được.

## 6. End Session

Khi End:

1. Desktop tạo summary.
2. Desktop gọi cloud completion ở background.
3. Cloud lưu summary.
4. Cloud ghi report completion metadata.
5. Desktop chỉ cập nhật local history.

Nếu cloud session chưa từng tạo được, local/hybrid vẫn chỉ hoàn tất summary và
report metadata trên desktop.

## 7. Demo checklist

Trước buổi bảo vệ:

```text
[ ] Webcam hoạt động
[ ] Model artifacts đầy đủ
[ ] FOCUSFLOW_CLOUD_API_KEY đã export
[ ] Cloud API /readyz trả ready
[ ] Settings đang ở hybrid
[ ] Demo video backup đã chuẩn bị
[ ] Local mode đã test
[ ] Firestore Console đang mở
[ ] Cloud Run Logs đang mở
```

Kịch bản demo:

1. Start session.
2. Cho thấy raw video chỉ hiển thị local.
3. Cho thấy ba component model.
4. Mở Cloud Run Logs để chứng minh inference cloud.
5. Tắt network ngắn để chứng minh hybrid fallback.
6. Bật network để chứng minh reconnect.
7. End Session.
8. Mở Firestore summary.
9. Mở report completion metadata trong Firestore/report.

## 8. Troubleshooting

### Cloud status disabled

Thiếu một trong:

- Cloud API URL;
- `FOCUSFLOW_CLOUD_API_KEY`;
- device ID.

Device ID tự sinh khi settings được normalize.

### Cloud source không xuất hiện

Kiểm tra:

1. Chờ đủ 30 frames.
2. `/readyz` của API.
3. Cloud Run Logs.
4. API key.
5. URL phải bắt đầu bằng `https://`.

### Local mode chạy nhưng cloud fail

Khả năng cao là:

- service chưa ready;
- API key sai;
- WebSocket bị proxy/firewall chặn;
- model cloud thiếu artifact;
- Cloud Run instance thiếu memory.

### History có report completed nhưng Firestore chưa thấy metadata

Kiểm tra theo thứ tự:

1. Cloud Run API logs.
2. Firestore update quyền của service account.
3. Local app history file.
