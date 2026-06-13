# Test Guide

Tài liệu này tập trung vào cách kiểm tra hai phần chính của dự án:

- **Client desktop**: PyQt6, camera preview, local/cloud/hybrid mode.
- **Server**: FastAPI, session lifecycle, inference API, WebSocket.

Nếu bạn chỉ muốn chạy demo nhanh, đi theo mục 5 và 6 trước.

## 0. Bản đồ module có thể test local

### Test local ngay

| Module | Cách test local | Ghi chú |
| --- | --- | --- |
| `shared/contracts.py` | `pytest -q tests/server/test_contracts.py` | Validate schema, shape, protocol. |
| `shared/identifiers.py` | `pytest -q tests/server/test_identifiers.py` | Kiểm tra ID readable và deterministic. |
| `tracking/buffer.py` | `pytest -q tests/test_logic_oonx.py` và test model liên quan | Không cần GCP. |
| `tracking/inference.py` | `pytest -q tests/test_logic_oonx.py` | Golden local model. |
| `server/repositories/sessions.py` | `pytest -q tests/server/test_repository.py` | Chạy memory repository local. |
| `server/repositories/users.py` | `pytest -q tests/server/test_user_repository.py` | Chạy memory repository local. |
| `server/services/auth_service.py` | `pytest -q tests/server/test_auth.py` | Mock Google token để test nhánh auth. |
| `server/api/routes.py` | `pytest -q tests/server/test_api.py tests/server/test_dashboard.py` | REST, WebSocket, dashboard. |
| `edge/cloud_client.py` | `pytest -q tests/server/test_edge_cloud_client.py` | Client transport local. |
| `edge/auth_client.py` | manual bằng `python main.py` | Thử login và callback local. |
| `ui/*` | `python main.py` | Test UI desktop trực tiếp. |
| `demo/validate_videos.py` | `python -m demo.validate_videos ...` | Chỉ cần file video local. |
| `demo/seed_users.py` | `python -m demo.seed_users ...` | Seed 100 user docs vào Firestore. |
| `demo/extract_features.py` | `python -m demo.extract_features ...` | Tạo fixture local. |
| `demo/run_video_clients.py` | `python -m demo.run_video_clients ...` | Replay video local tới API local/cloud. |
| `demo/run_scale.py` | `python -m demo.run_scale ...` | Chạy local against API local/cloud. |

### Không nên test local “thật”

| Module / phần | Cách thay thế local | Ghi chú |
| --- | --- | --- |
| `deploy/gcp/*` Cloud Build / Cloud Run | dùng `docker build` + `uvicorn` local | Config thật thì lên GCP Console. |
| Firestore production | memory repository hoặc Firestore thật trên GCP | Logic có thể test local bằng memory backend. |
| Pub/Sub production | logging backend local | Khi cần verify thật thì dùng Cloud Run logs / Pub/Sub metrics. |
| Cloud Run autoscaling | dashboard/benchmark local chỉ mô phỏng | Kết quả scale thật phải nhìn trên GCP. |

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

Nếu máy yếu, chỉ mở dashboard trong lúc test nhỏ. Với demo 100 client, nên
chạy dashboard trên Cloud Run thay vì local.

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

### Chạy 100 client trên GCP, không dùng máy local

Nếu mục tiêu là không để laptop xử lý tải, hãy chạy load generator từ **Google
Cloud Shell** hoặc một **GCE VM** nhỏ. Khi đó máy của bạn chỉ mở dashboard và
quan sát, còn 100 client ảo chạy trong môi trường GCP.

#### Cách 1: Cloud Shell

1. Mở Cloud Shell trong Google Cloud Console.
2. Clone repo hoặc mở workspace đã có code.
3. Kéo `.env` hoặc export trực tiếp các biến cần thiết:

```bash
export FOCUSFLOW_CLOUD_API_URL=https://YOUR_API_URL
export FOCUSFLOW_CLOUD_API_KEY=<your-cloud-api-key>
```

4. Nếu đã có feature fixtures, chạy:

```bash
python -m demo.run_scale \
  --manifest /tmp/focusflow-video-manifest.json \
  --features demo/features \
  --api-url "$FOCUSFLOW_CLOUD_API_URL" \
  --api-key "$FOCUSFLOW_CLOUD_API_KEY"
```

5. Nếu chưa có `demo/features`, tạo chúng trước trên Cloud Shell hoặc copy từ
   một lần chạy feature extraction khác.

#### Cách 2: GCE VM nhỏ

1. Tạo một VM nhỏ ở `asia-southeast1`.
2. Cài Python và dependencies.
3. Chạy đúng lệnh `demo.run_scale` như trên.

#### Lưu ý quan trọng

- Laptop của bạn không còn là máy phát tải nữa.
- Dashboard nên mở trên Cloud Run.
- Nếu dùng Cloud Shell, nhớ giữ tab còn mở cho tới khi benchmark xong.
- Nếu muốn an toàn hơn nữa, hãy dùng VM thay vì Cloud Shell.

Nếu bạn chỉ muốn kiểm tra phần local trước khi lên cloud:

1. Chạy `python -m demo.validate_videos --input demo/Data --limit 10`.
2. Chạy `python -m demo.extract_features --manifest /tmp/focusflow-video-manifest.json --output demo/features`.
3. Chạy `python -m demo.run_video_clients --input demo/Data --limit 5 --concurrency 2`.
4. Chỉ khi ba bước này ổn mới nâng lên 100.

Khi demo, bạn có thể nói ngắn gọn như sau:

- 100 video mẫu tương ứng 100 user/session ảo.
- Mỗi client ảo là một `device_id` riêng và một luồng session riêng.
- Server dashboard hiển thị preview trạng thái và có thể mở đủ 100 ô qua API summary.
- Mình chỉ quan sát số liệu: `device_id`, `fps`, `latency`, `state`, `face_found`,
  và trạng thái hoàn tất session.

Nếu muốn demo có tính “thấy được”, mở song song:

1. `https://YOUR_API_URL/dashboard` trên Cloud Run.
2. Terminal chạy `demo.run_scale`.
3. Bảng summary kết quả trong `demo/results`.

Như vậy người nghe sẽ thấy rõ đây là demo về:

- scale của session API;
- 100 client cùng lúc;
- dashboard quan sát số liệu trên cloud;
- không có raw video truyền lên server.

## 7.1. Seed 100 user thật vào Firestore rồi bắn session có `user_id`

Nếu bạn muốn Firestore có cả `focusflow_users` lẫn `focusflow_sessions`, hãy
seed user trước rồi mới bắn load:

```bash
python -m demo.seed_users \
  --project-id my-thesis-496702 \
  --count 100 \
  --output /tmp/focusflow-user-manifest.json
```

Lệnh này sẽ:

- tạo 100 document trong `focusflow_users`;
- ghi manifest user để load generator đọc lại;
- sinh `user_id` readable, không random rác.

Chạy lệnh này trong Cloud Shell hoặc trên GCE VM có quyền Firestore/ADC. Nếu
chạy trên máy local, nhớ có Application Default Credentials hợp lệ.

Sau đó bắn 100 session có `user_id`:

```bash
python -m demo.run_scale \
  --api-url https://YOUR_API_URL \
  --api-key YOUR_CLOUD_API_KEY \
  --manifest /tmp/focusflow-video-manifest.json \
  --users-manifest /tmp/focusflow-user-manifest.json
```

Kết quả mong đợi:

- Firestore có `focusflow_users` tăng lên 100 document;
- `focusflow_sessions` có `user_id` đi kèm từng session;
- dashboard cloud hiển thị user/session mapping rõ hơn;
- bạn có thể chứng minh “100 người” mà không phải login 100 lần.

## 8. Checklist test local theo thứ tự

Nếu muốn sàng lọc nhanh toàn bộ module mà không đụng GCP trước, đi theo thứ tự này:

1. `pytest -q tests/server/test_contracts.py tests/server/test_identifiers.py`
2. `pytest -q tests/server/test_user_repository.py tests/server/test_repository.py`
3. `pytest -q tests/server/test_auth.py tests/server/test_api.py tests/server/test_dashboard.py`
4. `pytest -q tests/server/test_edge_cloud_client.py`
5. `python main.py`
6. `python -m demo.validate_videos --input demo/Data --limit 10`
7. `python -m demo.extract_features --manifest /tmp/focusflow-video-manifest.json --output demo/features`
8. `python -m demo.run_video_clients --input demo/Data --limit 5 --concurrency 2`
9. `python -m demo.seed_users --project-id my-thesis-496702 --count 100 --output /tmp/focusflow-user-manifest.json`
10. `python -m demo.run_scale --manifest /tmp/focusflow-video-manifest.json --users-manifest /tmp/focusflow-user-manifest.json --api-url http://127.0.0.1:8080 --api-key test-secret`

Sau khi local pass, mới chuyển sang:

1. Cloud Run dashboard.
2. Firestore thật.
3. Pub/Sub thật.
4. Cloud scale replay 100 client.

## 9. Test Docker API

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

## 10. Kiểm tra giao diện public download portal

Nếu đã deploy bucket public:

1. Mở landing page static site.
2. Bấm từng nút tải theo OS.
3. Kiểm tra file tải về đúng tên.
4. Kiểm tra link `404.html` nếu thử đường dẫn sai.

## 11. Lỗi thường gặp

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
