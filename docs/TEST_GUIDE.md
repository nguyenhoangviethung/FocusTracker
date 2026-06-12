# Test Guide

Tài liệu này tập trung vào cách kiểm tra hai phần chính của dự án:

- **Client desktop**: PyQt6, camera preview, local/cloud/hybrid mode.
- **Server**: FastAPI, session lifecycle, inference API, WebSocket.

Nếu bạn chỉ muốn chạy demo nhanh, đi theo mục 5 và 6 trước.

## 1. Chuẩn bị môi trường

Từ root project:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
pip install -r requirements/server.txt
```

Kiểm tra Python:

```bash
python --version
```

Project hiện hướng tới Python 3.13.

## 2. Chạy automated tests

Chạy toàn bộ:

```bash
pytest -q
```

Các nhóm test chính:

- `tests/test_logic_oonx.py`: golden output của model local.
- `tests/server/test_contracts.py`: shape và validation contract.
- `tests/server/test_cloud_inference.py`: cloud adapter dùng artifact thật.
- `tests/server/test_repository.py`: session lifecycle.
- `tests/server/test_api.py`: REST và WebSocket integration.
- `tests/server/test_edge_cloud_client.py`: transport phía edge.
- `tests/demo/test_validate_videos.py`: video manifest cho demo.
- `tests/demo/test_metrics.py`: metric helper cho demo scale.

## 3. Test server local

Khởi động API local với memory repository:

```bash
source .venv/bin/activate
export FOCUSFLOW_ENV=development
export FOCUSFLOW_REPOSITORY=memory
export FOCUSFLOW_EVENT_BACKEND=logging
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Kiểm tra trong terminal khác:

```bash
curl http://127.0.0.1:8080/
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/readyz
```

Kết quả mong đợi:

```json
{"status":"ok"}
{"status":"ok"}
{"status":"ready"}
```

Swagger UI:

```text
http://127.0.0.1:8080/docs
```

Server dashboard:

```text
http://127.0.0.1:8080/dashboard
```

Dashboard này hiển thị:

- trạng thái ready;
- repository backend;
- số session gần nhất;
- session gần đây;
- status completed / active;
- device_id và user_id nếu có.

## 4. Test API key local

Khởi động server với key test:

```bash
export FOCUSFLOW_API_KEY="test-secret"
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Không có key phải trả `401`:

```bash
curl -i -X POST http://127.0.0.1:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"device_id":"manual-device","duration_seconds":60}'
```

Có key phải trả `201`:

```bash
curl -i -X POST http://127.0.0.1:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-secret" \
  -d '{"device_id":"manual-device","duration_seconds":60}'
```

## 5. Test client desktop local

Chạy app:

```bash
python main.py
```

Trong **Settings**:

1. Chọn `Inference Mode = local`.
2. Chọn camera source.
3. Save settings.
4. Start Session.

Kiểm tra giao diện:

- Home page hiển thị source đã chọn và inference mode.
- Active Session page hiện preview camera.
- Vision page hiện 3 component model và progress bars.
- Report page cho phép xem summary cuối phiên.

Kiểm tra hành vi:

1. Chờ đủ 30 frames.
2. Xem có số liệu GRU / TCN / XGBoost.
3. Pause phải release camera.
4. Resume phải mở camera lại.
5. End phải tạo history record.

Nếu test đăng nhập:

1. Mở app và đăng nhập bằng username/password hoặc Google.
2. Xác nhận chip user ở sidebar đã đổi từ `Not signed in`.
3. Kiểm tra `settings.json` có `auth_user_id`, `auth_provider`, và `auth_display_name`.
4. Kiểm tra session report có `user_id` nếu server trả về profile.
5. Nếu đăng nhập username/password, thử register một account mới rồi login lại.
6. Nếu đăng nhập Google, kiểm tra browser callback quay lại app và sidebar hiện email hoặc display name.

Nếu đã cấu hình Google login:

1. Bấm Sign in with Google ở màn đăng nhập.
2. Xác nhận `user_id` và email hiển thị trên header.
3. Đóng app, mở lại, kiểm tra session vẫn tạo được khi login thành công.
4. Trong Firestore, kiểm tra `focusflow_users`.

Firestore chỉ hiển thị collection sau lần ghi đầu tiên. Nếu Cloud Run trả
`404` cho `POST /v1/auth/google`, revision hiện tại chưa chứa code auth mới và
phải được build/deploy lại trước khi test đăng nhập cloud.

## 6. Test client + server local

Terminal server:

```bash
export FOCUSFLOW_API_KEY="test-secret"
export FOCUSFLOW_REPOSITORY=memory
export FOCUSFLOW_EVENT_BACKEND=logging
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Terminal client:

```bash
export FOCUSFLOW_CLOUD_API_KEY="test-secret"
python main.py
```

Trong **Settings**:

```text
Inference Mode: hybrid
Cloud API URL:  http://127.0.0.1:8080
```

Kiểm tra:

- UI hiển thị cloud session created/connected;
- telemetry source chuyển sang `CLOUD`;
- tắt server giữa session để xem hybrid fallback;
- bật server lại để kiểm tra reconnect;
- end session vẫn tạo summary cục bộ.

## 7. Test cloud video demo

Khi bạn muốn test luồng demo 100 video:

```bash
python -m demo.validate_videos --input demo/Data --limit 100 --output /tmp/focusflow-video-manifest.json
python -m demo.run_scale --manifest /tmp/focusflow-video-manifest.json
```

Nếu mạng chập chờn, dùng `--limit` nhỏ trước để xác nhận pipeline rồi mới
tăng số lượng.

## 8. Test Docker API

Build image:

```bash
docker build \
  -f deploy/gcp/Dockerfile.api \
  -t focusflow-api:local \
  .
```

Chạy container:

```bash
docker run --rm -p 8080:8080 \
  -e FOCUSFLOW_ENV=development \
  -e FOCUSFLOW_REPOSITORY=memory \
  -e FOCUSFLOW_EVENT_BACKEND=logging \
  focusflow-api:local
```

Kiểm tra:

```bash
curl http://127.0.0.1:8080/readyz
```

## 9. Kiểm tra giao diện public download portal

Nếu đã deploy bucket public:

1. Mở landing page static site.
2. Bấm từng nút tải theo OS.
3. Kiểm tra file tải về đúng tên.
4. Kiểm tra link `404.html` nếu thử đường dẫn sai.

## 10. Lỗi thường gặp

### `FileNotFoundError` model

Kiểm tra:

```bash
ls -lh models/late_fusion/
```

### `401 Invalid API key`

Giá trị `FOCUSFLOW_CLOUD_API_KEY` của desktop phải khớp với Secret Manager
`focusflow-api-key`.

### WebSocket disconnect sau một thời gian

Đây là hành vi bình thường trên Cloud Run vì request timeout. Desktop phải
reconnect.

### Firestore permission denied

Service account API thiếu role `Cloud Datastore User`.

### Pub/Sub permission denied

Service account API thiếu role `Pub/Sub Publisher`.

### Cloud source không xuất hiện

Kiểm tra:

1. Chờ đủ 30 frames.
2. `/readyz` của API.
3. API key.
4. URL phải bắt đầu bằng `https://` khi chạy cloud thật.

## 11. Checklist nhanh trước demo

```text
[ ] Webcam hoạt động
[ ] `python main.py` mở được UI
[ ] `pytest -q` pass
[ ] `curl /readyz` trả ready
[ ] Local mode pass
[ ] Hybrid mode pass
[ ] Public download portal mở được
[ ] Demo video folder đầy đủ
```
