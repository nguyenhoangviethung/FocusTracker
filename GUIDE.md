# FocusFlow Model Guide

FocusFlow serves the calibrated 4-class DeepForest product model documented in
`../engagement-cpu/checkpoints/reports/GUIDE.md`.

## Production Model

```text
model_name:      deep_forest_product_4class
accuracy:        76.85%
balanced accuracy:85.90%
macro F1:        78.02%
decision rule:   argmax over calibrated 4-class probabilities
```

The uncalibrated DeepForest experiment reached 88.00% accuracy but only 62.33%
balanced accuracy and is not a production artifact.

## Input Contract

```text
frame schema:       depth_robust_v2
raw frame feature:  168 values
raw sequence:       (30, 168)
enrichment:         velocity + per-window standard deviation
model sequence:     (30, 504)
tabular features:   3529 basic aggregate values
labels:             very_low, low, medium, high
```

The edge extractor is `tracking.detector.FaceFeatureDetector`. It uses
aspect-correct canonical landmarks, depth proxies, iris measurements,
MediaPipe blendshapes, and facial transformation matrices. Missing faces do
not enter the buffer. The server is the only place that loads `model.joblib`.

## Artifact

Download and unpack the bundle into `models/deep_forest_product_4class/`:

```text
Hnug/daisee-processed/checkpoints/runs/deep_forest_product_4class.zip
  model.joblib
  summary.json
```

## Inference Contract

```python
layer1_features = concat_predict_proba(layer1, basic_features)
layer2_prob = mean_predict_proba(layer2, concat(basic_features, layer1_features))
prob = softmax(log(clip(layer2_prob)) / 1.25 + [1.5, 2.5, 0.0, 0.5])
prediction = argmax(prob)
focus_score = prob[2] + prob[3]
state = "ENGAGED" if prediction in {2, 3} else "DISTRACTED"
```

The response exposes `layer1_extra_trees`, `layer1_random_forest`, and
`layer2_cascade` as component telemetry. `focus_score` is telemetry only; the
state remains the calibrated 4-class argmax result.

The app maps `ENGAGED` to final `FOCUSED`; face absence still wins via the
face-presence guard. There is no OS telemetry or heuristic override.

## Runtime Code Map

| File | Responsibility |
|---|---|
| `tracking/detector.py` | Production `depth_robust_v2` frame extraction |
| `tracking/buffer.py` | Builds `(30,168)` windows and `(30,504)` enrichment |
| `tracking/inference.py` | Loads and evaluates the calibrated DeepForest bundle |
| `tracking/tracker.py` | Camera thread and cloud telemetry queue |
| `server/core/inference.py` | Thread-safe cloud inference adapter |

## Fallbacks

- Fewer than 30 valid frames: render `WARMING_UP` and send no model packet.
- No face: retain local preview and use the face-presence guard.
- NaN/Inf: sanitize to `0.0` before enrichment; invalid feature vectors are
  dropped before entering the window.
- Missing `model.joblib`: fail startup with a clear `FileNotFoundError`.
- Any shape other than `(30,168)` raw or `(30,504)` enriched: fail clearly.

## Updating The Artifact

1. Download `deep_forest_product_4class.zip` from the Hugging Face dataset.
2. Unpack `model.joblib` and `summary.json` into
   `models/deep_forest_product_4class/`.
3. Run `pytest tests/server/test_cloud_inference.py tests/server/test_api.py`.
4. Build the Cloud Run image only after the server smoke test loads that bundle.
