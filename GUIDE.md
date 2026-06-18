# FocusFlow Model Guide

Tài liệu này mô tả model production đang được serve trong FocusTracker.
Artifact gốc nằm ở repo training:

```text
../engagement-cpu/checkpoints/runs/product_4class_fixed_triple_xgb/
```

Theo `../engagement-cpu/README.md`, artifact này cũng được đóng gói trên
Hugging Face dataset `Hnug/daisee-processed` tại:

```text
product_4class_fixed_triple_xgb/product_4class_fixed_triple_xgb.zip
```

## Model Đang Dùng

| Mục đích | Model | Ghi chú |
|---|---|---|
| Runtime chính | `fixed_triple_xgb_fusion` | 4-class fixed triple-XGBoost fusion |
| Component 1 | `final_xgb` | nhánh XGBoost mạnh nhất |
| Component 2 | `boost_xgb` | nhánh boosted bổ sung |
| Component 3 | `targeted_xgb` | nhánh targeted theo class |

## Input Contract

Pipeline app:

1. Webcam/video frame -> MediaPipe FaceMesh features.
2. Feature frame -> `FeatureSequenceBuffer`.
3. Raw sequence `(30, 30)` -> `tracking.buffer.enrich_raw_sequence()`.
4. Enriched sequence `(30, 90)` -> tsfresh-like tabular feature vector `2161`.
5. Mỗi component áp dụng `preprocessor.npz`, chạy XGBoost, rồi trả 4-class probabilities.
6. Runtime fuse probabilities, calibrate bằng class bias + temperature, rồi map về focus score.

Shape chuẩn:

```text
T = 30
raw frame feature dim = 30
enriched sequence dim = 90
tabular feature dim = 2161
class labels = very_low, low, medium, high
```

## Artifacts Trong Repo App

```text
models/product_4class_fixed_triple_xgb/
  README.md
  summary.json
  reproduction_config.json
  final_xgb/model.json
  final_xgb/preprocessor.npz
  final_xgb/summary.json
  boost_xgb/model.json
  boost_xgb/preprocessor.npz
  boost_xgb/summary.json
  targeted_xgb/model.json
  targeted_xgb/preprocessor.npz
  targeted_xgb/summary.json
models/face_landmarker.task
```

## Fusion Contract

Runtime dùng đúng tham số trong `reproduction_config.json`:

```python
mixed = (0.84 * final_xgb_probs) + (0.14 * boost_xgb_probs) + (0.02 * targeted_xgb_probs)
adjusted = class_bias(mixed, bias_power=0.42, validation_counts=[23, 143, 813, 450])
adjusted = temperature_calibrate(adjusted, temperature=1.15)
focus_score = adjusted[2] + adjusted[3]
prediction = int(adjusted.argmax(axis=-1))
state = "ENGAGED" if prediction in {2, 3} else "DISTRACTED"
```

The app maps `ENGAGED` to final `FOCUSED`; face absence still wins via the
face-presence guard. There is no OS telemetry or heuristic override.

## Runtime Code Map

| File | Responsibility |
|---|---|
| `tracking/detector.py` | MediaPipe feature extraction |
| `tracking/buffer.py` | Builds and enriches the 30-frame sequence |
| `tracking/inference.py` | Loads the triple-XGB artifact and runs 4-class fusion |
| `tracking/tracker.py` | Camera thread, cloud/local/hybrid routing, queue telemetry |
| `server/core/inference.py` | Cloud API adapter around the same runtime inferencer |

## Service Response Shape

`ONNXEngagementInferencer.predict()` returns:

```json
{
  "model_name": "fixed_triple_xgb_fusion",
  "model_version": "product_4class_fixed_triple_xgb",
  "label_space": "daisee_4class",
  "decision_rule": "argmax_4class",
  "probability": 0.0,
  "focus_score": 0.0,
  "state": "ENGAGED",
  "class_labels": ["very_low", "low", "medium", "high"],
  "probabilities_4class": [0.0, 0.0, 0.0, 0.0],
  "prediction_4class": 0,
  "prediction_label": "very_low",
  "sequence_length": 30,
  "raw_feature_dim": 30,
  "enriched_feature_dim": 90,
  "components": {
    "final_xgb": {"probability": 0.0, "probabilities": [0.0, 0.0, 0.0, 0.0]},
    "boost_xgb": {"probability": 0.0, "probabilities": [0.0, 0.0, 0.0, 0.0]},
    "targeted_xgb": {"probability": 0.0, "probabilities": [0.0, 0.0, 0.0, 0.0]}
  },
  "weights": {
    "final_xgb": 0.84,
    "boost_xgb": 0.14,
    "targeted_xgb": 0.02
  }
}
```

## Fallbacks Cần Giữ

* Không đủ 30 frame: giữ trạng thái `WARMING_UP`.
* Không detect face: vẫn render frame, nhưng không tin AI score mới.
* NaN/Inf trong feature: replace bằng `0.0` trước inference.
* Thiếu artifact: fail rõ bằng `FileNotFoundError` để biết bundle bị thiếu.
* Sai shape `(30, 90)` hoặc sai tabular dim `2161`: fail rõ bằng `ValueError`.
* Pause session: release camera và reset buffer/inferencer để tiết kiệm CPU.

## Khi Cập Nhật Model

1. Rebuild artifact trong repo training:

```bash
cd ../engagement-cpu
bash scripts/reproduce_product_4class.sh
```

2. Copy artifact vào app:

```bash
rsync -a --delete \
  ../engagement-cpu/checkpoints/runs/product_4class_fixed_triple_xgb/ \
  models/product_4class_fixed_triple_xgb/
```

3. Chạy regression tests:

```bash
pytest tests/test_logic_oonx.py tests/server/test_cloud_inference.py tests/server/test_api.py
```

4. Chạy manual test nếu cần xem telemetry:

```bash
python tests/manual/test_tracker.py --model models/product_4class_fixed_triple_xgb
```

5. Cập nhật file này nếu weight, calibration, class mapping, shape hoặc artifact name thay đổi.
