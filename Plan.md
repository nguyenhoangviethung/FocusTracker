# FocusFlow Distributed Implementation Plan

`AGENTS.md` is the architecture source of truth.

## Phase 1: Vision-only cleanup

- Remove OS tracking, keyword heuristics, and Hardcore Mode.
- Keep the local GRU + TCN + XGBoost pipeline operational.
- Show component probabilities and focus trend in the desktop UI.

## Phase 2: Cloud API

- Version contracts in `shared/contracts.py`.
- Run FastAPI and CPU inference on Cloud Run.
- Use Firestore for session metadata and summaries.
- Publish `session.completed` to Pub/Sub.

## Phase 3: Edge transport

- Support `local`, `cloud`, and `hybrid` inference modes.
- Use REST for session lifecycle and WebSocket for telemetry.
- Reconnect with exponential backoff.
- Never upload raw frames.

## Phase 4: Async reports

- Move AI Coach and mentor email from desktop to a Cloud Run worker.
- Use Cloud Tasks for retry and idempotency.
- Store generated feedback and delivery status in Firestore.

## Phase 5: Operations

- Build and deploy through Cloud Build and Artifact Registry.
- Measure p50/p95 latency, throughput, bandwidth, memory, and reconnect time.
- Add dashboards, alerts, budgets, and a documented thesis evaluation.
