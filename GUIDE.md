# FocusFlow Model Guide

Tài liệu này được kéo về từ repo `engagement-cpu`, source gốc:

```text
../engagement-cpu/checkpoints/reports/GUIDE.md
```

Giữ bản copy trong FocusTracker để bảo trì app mà không cần đọc tài liệu ở thư mục khác.

## Model Đang Dùng

| Mục đích | Model | Ghi chú |
|---|---|---|
| Runtime chính | `late_fusion_gru_tcn_xgb` | Ensemble GRU + TCN + XGBoost |
| Neural temporal | `gru`, `tcn` | Chạy qua ONNXRuntime |
| Tabular temporal | `xgboost` | Chạy từ `engagement_xgb.json` + preprocessor |

## Input Contract

Pipeline app:

1. Webcam/video frame -> MediaPipe FaceMesh features.
2. Feature frame -> `FeatureSequenceBuffer`.
3. Sequence enriched shape `(30, 90)` -> GRU/TCN ONNX + XGBoost tabular features.
4. GRU/TCN inputs must be normalized with `feature_mean`/`feature_std` from the source `.pt` checkpoints when `normalize_features=true`.
5. XGBoost uses the raw enriched sequence to build tsfresh-like tabular features, then applies `engagement_xgb.preprocess.npz`.
6. Late fusion probability -> `fusion_logic` kết hợp OS tracker.

Shape chuẩn:

```text
T = 30
raw frame feature dim = 30
enriched sequence dim = 90
model input = (30, 90)
```

## Artifacts Trong Repo App

```text
models/late_fusion/engagement_gru.onnx
models/late_fusion/engagement_gru.json
models/late_fusion/engagement_tcn.onnx
models/late_fusion/engagement_tcn.json
models/late_fusion/engagement_xgb.json
models/late_fusion/engagement_xgb.summary.json
models/late_fusion/engagement_xgb.preprocess.npz
models/late_fusion/late_fusion_gru_tcn_xgb_report.json
models/face_landmarker.task
```

## Fusion Contract

Late-fusion model probability:

```python
p_final = (0.30 * p_gru) + (0.30 * p_tcn) + (0.40 * p_xgb)
prediction = int(p_final >= 0.54)
```

The app then combines `p_final` with OS context in `main.fusion_logic`.

## Runtime Code Map

| File | Responsibility |
|---|---|
| `tracking/detector.py` | MediaPipe feature extraction |
| `tracking/buffer.py` | Builds the 30-frame enriched sequence |
| `tracking/inference.py` | Loads GRU/TCN ONNX, XGBoost, metadata, and runs late fusion |
| `tracking/tracker.py` | Camera thread, OS thread, pause/resume, queue telemetry |
| `main.py` | Final AI + OS decision fusion |

## Service Response Shape

`ONNXEngagementInferencer.predict()` should return enough trace data to debug production sessions:

```json
{
  "model_name": "late_fusion_gru_tcn_xgb",
  "model_version": "20260608",
  "threshold": 0.54,
  "probability": 0.0,
  "focus_score": 0.0,
  "state": "ENGAGED",
  "sequence_length": 30,
  "raw_feature_dim": 30,
  "enriched_feature_dim": 90,
  "components": {
    "gru": {"probability": 0.0},
    "tcn": {"probability": 0.0},
    "xgboost": {"probability": 0.0}
  },
  "weights": {
    "gru": 0.30,
    "tcn": 0.30,
    "xgboost": 0.40
  }
}
```

## Fallbacks Cần Giữ

* Không đủ 30 frame: giữ trạng thái `WARMING_UP`.
* Không detect face: vẫn render frame, nhưng không tin AI score mới.
* NaN/Inf trong feature: replace bằng `0.0` trước inference.
* Thiếu artifact: fail rõ bằng `FileNotFoundError` để biết bundle bị thiếu.
* Thiếu `feature_mean`/`feature_std` khi `normalize_features=true`: fail rõ bằng `ValueError`, không được chạy inference sai scale.
* Pause session: release camera và reset buffer/inferencer để tiết kiệm CPU.

## Khi Cập Nhật Model

1. Export ONNX bằng exporter repo app để dùng đúng source model GRU/TCN:

```bash
python scripts/export_to_onnx.py \
  --checkpoint ../engagement-cpu/checkpoints/runs/final_rnn_temporal_models_20260529/rnn_gru/engagement_gru.pt \
  --output models/late_fusion/engagement_gru.onnx

python scripts/export_to_onnx.py \
  --checkpoint ../engagement-cpu/checkpoints/runs/final_rnn_temporal_models_20260529/rnn_tcn/engagement_tcn.pt \
  --output models/late_fusion/engagement_tcn.onnx
```

2. Copy/sync normalization metadata vào repo app:

```bash
python scripts/sync_late_fusion_metadata.py --engagement-repo ../engagement-cpu
```

Runtime chỉ được đọc artifact dưới `models/late_fusion/`; mọi đường dẫn source training trong metadata chỉ là ghi chú bảo trì, không phải dependency deploy.

Trong app live, runtime vẫn infer đủ GRU + TCN + XGBoost. Tuy nhiên nếu GRU và TCN cùng vượt threshold riêng, score chính dùng `neural_consensus_guarded` để tránh XGBoost under-calibrated trên webcam cá nhân kéo tụt confidence; XGBoost vẫn được giữ trong telemetry/trace và vẫn tham gia khi neural chưa đồng thuận.

3. Đảm bảo metadata khai báo đúng `sequence_length`, `raw_feature_dim`, `enriched_feature_dim`, threshold và calibration.

4. Chạy regression test. Test này pin golden output cho GRU + TCN + XGBoost để bắt lỗi export sai kiến trúc hoặc sai calibration:

```bash
pytest tests/test_logic_oonx.py
```

5. Chạy manual test nếu cần xem telemetry:

```bash
python tests/manual/test_tracker.py --model models/late_fusion/engagement_gru.onnx
```

6. Cập nhật file này nếu weight, threshold, shape hoặc artifact name thay đổi.
