# Google Cloud Console Setup

The local account has a likely thesis project:

```text
project ID: my-thesis-496702
name:       my-thesis
billing:    enabled
```

Confirm this project in the Console project selector before continuing. The
currently configured CLI default `mcp-shared-bot-497416` looks shared and must
not be used for FocusFlow.

Recommended region: `asia-southeast1`.

## 1. Create The Project

1. Open [Manage resources](https://console.cloud.google.com/cloud-resource-manager).
2. Select **Create project**.
3. Use a name such as `FocusFlow Thesis`.
4. Attach a billing account.
5. Copy the generated project ID. All later steps must show this project in the
   project selector.

## 2. Enable APIs

Open **APIs & Services > Library** and enable:

- Cloud Run Admin API
- Cloud Build API
- Artifact Registry API
- Firestore API
- Pub/Sub API
- Secret Manager API
- Service Usage API
- Cloud Logging API
- Cloud Monitoring API

Direct page:
[API Library](https://console.cloud.google.com/apis/library)

## 3. Create Artifact Registry

1. Open **Artifact Registry > Repositories**.
2. Create repository:
   - Name: `focusflow`
   - Format: Docker
   - Mode: Standard
   - Region: `asia-southeast1`
3. Keep immutable tags disabled during development; enable them for a release
   repository later.

## 4. Create Firestore

1. Open **Firestore > Databases**.
2. Create database in **Native mode**.
3. Database ID: `(default)`.
4. Select a location close to Cloud Run. Prefer a compatible Singapore/Asia
   location shown by the Console.
5. Do not create a collection manually. The API creates
   `focusflow_sessions` on first write.

Firestore stores durable session metadata and summaries only. It must not store
every feature sequence.

## 5. Create Pub/Sub Topic

1. Open **Pub/Sub > Topics**.
2. Create topic `focusflow-session-events`.
3. Leave the default subscription disabled for now unless another service is
   already deployed.
4. Keep message retention at the default during development.

## 6. Create Secret

1. Open **Security > Secret Manager**.
2. Create secret `focusflow-api-key`.
3. Generate a random value of at least 32 bytes locally.
4. Add it as version `1`.
5. Never paste the API key into source code or Cloud Build substitutions.

## 7. Create Cloud Run Service Account

1. Open **IAM & Admin > Service Accounts**.
2. Create `focusflow-api`.
3. Grant:
   - Cloud Datastore User
   - Pub/Sub Publisher
   - Secret Manager Secret Accessor
4. Do not create or download JSON keys.

The Cloud Build service account also needs:

- Artifact Registry Writer
- Cloud Run Admin
- Service Account User on `focusflow-api`

Grant these through IAM after identifying the service account used by your
Cloud Build trigger.

## 8. Create The API Cloud Build Trigger

1. Open **Cloud Build > Triggers**.
2. Connect the GitHub repository.
3. Create a push trigger for the deployment branch.
4. Configuration type: Cloud Build configuration file.
5. Location: `deploy/gcp/cloudbuild.yaml`.
6. Run the trigger manually once.

## 9. Verify Cloud Run

After deployment:

1. Open **Cloud Run > focusflow-api**.
2. Confirm:
   - Region: `asia-southeast1`
   - CPU: 2
   - Memory: 2 GiB
   - Concurrency: 4
   - Request timeout: 3600 seconds
   - Service account: `focusflow-api`
   - Secret mapping: `FOCUSFLOW_API_KEY`
3. Open the service URL plus `/healthz`.
4. Expected response: `{"status":"ok"}`.
5. Check **Logs** for model initialization errors.

The service is unauthenticated at the Cloud Run IAM layer because the desktop
does not hold a Google service-account key. Application requests are protected
by `X-API-Key`. This is acceptable for the thesis slice, but a production
multi-user product should move to Identity Platform or another user identity
provider.

Complete a short test session and verify:

- a Firestore session document has a summary;
- Pub/Sub contains a `session.completed` publish metric;
- the Firestore document contains `report_status=completed`;
- the Firestore document contains `report_started_at` and
  `report_completed_at`.

## 12. Budget And Alerts

1. Open **Billing > Budgets & alerts**.
2. Create a low monthly thesis budget with alerts at 50%, 80%, and 100%.
3. In Cloud Monitoring, create alerts for:
   - Cloud Run 5xx responses;
   - p95 request latency;
   - instance count near max;
   - Pub/Sub undelivered messages once a subscription exists.

## 13. WebSocket Note

Cloud Run WebSockets still follow the configured request timeout. The desktop
client must reconnect and resume with a new connection. Do not treat a
WebSocket connection as durable session storage.
