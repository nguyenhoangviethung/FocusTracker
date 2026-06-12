# Auth Guide

Tài liệu này ghi lại phần đăng nhập Google cho desktop client FocusFlow AI.
Mục tiêu là định danh người dùng trước khi tạo session, không thay thế API key
được dùng để gọi Cloud Run.

Hiện client hỗ trợ 2 cách:

1. Username/password đơn giản, hash bằng PBKDF2-SHA256 và lưu Firestore bằng
   transaction.
2. Google OAuth desktop login, dùng các biến env OAuth và flow loopback desktop
   chuẩn để nhận `id_token`, rồi gửi token lên server để xác minh và upsert
   user profile.

## 1. Desktop OAuth config

Desktop dùng các biến môi trường OAuth sau. Đây là cấu hình chuẩn để bạn
không cần giữ file JSON trong repo:

```text
client id:   1093941638042-h6b0ogrnj6jhe959usdqnjqbh6hlrg92.apps.googleusercontent.com
project:     my-thesis-496702
type:        installed application
redirect:    http://localhost
scopes:      openid, email
```

## 2. Biến môi trường local

```text
FOCUSFLOW_GOOGLE_OAUTH_CLIENT_ID=1093941638042-h6b0ogrnj6jhe959usdqnjqbh6hlrg92.apps.googleusercontent.com
FOCUSFLOW_GOOGLE_OAUTH_SECRET=<from Google Cloud OAuth client>
FOCUSFLOW_GOOGLE_OAUTH_AUTH_URI=https://accounts.google.com/o/oauth2/auth
FOCUSFLOW_GOOGLE_OAUTH_TOKEN_URI=https://oauth2.googleapis.com/token
FOCUSFLOW_GOOGLE_OAUTH_REDIRECT_URIS=http://localhost
FOCUSFLOW_GOOGLE_OAUTH_SCOPES="openid https://www.googleapis.com/auth/userinfo.email"
```

## 3. Cách dùng trong app

- Google login chỉ dùng để gắn `user_id` cho session và report.
- Username/password cũng chỉ dùng để gắn danh tính, không thay thế app API key.
- Cloud Run vẫn được gọi bằng `X-API-Key`.
- Raw video vẫn không được gửi lên cloud.
- Nếu login fail, desktop vẫn có thể chạy offline hoặc hybrid theo cấu hình.

## 4. Firestore collections

Cloud Run tạo collection khi có lần ghi đầu tiên; Firestore không hiển thị
collection rỗng. Sau một lần Google login thành công trên revision có auth,
Console sẽ có:

```text
focusflow_users/{user_id}
focusflow_google_identities/{google_subject}
```

Username/password tạo:

```text
focusflow_users/{user_id}
focusflow_usernames/{username}
```

Document mới dùng ID dễ đọc và ổn định:

```text
focusflow_users/user_google_student@example.edu
focusflow_google_identities/google_subject_113326427935116102578
focusflow_users/user_password_student01
focusflow_usernames/username_student01
```

Email, username và Google subject đã nằm trong hồ sơ định danh Firestore; không
được đưa các đường dẫn này vào log public hoặc public download bucket.

Nếu chỉ thấy `focusflow_sessions`, kiểm tra endpoint auth của revision:

```bash
curl -i -X POST "$FOCUSFLOW_CLOUD_API_URL/v1/auth/google" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $FOCUSFLOW_CLOUD_API_KEY" \
  -d '{"id_token":"check"}'
```

- `404`: Cloud Run vẫn đang chạy image cũ, cần build/deploy commit mới.
- `401 Invalid Google token`: route auth đã tồn tại và OAuth config đã được đọc.
- `503`: route tồn tại nhưng thiếu `FOCUSFLOW_GOOGLE_OAUTH_CLIENT_ID`.
