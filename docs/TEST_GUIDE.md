# Test Guide

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

## 2. Chạy toàn bộ automated tests

```bash
pytest -q
```

Kết quả mong đợi:

```text
all tests passed
```

Các test chính:

- `tests/test_logic_oonx.py`: golden output của model local.
- `tests/server/test_contracts.py`: tensor phải đúng `(30,30)`.
- `tests/server/test_cloud_inference.py`: cloud adapter chạy artifact thật.
- `tests/server/test_repository.py`: session lifecycle.
- `tests/server/test_api.py`: REST và WebSocket integration.
- `tests/server/test_edge_cloud_client.py`: URL transport.

## 3. Test model riêng

```bash
pytest -q tests/test_logic_oonx.py
```

Nếu fail:

1. Kiểm tra đủ file trong `models/late_fusion/`.
2. Kiểm tra metadata normalization GRU/TCN.
3. Không update golden number trước khi hiểu nguyên nhân thay đổi.
4. Nếu vừa export model mới, đọc lại `GUIDE.md`.

## 4. Test server riêng

```bash
pytest -q tests/server
```

Test server local dùng:

- memory repository;
- logging event publisher;
- model artifact thật.

Không cần credential GCP.

## 5. Chạy API local

Terminal 1:

```bash
source .venv/bin/activate
export FOCUSFLOW_ENV=development
export FOCUSFLOW_REPOSITORY=memory
export FOCUSFLOW_EVENT_BACKEND=logging
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Terminal 2:

```bash
curl http://127.0.0.1:8080/
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/readyz
```

Kết quả:

```json
{"status":"ok"}
{"status":"ok"}
{"status":"ready"}
```

Swagger UI:

```text
http://127.0.0.1:8080/docs
```

## 6. Test API key local

Khởi động server:

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

## 7. Test desktop local

```bash
python main.py
```

Trong Settings:

1. Chọn `Inference Mode = local`.
2. Save Settings.
3. Start Session.
4. Kiểm tra camera preview.
5. Chờ đủ 30 frames.
6. Kiểm tra GRU/TCN/XGBoost percentages.
7. Pause phải release camera.
8. Resume phải mở camera lại.
9. End phải tạo history record.

## 8. Test desktop với API local

Terminal server:

```bash
export FOCUSFLOW_API_KEY="test-secret"
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Terminal desktop:

```bash
export FOCUSFLOW_CLOUD_API_KEY="test-secret"
python main.py
```

Trong Settings:

```text
Inference Mode: hybrid
Cloud API URL:  http://127.0.0.1:8080
```

Kiểm tra:

- UI hiển thị cloud session created/connected;
- telemetry source chuyển sang `CLOUD`;
- tắt server giữa session;
- desktop tiếp tục bằng local fallback;
- bật server lại;
- WebSocket tự reconnect.

## 9. Build Docker API

```bash
docker build \
  -f deploy/gcp/Dockerfile.api \
  -t focusflow-api:local \
  .
```

Chạy:

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

## 10. Lỗi thường gặp

### Download reset khi Docker build

Dockerfile đã cấu hình pip timeout và retry. Chạy lại cùng command; Docker cache
giữ các layer đã xong.

### `FileNotFoundError` model

Kiểm tra:

```bash
ls -lh models/late_fusion/
```

Không đổi path artifact trong metadata để trỏ ra repo training.

### `401 Invalid API key`

Giá trị desktop `FOCUSFLOW_CLOUD_API_KEY` phải giống Secret Manager
`focusflow-api-key`.

### WebSocket disconnect sau một thời gian

Đây là hành vi bình thường trên Cloud Run vì request timeout. Kiểm tra log
reconnect thay vì coi session state nằm trong socket.

### Firestore permission denied

Service account API thiếu role `Cloud Datastore User`.

### Pub/Sub permission denied

Service account API thiếu role `Pub/Sub Publisher`.

### Legacy workflow config left behind

Nếu vẫn thấy lỗi liên quan tới report workflow cũ thì môi trường đang còn sót
cấu hình. Xoá các biến cũ khỏi shell hoặc Cloud Run rồi chạy lại API.
