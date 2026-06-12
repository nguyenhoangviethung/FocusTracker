# FocusFlow AI

FocusFlow AI là hệ thống edge-to-cloud theo dõi mức độ tập trung bằng webcam,
MediaPipe và ensemble GRU + TCN + XGBoost.

## Tài liệu

- `docs/ARCHITECTURE_GUIDE.md`
- `docs/TEST_GUIDE.md`
- `docs/GCP_DEPLOY_GUIDE.md`
- `docs/DESKTOP_CLOUD_GUIDE.md`
- `docs/AUTH_GUIDE.md`
- `deploy/gcp/static-site/`: landing page public cho tải app theo hệ điều hành.

Mẫu biến môi trường nằm ở [`.env.example`](/home/bear/Documents/Workspace/Thesis20252/FocusTracker/.env.example).

## Thành phần chính

- `main.py`: điểm vào duy nhất của ứng dụng.
- `ui/`: giao diện desktop PyQt6.
- `tracking/`: trích xuất đặc trưng, buffer 30 frame và local fallback inference.
- `edge/`: REST/WebSocket client cho Cloud Run.
- `shared/`: Pydantic contracts dùng chung.
- `server/`: FastAPI gateway, cloud inference và persistence adapters.
- `deploy/gcp/`: Docker, Cloud Build và hướng dẫn Google Cloud Console.
- `models/late_fusion/engagement_gru.onnx`: artifact GRU cho ensemble late-fusion.
- `models/late_fusion/engagement_tcn.onnx`: artifact TCN cho ensemble late-fusion.
- `models/late_fusion/engagement_xgb.json`: artifact XGBoost cho ensemble late-fusion.
- `models/late_fusion/late_fusion_gru_tcn_xgb_report.json`: report chọn ensemble.
- `models/face_landmarker.task`: model MediaPipe FaceMesh.
- `GUIDE.md`: guide production inference được kéo từ `../engagement-cpu/checkpoints/reports/GUIDE.md` để bảo trì model ngay trong repo app.

## Chạy app

```bash
pip install -r requirements.txt
python main.py
```

Cloud/hybrid mode đọc API key từ:

```bash
export FOCUSFLOW_CLOUD_API_KEY="..."
python main.py
```

## Chạy cloud API local

```bash
pip install -r requirements/server.txt
FOCUSFLOW_REPOSITORY=memory uvicorn server.app:app --reload
```

## Test nhanh pipeline

```bash
python tests/manual/test_tracker.py --model models/late_fusion/engagement_gru.onnx
```

## Build desktop app

```bash
pyinstaller focusflow_app.spec --clean
```

## Public download portal

For demo distribution, the repository includes a static landing page designed
for Google Cloud Storage static website hosting.

- Put the built release artifacts in a public Cloud Storage bucket.
- Publish the landing page from `deploy/gcp/static-site/`.
- Link each OS download button directly to the public object URL.

This keeps the cloud backend focused on API, inference, and session storage
while the download portal stays simple and easy to maintain.

## Ghi chú

- Runtime không dùng PyTorch.
- UI stack hiện tại là PyQt6.
- Hệ thống không thu thập window title, process, bàn phím hoặc chuột.
- Raw webcam frame không được gửi lên cloud.
- `scripts/export_to_onnx.py` chỉ dùng khi cần xuất lại checkpoint sang ONNX.
- Dữ liệu phiên được lưu cục bộ trong `data/history.json`.
- Report completion chỉ ghi trạng thái/timestamp, không còn AI coach hoặc mentor email.
