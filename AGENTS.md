# FOCUSFLOW AI DISTRIBUTED ARCHITECTURE SPECIFICATION

## 1. Product Direction

FocusFlow AI is a privacy-oriented distributed focus monitoring system.

The product has two runtime sides:

- **Edge desktop client:** PyQt6, OpenCV, and MediaPipe. It captures webcam
  frames, extracts a 30-value facial feature vector per frame, renders the
  local preview, and sends feature sequences to the cloud.
- **Google Cloud backend:** FastAPI on Cloud Run. It enriches raw sequences,
  runs the deployed GRU + TCN + XGBoost late-fusion model, stores session
  summaries, and records report completion metadata.

The project is intentionally **vision-only**.

### Removed capabilities

Do not implement or reintroduce:

- active window title tracking;
- process monitoring or process termination;
- keystroke, mouse, CPM, or KPM collection;
- productive/distracting keyword heuristics;
- Hardcore Mode;
- AI + OS heuristic fusion;
- raw webcam frame upload or storage.

The final focus decision comes only from the deployed late-fusion engagement
model and the face-presence guard.

## 2. Source Of Truth

When documents disagree, use this priority:

1. This `AGENTS.md`.
2. Runtime model metadata in `models/late_fusion/`.
3. `GUIDE.md`.
4. Existing implementation and older planning documents.

Do not replace the deployed model with an imagined architecture. The current
production model is:

```text
raw frame features:       30 values
raw temporal sequence:    (30, 30)
enriched model sequence:  (30, 90)
components:               GRU ONNX + TCN ONNX + XGBoost
selected weights:         0.30 + 0.30 + 0.40
selected threshold:       0.54
runtime:                  CPU, ONNXRuntime, XGBoost
```

`tracking.buffer.enrich_raw_sequence()` is the canonical transformation from
`(30, 30)` to `(30, 90)`. Both local tests and cloud inference must use it.

## 3. Target GCP Architecture

```text
┌──────────────────────────── EDGE DESKTOP ────────────────────────────┐
│ PyQt6 UI                                                            │
│   │                                                                 │
│   ├── Camera worker: OpenCV -> MediaPipe -> raw feature [30]        │
│   ├── Sliding buffer: 30 frames -> raw sequence [30, 30]            │
│   ├── Preview renderer: local frames only                           │
│   └── Network worker: session REST + telemetry WebSocket            │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ TLS
                                │ JSON v1 initially
                                │ no image/video payload
                                ▼
┌──────────────────────── GOOGLE CLOUD ────────────────────────────────┐
│ Cloud Run: focusflow-api                                            │
│   ├── FastAPI REST session lifecycle                                │
│   ├── WebSocket telemetry ingestion                                 │
│   ├── shape/schema/idempotency validation                           │
│   ├── enrich [30,30] -> [30,90]                                     │
│   ├── GRU + TCN + XGBoost CPU inference                             │
│   └── model-only focus decision                                     │
│                                                                     │
│ Firestore                                                           │
│   ├── session metadata and status                                   │
│   └── completed summary and report metadata                        │
│                                                                     │
│ Pub/Sub                                                             │
│   └── durable domain events: session.completed                      │
│                                                                     │
│ Secret Manager                                                      │
│   ├── FOCUSFLOW_API_KEY                                             │
│   └── credentials for Firestore / PubSub                            │
│                                                                     │
│ Artifact Registry + Cloud Build                                     │
│   └── build and deploy immutable container revisions                │
│                                                                     │
│ Cloud Storage public site                                           │
│   ├── static landing page for product/demo                          │
│   ├── public release artifacts by OS                                │
│   └── direct download links for Windows/macOS/Linux                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Initial deployment boundary

The first production slice keeps API gateway and CPU inference in one Cloud Run
service. This avoids an unnecessary network hop and keeps the thesis demo
operationally understandable.

Only split inference into another Cloud Run service after load tests prove that
model CPU or memory contention is the bottleneck. The shared protocol must not
change when that split happens.

### Cloud Run constraints

- WebSocket connections are subject to Cloud Run request timeout.
- The edge client must reconnect with exponential backoff and jitter.
- A Cloud Run instance is stateless; no session truth may live only in memory.
- Model artifacts are loaded once during application lifespan per instance.
- Blocking inference runs outside the asyncio event loop.
- Configure CPU to remain allocated while handling a connected request.
- Start with concurrency `4`; tune only from measured latency and memory data.

### Public release portal

For thesis/demo distribution, a public static website in Cloud Storage is
allowed and preferred over custom download auth when the goal is simplicity.

- Host the landing page as a static site in Cloud Storage.
- Place release binaries in a public bucket or public object path.
- Use Cloud Run only for the API and operational backend.
- Keep the landing page limited to product overview, version notes, and OS
  download links.
- Never place secrets, API keys, service-account files, or internal logs in the
  public bucket.
- Public artifacts may include only release builds, checksums, and demo docs.

## 4. Repository Structure

The repository evolves in place. Do not create a second desktop application or
duplicate UI tree.

```text
FocusTracker/
├── main.py                         # Single desktop entrypoint
├── ui/                             # Existing PyQt6 desktop UI
├── tracking/
│   ├── detector.py                 # MediaPipe feature extraction
│   ├── buffer.py                   # Canonical raw-to-enriched transform
│   ├── inference.py                # Local fallback and golden tests
│   └── tracker.py                  # Vision worker only
├── edge/
│   └── cloud_client.py             # REST lifecycle + WebSocket transport
├── shared/
│   ├── contracts.py                # Versioned Pydantic wire contracts
│   └── __init__.py
├── server/
│   ├── app.py                      # FastAPI application factory/lifespan
│   ├── config.py                   # Environment configuration
│   ├── api/
│   │   └── routes.py               # REST + WebSocket routes
│   ├── core/
│   │   └── inference.py            # Cloud model adapter
│   ├── repositories/
│   │   └── sessions.py             # Memory dev + Firestore production
│   └── services/
│       ├── event_publisher.py       # Pub/Sub adapter
│       └── report finalization is handled inline at session complete
├── deploy/gcp/
│   ├── Dockerfile.api
│   ├── cloudbuild.yaml
│   ├── env.example
│   └── CONSOLE_SETUP.md
├── models/late_fusion/             # Immutable runtime artifacts
└── tests/
    ├── server/
    └── test_logic_oonx.py
```

Legacy `tracking/os_tracker.py`, `tracking/hardcore.py`, and
`server/core/fusion.py` must not exist.

## 5. Protocol V1

Contracts live in `shared/contracts.py`. Contract changes require either
backward-compatible optional fields or a new protocol version.

### Session lifecycle

```text
POST /v1/sessions
GET  /v1/sessions/{session_id}
POST /v1/sessions/{session_id}/complete
WS   /v1/ws/sessions/{session_id}?device_id=...
POST /v1/inference
GET  /healthz
GET  /readyz
```

### Telemetry packet

```json
{
  "protocol_version": "1.0",
  "message_id": "uuid",
  "session_id": "uuid",
  "device_id": "stable-installation-id",
  "captured_at": "ISO-8601 UTC",
  "sequence_number": 42,
  "raw_feature_sequence": [[0.0]],
  "face_found": true,
  "configuration": {
    "engagement_threshold": 0.54
  }
}
```

The example abbreviates the tensor. Validation requires exactly `30` frames and
exactly `30` float values per frame.

### Inference response

The server returns:

- model name and version;
- final focus score and state;
- GRU, TCN, and XGBoost component probabilities;
- selected weights;
- decision trace;
- processing latency;
- original `message_id` for correlation.

Do not include frames, landmarks, window titles, process names, or input-device
activity in any protocol.

## 6. Security And Privacy

- Webcam frames remain in edge process memory and are never transmitted.
- Facial features are biometric-derived telemetry and are still sensitive.
  Never claim that they are anonymous or impossible to reconstruct.
- Use TLS only (`https`/`wss`) outside local development.
- Authenticate desktop requests using an API key during the thesis phase.
- Support two desktop identity flows for demo tracking: username/password and
  Google OAuth2. Both flows may set `user_id`, but neither replaces
  `X-API-Key`.
- Store password hashes with a strong salted hash and keep OAuth identities in
  Firestore via transactions.
- Store the API key in Secret Manager for cloud services and secure local
  configuration for the desktop client.
- Do not commit `.env`, credentials, service-account keys, or legacy report-workflow secrets.
- Production Cloud Run service accounts use least privilege.
- Do not download long-lived Google service-account JSON keys to the desktop.
- Add Firebase/Auth0/Identity Platform user authentication in a later phase if
  multi-user identity becomes part of the evaluated scope.

## 7. Storage And Events

### Firestore

Use Firestore Native mode. Store durable session data only:

```text
focusflow_sessions/{session_id}
  device_id
  user_id
  status
  started_at
  ended_at
  last_seen_at
  duration_seconds
  summary
  model_version
  report_status
  report_started_at
  report_completed_at
```

New Firestore document IDs must be deterministic and readable:

```text
session_{device_id}_{UTC timestamp with microseconds}
user_google_{normalized email}
user_password_{normalized username}
google_subject_{Google subject}
username_{normalized username}
```

Do not add random Firestore auto IDs. Existing legacy documents do not need
automatic migration; they may be deleted manually during thesis development.

Do not persist every 30 FPS feature sequence in Firestore. Realtime telemetry is
processed in flight. Persist only sampled metrics later if a measured research
requirement justifies the cost.

### Pub/Sub and report completion

- Publish `session.completed` after a summary is durably saved.
- Event payloads contain identifiers and summary metadata, not raw features.
- Keep event handlers idempotent.

## 8. Desktop Runtime Modes

During migration the desktop supports:

- `local`: current bundled model inference, no cloud required;
- `cloud`: edge feature extraction, cloud inference;
- `hybrid`: cloud preferred, local fallback after network timeout.

Production target is `cloud`. Thesis demos should keep `hybrid` available so a
network interruption does not destroy the demonstration.

The UI thread must never perform camera capture, inference, HTTP, or WebSocket
I/O directly.

## 9. GCP Deployment Standard

Default region for a Vietnam-based demo is `asia-southeast1` unless latency,
quota, or policy measurements justify another region.

Required Google Cloud services:

- Cloud Run
- Artifact Registry
- Cloud Build
- Firestore
- Pub/Sub
- Secret Manager
- Cloud Logging and Cloud Monitoring

Use a dedicated project such as `focusflow-thesis-<suffix>`. Do not deploy into
an unrelated shared project.

All deployable resources must be reproducible from checked-in Docker,
Cloud Build, and documented Console settings. Manual Console changes must be
recorded in `deploy/gcp/CONSOLE_SETUP.md`.

For public client distribution, use Cloud Storage static website hosting as the
download portal and keep the landing page in source control under
`deploy/gcp/static-site/`.

## 10. Implementation Phases

### Phase 1: Vision-only cleanup

- Remove OS tracker, keyword heuristics, Hardcore Mode, and their UI.
- Keep local late-fusion inference working.
- Replace the old OS card with component model telemetry.
- Update all documentation and dependencies.

Exit criterion: no runtime import or UI reference to removed capabilities.

### Phase 2: Cloud API vertical slice

- Add versioned contracts.
- Add FastAPI health, session, inference, and WebSocket endpoints.
- Load the late-fusion model once per Cloud Run instance.
- Add memory repository for tests and Firestore repository for production.

Exit criterion: an integration test submits `(30,30)` and receives component
probabilities from the real bundled model.

### Phase 3: Edge cloud transport

- Add a network worker with reconnect/backoff.
- Add stable device ID and session lifecycle.
- Add `local`, `cloud`, and `hybrid` modes.
- Keep preview frames strictly local.

Exit criterion: desktop demo survives a temporary network disconnect.

### Phase 4: Durable workflow

- Save summaries in Firestore.
- Publish `session.completed`.
- Record report completion metadata only.

Exit criterion: repeated completion calls are idempotent.

### Phase 5: Operations and evaluation

- Add Cloud Build deployment.
- Add structured logs, request correlation, latency metrics, and alerts.
- Benchmark bandwidth, p50/p95 latency, CPU, memory, reconnect recovery, and
  model throughput.
- Document measured results; do not present estimates as facts.

## 11. Engineering Rules

- Keep `python main.py` as the only desktop entrypoint.
- Use PyQt6 only for the desktop UI.
- Keep model runtime free of PyTorch.
- Reuse existing model artifacts and metadata.
- Prefer typed contracts and structured serialization.
- Never silently accept the wrong model shape.
- Never do blocking work in the UI or asyncio event loop.
- Add focused tests for every contract, repository, and inference boundary.
- Preserve offline fallback until cloud reliability has been demonstrated.
- Update this document whenever a system boundary or protocol changes.
