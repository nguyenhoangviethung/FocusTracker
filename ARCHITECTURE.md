# FocusFlow AI Architecture

This document is the ASCII map of the current runtime architecture.
It focuses on how data moves through the system and what runs in the
background on the desktop, on Cloud Run, and in the supporting cloud services.

Core rules:
- Vision-only system.
- No OS/process/window tracking.
- No keyboard, mouse, CPM, or KPM collection.
- No raw webcam frame upload or storage.
- The canonical raw-to-enriched transform is `tracking.buffer.enrich_raw_sequence()`.
- Final focus decisions come from the deployed late-fusion model plus the face-presence guard.

## 1. End-to-end flow

```text
+==================================================================================================+
| EDGE DESKTOP                                                                                    |
|                                                                                                  |
|  python main.py                                                                                  |
|                                                                                                  |
|  +----------------------+        signals/state        +----------------------------------------+ |
|  | UI thread            |<--------------------------->| PyQt6 widgets                          | |
|  | - render controls    |                            | - session state                         | |
|  | - never blocks I/O   |                            | - preview status                        | |
|  +----------------------+                            +----------------------------------------+ |
|           |                                                                                      |
|           | start / stop / reconnect                                                             |
|           v                                                                                      |
|  +----------------------+                                                                        |
|  | tracker worker       |                                                                        |
|  | tracking/tracker.py  |                                                                        |
|  | vision worker only   |                                                                        |
|  +-----------+----------+                                                                        |
|              |                                                                                   |
|              +--> [Camera worker] OpenCV capture                                                |
|              |        |                                                                         |
|              |        v                                                                         |
|              |   [MediaPipe FaceMesh] -> 30-value feature vector / frame                        |
|              |                                                                                   |
|              +--> [Preview renderer] <---- local frames only ---------------------------------+  |
|              |                                                                               |  |
|              +--> [Sliding buffer] 30 frames -> raw sequence (30,30)                        |  |
|              |                                                                               |  |
|              +--> [Local inference worker / fallback]                                       |  |
|              |       tracking.buffer.enrich_raw_sequence()                                   |  |
|              |       (30,30) -> (30,90)                                                      |  |
|              |       bundled GRU + TCN + XGBoost                                             |  |
|              |                                                                               |  |
|              +--> [Network worker] edge/cloud_client.py                                      |  |
|                      - stable device_id                                                      |  |
|                      - POST /v1/sessions                                                     |  |
|                      - WS /v1/ws/sessions/{session_id}?device_id=...                        |  |
|                      - POST /v1/sessions/{session_id}/complete                               |  |
|                      - exponential backoff + jitter                                           |  |
|                      - JSON v1 only                                                          |  |
|                      - no image/video payload                                                 |  |
|                                                                                                  |
|  Optional identity flow:                                                                         |
|    edge/auth_client.py -> username/password or Google OAuth2 -> user_id demo tracking          |
|    X-API-Key is still required for desktop requests.                                            |
+==================================================================================================+
                                  | TLS HTTPS / WSS
                                  | telemetry packets are JSON v1 only
                                  v
+==================================================================================================+
| CLOUD RUN: focusflow-api (stateless, concurrency=4, CPU allocated while connected)              |
|                                                                                                  |
|  [server/app.py lifespan]                                                                        |
|      |                                                                                           |
|      +--> load model artifacts once per instance                                                 |
|      |     models/late_fusion/*                                                                 |
|      |                                                                                           |
|  [server/api/routes.py]                                                                          |
|      |                                                                                           |
|      +--> GET  /healthz                                                                          |
|      +--> GET  /readyz                                                                           |
|      +--> POST /v1/sessions                                                                      |
|      +--> GET  /v1/sessions/{session_id}                                                         |
|      +--> POST /v1/sessions/{session_id}/complete                                                |
|      +--> WS   /v1/ws/sessions/{session_id}?device_id=...                                       |
|      +--> POST /v1/inference                                                                     |
|      +--> schema / shape / idempotency validation                                                |
|      +--> X-API-Key auth                                                                         |
|                                                                                                  |
|  [async handler]                                                                                 |
|      |                                                                                           |
|      +--> dispatch blocking inference outside the event loop                                    |
|             to a worker / threadpool                                                             |
|                                                                                                  |
|  [server/core/inference.py]                                                                      |
|      |                                                                                           |
|      +--> tracking.buffer.enrich_raw_sequence()                                                  |
|      +--> GRU ONNX probability                                                                   |
|      +--> TCN ONNX probability                                                                   |
|      +--> XGBoost probability                                                                    |
|      +--> late fusion weights: 0.30 + 0.30 + 0.40                                               |
|      +--> threshold: 0.54                                                                        |
|      +--> face_found guard                                                                       |
|                                                                                                  |
|  [server/repositories/sessions.py]                                                               |
|      +--> Firestore focusflow_sessions/{session_id}                                               |
|      +--> deterministic readable session IDs                                                     |
|      +--> live_metrics overwrite snapshot <= 1 Hz                                                |
|      +--> summary + report metadata                                                              |
|                                                                                                  |
|  [server/repositories/users.py]                                                                  |
|      +--> Firestore focusflow_users                                                               |
|      +--> username/password and Google subject records                                           |
|                                                                                                  |
|  [server/services/auth_service.py]                                                               |
|      +--> verify username/password or Google OAuth2                                              |
|      +--> upsert user identity transactionally                                                    |
|                                                                                                  |
|  [server/services/event_publisher.py]                                                            |
|      +--> publish session.completed AFTER summary is durably saved                               |
|                                                                                                  |
|  Response payload:                                                                               |
|      model name/version, final focus score/state, component probabilities, weights,             |
|      decision trace, processing latency, original message_id                                     |
|                                                                                                  |
|  Never return raw frames, landmarks, window titles, process names, or input-device activity.    |
+==================================================================================================+
```

## 2. Desktop background workers

```text
+==================================================================================================+
| DESKTOP PROCESS                                                                                  |
|                                                                                                  |
|  main.py                                                                                         |
|    |                                                                                             |
|    v                                                                                             |
|  +----------------------+                                                                        |
|  | UI thread            |                                                                        |
|  | - PyQt6 only         |                                                                        |
|  | - render widgets     |                                                                        |
|  | - receives signals    |                                                                        |
|  | - never does camera   |                                                                        |
|  |   capture / I/O /     |                                                                        |
|  |   inference           |                                                                        |
|  +----------+-----------+                                                                        |
|             |                                                                                    |
|             | signals / queued state                                                            |
|             v                                                                                    |
|  +----------------------+                                                                        |
|  | Camera worker        |                                                                        |
|  | OpenCV capture       |                                                                        |
|  | MediaPipe features   |                                                                        |
|  +----------+-----------+                                                                        |
|             |                                                                                    |
|             v                                                                                    |
|  +----------------------+                                                                        |
|  | Sliding buffer       |                                                                        |
|  | 30 frames -> (30,30)|                                                                        |
|  +----------+-----------+                                                                        |
|             |                                                                                    |
|             +----------------------+----------------------+                                       |
|                                    |                      |                                       |
|                                    v                      v                                       |
|                         +----------------------+   +----------------------+                       |
|                         | Local inference     |   | Network worker        |                       |
|                         | tracking/inference  |   | edge/cloud_client.py  |                       |
|                         | tracking.buffer     |   | REST + WSS transport  |                       |
|                         | enrich_raw_sequence  |   | stable device_id      |                       |
|                         | bundled fallback     |   | backoff + jitter      |                       |
|                         +----------------------+   +----------+-----------+                       |
|                                                            |                                      |
|                                                            v                                      |
|                                                   TLS HTTPS / WSS                                  |
|                                                   JSON v1 telemetry                               |
|                                                   no raw image/video                              |
|                                                                                                  |
|  Preview renderer --------------------------------------------------------------------------------|
|    - renders local frames only                                                                    |
|    - never leaves the edge process                                                                 |
|                                                                                                  |
|  Identity client                                                                                  |
|    - edge/auth_client.py                                                                          |
|    - username/password demo flow                                                                  |
|    - Google OAuth2 demo flow                                                                      |
|    - user_id for demo tracking                                                                    |
|    - does not replace X-API-Key                                                                   |
+==================================================================================================+
```

## 3. Cloud Run internals

```text
+==================================================================================================+
| CLOUD RUN SERVICE: focusflow-api                                                                  |
|                                                                                                  |
|  Deployment / runtime rules                                                                      |
|  - stateless instances                                                                           |
|  - concurrency = 4                                                                               |
|  - CPU stays allocated while handling a connected request                                        |
|  - model artifacts load once during app lifespan                                                 |
|  - blocking inference runs outside the asyncio event loop                                        |
|                                                                                                  |
|  [ASGI / FastAPI app]                                                                            |
|      |                                                                                           |
|      +--> [Health and readiness]                                                                 |
|      |       - GET /healthz                                                                      |
|      |       - GET /readyz                                                                       |
|      |                                                                                           |
|      +--> [Session lifecycle]                                                                    |
|      |       - POST /v1/sessions                                                                 |
|      |       - GET /v1/sessions/{session_id}                                                     |
|      |       - POST /v1/sessions/{session_id}/complete                                           |
|      |                                                                                           |
|      +--> [Telemetry transport]                                                                  |
|      |       - WS /v1/ws/sessions/{session_id}?device_id=...                                     |
|      |       - accepts JSON v1 only                                                              |
|      |                                                                                           |
|      +--> [Inference endpoint]                                                                   |
|      |       - POST /v1/inference                                                                |
|      |                                                                                           |
|      +--> [Validation layer]                                                                     |
|              - protocol version                                                                   |
|              - raw shape checks                                                                   |
|              - idempotency                                                                       |
|              - X-API-Key                                                                         |
|                                                                                                  |
|  [server/app.py lifespan]                                                                        |
|      +--> load late-fusion artifacts once                                                         |
|                                                                                                  |
|  [server/core/inference.py]                                                                      |
|      +--> enrich raw sequence (30,30) -> (30,90)                                                  |
|      +--> GRU ONNX                                                                               |
|      +--> TCN ONNX                                                                               |
|      +--> XGBoost                                                                                 |
|      +--> face_found guard                                                                       |
|      +--> late fusion decision                                                                   |
|                                                                                                  |
|  [server/repositories/sessions.py]                                                               |
|      +--> focusflow_sessions/{session_id}                                                        |
|      +--> live_metrics snapshot                                                                  |
|      +--> summary and report metadata                                                            |
|                                                                                                  |
|  [server/repositories/users.py]                                                                  |
|      +--> focusflow_users                                                                        |
|                                                                                                  |
|  [server/services/auth_service.py]                                                               |
|      +--> auth and user upsert                                                                   |
|                                                                                                  |
|  [server/services/event_publisher.py]                                                            |
|      +--> Pub/Sub: session.completed                                                             |
+==================================================================================================+
```

## 4. Persistent storage, events, and delivery

```text
+--------------------------------------------------------------------------------------------------+
| FIRESTORE NATIVE                                                                                 |
|                                                                                                  |
|  focusflow_sessions/{session_id}                                                                 |
|    - device_id                                                                                   |
|    - user_id                                                                                     |
|    - status                                                                                      |
|    - started_at                                                                                  |
|    - ended_at                                                                                    |
|    - last_seen_at                                                                                |
|    - duration_seconds                                                                            |
|    - summary                                                                                     |
|    - live_metrics                                                                                |
|    - model_version                                                                               |
|    - report_status                                                                               |
|    - report_started_at                                                                           |
|    - report_completed_at                                                                         |
|                                                                                                  |
|  focusflow_users                                                                                |
|    - user_password_{normalized username}                                                         |
|    - user_google_{normalized email}                                                              |
|    - google_subject_{Google subject}                                                             |
|    - username_{normalized username}                                                              |
|                                                                                                  |
|  live_metrics is overwrite-only and sampled at <= 1 Hz per desktop session.                      |
|  It must never contain raw features, frames, landmarks, or telemetry history.                   |
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| PUB/SUB                                                                                          |
|                                                                                                  |
|  session.completed is published only after the summary is durably saved.                        |
|  Event payloads contain identifiers and summary metadata only.                                   |
|  Event handlers must be idempotent.                                                              |
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| SECRET MANAGER                                                                                   |
|                                                                                                  |
|  - FOCUSFLOW_API_KEY                                                                              |
|  - credentials for Firestore / Pub/Sub                                                           |
|                                                                                                  |
|  No service-account JSON keys are downloaded to the desktop.                                     |
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| BUILD AND RELEASE                                                                                |
|                                                                                                  |
|  Source repo -> Cloud Build -> Artifact Registry -> Cloud Run                                    |
|                                                                                                  |
|  Cloud Storage static site                                                                       |
|    - public landing page                                                                         |
|    - release binaries by OS                                                                      |
|    - checksums and demo docs                                                                     |
|    - no secrets or internal logs                                                                 |
+--------------------------------------------------------------------------------------------------+

+--------------------------------------------------------------------------------------------------+
| OBSERVABILITY                                                                                    |
|                                                                                                  |
|  Cloud Logging + Cloud Monitoring                                                                |
|  - request correlation                                                                           |
|  - latency metrics                                                                               |
|  - resource usage                                                                                |
|  - reconnect recovery                                                                            |
+--------------------------------------------------------------------------------------------------+
```

## 5. Session flow at a glance

```text
1. Desktop creates a session with POST /v1/sessions.
2. Desktop opens WS /v1/ws/sessions/{session_id}?device_id=... .
3. Camera worker extracts 30-value face features per frame.
4. Sliding buffer builds raw sequence (30,30).
5. Cloud validates packet shape and enriches to (30,90).
6. GRU ONNX, TCN ONNX, and XGBoost produce component probabilities.
7. Late fusion combines them with weights 0.30 / 0.30 / 0.40.
8. Face-presence guard can suppress the final focus decision when needed.
9. Session summary and live metrics are written to Firestore.
10. session.completed is published after persistence.
11. Desktop calls POST /v1/sessions/{session_id}/complete.
```

## 6. Removed capabilities

These systems must stay absent from the architecture:

- active window title tracking
- process monitoring or process termination
- keystroke, mouse, CPM, or KPM collection
- productive/distracting keyword heuristics
- Hardcore Mode
- AI + OS heuristic fusion
- raw webcam frame upload or storage

## 7. Source-of-truth reminders

- `tracking.buffer.enrich_raw_sequence()` is the only accepted transform from `(30,30)` to `(30,90)`.
- The production model is the GRU + TCN + XGBoost late-fusion bundle in `models/late_fusion/`.
- The system stays vision-only even when identity flows are enabled.
- Cloud Run remains stateless; Firestore holds durable session truth.
- The desktop must reconnect WebSockets with exponential backoff and jitter.
