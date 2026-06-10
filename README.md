# FocusFlow AI

FocusFlow AI là ứng dụng desktop theo dõi mức độ tập trung theo thời gian thực bằng webcam, MediaPipe, ONNXRuntime và XGBoost.

## Thành phần chính

- `main.py`: điểm vào duy nhất của ứng dụng.
- `ui/`: giao diện CustomTkinter, không mix `ttkbootstrap` để tránh lỗi render/pixel trên Ubuntu.
- `tracking/`: trích xuất đặc trưng, buffer 30 frame và suy luận late-fusion.
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

## Test nhanh pipeline

```bash
python tests/manual/test_tracker.py --model models/late_fusion/engagement_gru.onnx
```

## Build desktop app

```bash
pyinstaller focusflow_app.spec --clean
```

## Ghi chú

- Runtime không dùng PyTorch.
- UI stack hiện tại chọn `CustomTkinter` thay vì `ttkbootstrap`.
- `scripts/export_to_onnx.py` chỉ dùng khi cần xuất lại checkpoint sang ONNX.
- Dữ liệu phiên được lưu cục bộ trong `data/history.json`.
