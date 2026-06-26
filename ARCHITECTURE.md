# FocusFlow AI Architecture

This document describes the current runtime architecture. `AGENTS.md` and the
deployed artifact under `models/product_4class_fixed_triple_xgb/` remain the
highest-priority sources of truth.

## 1. Architectural style

FocusFlow is an edge-to-cloud, privacy-oriented system:

- the desktop captures frames and extracts numeric facial features;
- raw frames remain in edge process memory and are never uploaded;
- the Cloud Run API owns production inference and session lifecycle;
- Firestore stores user/session records, not the 30 FPS feature stream;
- Pub/Sub receives durable domain events such as `session.completed`.

The production model is Fixed Triple-XGBoost. It combines `final_xgb`,
`boost_xgb`, and `targeted_xgb` with weights `0.84`, `0.14`, and `0.02`.
There is no GRU/TCN production path and no local ONNX fallback in the current
desktop session workflow.

## 2. Runtime boundaries

### Edge desktop

| Component | Responsibility |
| --- | --- |
| `ui/` | PyQt6 presentation and user interaction |
| `tracking/detector.py` | MediaPipe face detection and 30-value frame vector |
| `tracking/buffer.py` | Canonical `(30,30)` to `(30,90)` enrichment |
| `tracking/tracker.py` | Camera/network worker orchestration and UI-safe queue |
| `edge/cloud_client.py` | Blocking REST/WebSocket transport on background threads |
| `utils/` | Local settings, paths, logging, and report cache |

### Cloud Run API

| Component | Responsibility |
| --- | --- |
| `server/api/routes.py` | HTTP/WebSocket boundary, authentication and validation |
| `server/core/inference.py` | Thread-safe inference application service |
| `tracking/inference.py` | Triple-XGBoost model adapter and 2161-D aggregation |
| `server/repositories/` | Memory and Firestore persistence adapters |
| `server/services/` | Authentication and Pub/Sub event adapters |
| `shared/contracts.py` | Versioned Pydantic wire contracts |

Dependencies flow from presentation/transport toward application services and
domain/model adapters. Managed services are reached only through repository or
publisher interfaces. The edge imports shared contracts but does not import the
server package.

## 3. Inference flow

1. OpenCV captures one frame on the edge.
2. MediaPipe returns a 30-value vector and a face-presence flag.
3. `FeatureSequenceBuffer` accumulates 30 vectors into `(30,30)`.
4. At most once per second, the tracker sends a `TelemetryPacket` over WSS.
5. FastAPI validates API key, identifiers, protocol version and tensor shape.
6. `enrich_raw_sequence()` creates the canonical `(30,90)` tensor.
7. The model adapter creates 2161 tsfresh-like window statistics.
8. Three XGBoost components return four-class probabilities.
9. Weighted fusion, class bias and temperature calibration are applied.
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
- Blocking XGBoost inference is dispatched outside FastAPI's event loop.
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
