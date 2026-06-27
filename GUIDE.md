# FocusFlow Model Guide

FocusFlow product runtime now uses the depth-robust Triple XGBoost 4-class
artifact selected from the `engagement-cpu` checkpoint reports.

## Production Model

```text
model_name:         triple_xgb_depth_robust_fusion
model_version:      triple_xgb_depth_robust_target_band_product
accuracy:           76.85%
balanced accuracy:  83.20%
macro F1:           76.91%
mean latency:       24.80 ms
decision rule:      argmax over calibrated 4-class probabilities
component weights:  final_xgb=0.72, boost_xgb=0.26, targeted_xgb=0.02
```

The UI displays `focus_score = P(high)` as telemetry. The final model state
still comes from the 4-class argmax: only class `high` maps to `ENGAGED`;
`very_low`, `low`, and `medium` all map to `DISTRACTED`. The face-presence guard
has priority and maps missing faces to `NO_FACE`.

## Input Contract

```text
frame schema:       depth_robust_v2
raw frame feature:  168 values
raw sequence:       (30, 168)
enrichment:         value + velocity + per-window std
model sequence:     (30, 504)
tabular features:   12097 tsfresh-like aggregate values
labels:             very_low, low, medium, high
```

`tracking.detector.FaceFeatureDetector` extracts one 168-value feature vector
from each valid frame. `tracking.buffer.enrich_raw_sequence()` is the canonical
raw-to-enriched transform. Both edge inference and Cloud Run inference must use
that same transform.

## Artifact

Install the bundle at:

```text
models/triple_xgb_depth_robust_target_band_product/
  fusion_config.json
  summary.json
  final_xgb/model.json
  final_xgb/preprocessor.npz
  boost_xgb/model.json
  boost_xgb/preprocessor.npz
  targeted_xgb/model.json
  targeted_xgb/preprocessor.npz
```

Canonical remote artifact:

```text
Hnug/daisee-processed/checkpoints/runs/triple_xgb_depth_robust_target_band_product.zip
```

Cloud Build fetches the same zip from:

```text
gs://${PROJECT_ID}-focusflow-releases/models/triple_xgb_depth_robust_target_band_product.zip
```

## Inference Contract

```python
enriched = enrich_raw_sequence(raw_30x168)     # -> (30, 504)
x = tsfresh_like_features(enriched)            # -> (12097,)
p_final = final_xgb.predict_proba(scale_final(x))
p_boost = boost_xgb.predict_proba(scale_boost(x))
p_targeted = targeted_xgb.predict_proba(scale_targeted(x))
p_fused = 0.72 * p_final + 0.26 * p_boost + 0.02 * p_targeted
p_calibrated = normalize(p_fused * class_bias_from_validation_support)
prediction = argmax(p_calibrated)
focus_score = p_calibrated[3]
state = "ENGAGED" if prediction == 3 else "DISTRACTED"
```

The response exposes `final_xgb`, `boost_xgb`, and `targeted_xgb` component
probabilities. There is no OS telemetry or heuristic override.

## Runtime Code Map

| File | Responsibility |
|---|---|
| `tracking/detector.py` | Production `depth_robust_v2` frame extraction |
| `tracking/buffer.py` | Builds `(30,168)` windows and `(30,504)` enrichment |
| `tracking/inference.py` | Loads and evaluates the Triple XGB product bundle |
| `tracking/tracker.py` | Camera thread, bounded edge inference worker, and optional cloud transport |
| `server/core/inference.py` | Thread-safe Cloud Run inference adapter |

## Fallbacks

- Fewer than 30 valid frames: render `WARMING_UP` and send no model packet.
- No face: retain local preview and use the face-presence guard.
- NaN/Inf: sanitize to `0.0` before inference; invalid feature vectors are
  dropped before entering the window.
- Missing `fusion_config.json` or component model files: fail startup clearly.
- Any shape other than `(30,168)` raw or `(30,504)` enriched: fail clearly.
