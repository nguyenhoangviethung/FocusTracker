# FocusFlow AI Architecture

This document describes the current runtime architecture. `AGENTS.md` and the
deployed artifact under `models/deep_forest_product_4class/` remain the
highest-priority sources of truth.

## 1. Architectural style

FocusFlow is an edge-to-cloud, privacy-oriented system:

- the desktop captures frames and extracts numeric facial features;
- raw frames remain in edge process memory and are never uploaded;
- the Cloud Run API owns production inference and session lifecycle;
- Firestore stores user/session records, not the 30 FPS feature stream;
- Pub/Sub receives durable domain events such as `session.completed`.

The production model is the calibrated 4-class DeepForest artifact. It uses
layer-1 ExtraTrees and RandomForest estimators followed by a layer-2 cascade.
There is no GRU/TCN or XGBoost production path in the current desktop session
workflow.

## 2. Runtime boundaries

### Edge desktop

| Component | Responsibility |
| --- | --- |
| `ui/` | PyQt6 presentation and user interaction |
| `tracking/detector.py` | MediaPipe face detection and 168-value depth-robust frame vector |
| `tracking/buffer.py` | Canonical `(30,168)` to `(30,504)` enrichment |
| `tracking/tracker.py` | Camera/network worker orchestration and UI-safe queue |
| `edge/cloud_client.py` | Blocking REST/WebSocket transport on background threads |
| `utils/` | Local settings, paths, logging, and report cache |

### Cloud Run API

| Component | Responsibility |
| --- | --- |
| `server/api/routes.py` | HTTP/WebSocket boundary, authentication and validation |
| `server/core/inference.py` | Thread-safe inference application service |
| `tracking/inference.py` | Calibrated DeepForest adapter and 3529-D aggregation |
| `server/repositories/` | Memory and Firestore persistence adapters |
| `server/services/` | Authentication and Pub/Sub event adapters |
| `shared/contracts.py` | Versioned Pydantic wire contracts |

Dependencies flow from presentation/transport toward application services and
domain/model adapters. Managed services are reached only through repository or
publisher interfaces. The edge imports shared contracts but does not import the
server package.

## 3. Inference flow

1. OpenCV captures one frame on the edge.
2. MediaPipe returns a 168-value `depth_robust_v2` vector and a face-presence flag.
3. `FeatureSequenceBuffer` accumulates 30 vectors into `(30,168)`.
4. At most once per second, the tracker sends a `TelemetryPacket` over WSS.
5. FastAPI validates API key, identifiers, protocol version and tensor shape.
6. `enrich_raw_sequence()` creates the canonical `(30,504)` tensor.
7. The model adapter creates 3529 basic aggregate values.
8. The layer-1 ExtraTrees/RandomForest estimators and layer-2 cascade return four-class probabilities.
9. Class-logit bias and temperature calibration are applied.
10. The server returns `InferenceResponse` correlated by `message_id`.
11. The UI renders the four-class result, focus telemetry and component scores.

The class decision is `argmax_4class`. `focus_score = P(medium) + P(high)` is
continuous telemetry for charts and summaries; it is not a binary threshold
decision. If `face_found=false`, the face-presence guard returns `NO_FACE`.

## 4. Concurrency and failure behavior

- PyQt widgets run only on the UI thread.
- Camera capture and cloud transport run on separate background threads.
- Queues are bounded and retain the latest useful telemetry under load.
- The WebSocket client reconnects with exponential backoff and jitter.
- During disconnection, the UI reports reconnecting and does not fabricate a
  local model prediction.
- Blocking DeepForest inference is dispatched outside FastAPI's event loop.
- Model artifacts are loaded once per Cloud Run instance.
- Cloud Run is stateless; session truth lives in the repository.

## 5. Persistence

`focusflow_users` is the only user collection. Password and Google identities
share the same repository and deterministic ID rules.

`focusflow_sessions` stores lifecycle metadata, a bounded live snapshot and the
final summary. It does not store every feature sequence. Session completion is
idempotent and emits `session.completed` through the event publisher.

## 6. Security and privacy

- Use HTTPS/WSS outside local development.
- Require `X-API-Key` for desktop API access.
- Keep service secrets in Secret Manager.
- Store password hashes using salted PBKDF2-SHA256.
- Never upload or persist raw webcam frames.
- Treat facial-feature telemetry as sensitive biometric-derived data.
- Do not collect window titles, processes, keyboard, mouse or OS activity.

## 7. UML set

Editable Mermaid sources and generated publication assets live in
[`docs/uml`](docs/uml/README.md):

1. use-case diagram;
2. component diagram;
3. deployment diagram;
4. realtime inference sequence;
5. desktop session state machine;
6. domain/data model.

Run `bash scripts/render_uml.sh` to regenerate SVG and PNG assets.
