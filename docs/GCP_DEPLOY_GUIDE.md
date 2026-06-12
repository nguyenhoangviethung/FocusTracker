# GCP Deploy Guide

Guide này dùng Google Cloud Console là chính. Project phù hợp đã thấy trong
account:

```text
Project ID: my-thesis-496702
Project name: my-thesis
Billing: enabled
Region: asia-southeast1
```

Trước mỗi bước, nhìn project selector trên thanh đầu Console và xác nhận đang ở
`my-thesis-496702`

## Trạng thái đã kiểm tra ngày 12/06/2026

Các lệnh `gcloud` chỉ được dùng để đọc, không tạo hoặc sửa resource.

Đã tồn tại:

- project `my-thesis-496702`, project number `1093941638042`;
- Firestore Native `(default)` tại `asia-southeast1`;
- Artifact Registry repository `focusflow`;
- Pub/Sub topic `focusflow-session-events`;
- Secret Manager secret `focusflow-api-key`, version `1` đang enabled;
- các API Cloud Run, Cloud Build, Artifact Registry, Firestore, Pub/Sub và
  Secret Manager đã enabled.

Chưa tồn tại:

- Cloud Run service `focusflow-api`;
- image trong Artifact Registry repository;
- Cloud Build trigger.

Cloud Build hiện báo default service account là:

```text
1093941638042-compute@developer.gserviceaccount.com
```

Account này đã được cấp quyền build/deploy cần thiết và có `Service Account
User` trên `focusflow-api@my-thesis-496702.iam.gserviceaccount.com`.

## Phase A: Chuẩn bị project

### Step 1: Chọn project

1. Mở <https://console.cloud.google.com/>.
2. Nhấn project selector.
3. Chọn `my-thesis`.
4. Xác nhận Project ID là `my-thesis-496702`.

### Step 2: Enable APIs

Mở **APIs & Services > Library**:

<https://console.cloud.google.com/apis/library>

Enable lần lượt:

1. Cloud Run Admin API
2. Cloud Build API
3. Artifact Registry API
4. Firestore API
5. Pub/Sub API
6. Secret Manager API
7. Service Usage API
8. Cloud Logging API
9. Cloud Monitoring API

Nếu gặp quota `429`, chờ vài phút rồi enable tiếp, không bấm liên tục.

## Phase B: Storage và messaging

### Step 3: Tạo Firestore

1. Mở **Firestore Database**.
2. Nhấn **Create database**.
3. Chọn **Native mode**.
4. Database ID: `(default)`.
5. Chọn location gần Singapore/Cloud Run.
6. Chọn Production mode.

Không cần tạo collection bằng tay. API sẽ tạo `focusflow_sessions`.

### Step 4: Tạo Pub/Sub topic

1. Mở **Pub/Sub > Topics**.
2. Nhấn **Create topic**.
3. Topic ID: `focusflow-session-events`.
4. Không cần subscription ở phase đầu.

## Phase C: Container registry

### Step 6: Tạo Artifact Registry

1. Mở **Artifact Registry > Repositories**.
2. Nhấn **Create repository**.
3. Name: `focusflow`.
4. Format: Docker.
5. Mode: Standard.
6. Location type: Region.
7. Region: `asia-southeast1`.

Image path sau này:

```text
asia-southeast1-docker.pkg.dev/my-thesis-496702/focusflow/...
```

## Phase D: Secrets

### Step 7: Tạo API key

Sinh key local:

```bash
openssl rand -hex 32
```

Mở **Security > Secret Manager** và tạo:

```text
Secret name: focusflow-api-key
Value:       output của openssl
```

Lưu key vào password manager. Desktop cần cùng giá trị này qua environment
variable, không ghi vào git.

Khi cần điền `.env` local, tự chạy lệnh sau. Guide không tự đọc hoặc ghi secret
payload:

```bash
gcloud secrets versions access latest \
  --secret=focusflow-api-key \
  --project=my-thesis-496702
```

Điền output vào cả `FOCUSFLOW_API_KEY` và `FOCUSFLOW_CLOUD_API_KEY`.

## Phase E: IAM

### Step 9: Tạo service account API

Mở **IAM & Admin > Service Accounts**.

Tạo:

```text
Name: focusflow-api
ID:   focusflow-api
```

Grant roles:

- Cloud Datastore User
- Pub/Sub Publisher
- Secret Manager Secret Accessor

Không tạo hoặc download service account JSON key.

## Phase F: Cloud Build permissions

### Step 12: Xác định Cloud Build service account

1. Mở **Cloud Build > Settings** hoặc một build bất kỳ.
2. Xác định service account trigger sử dụng.
3. Mở IAM.
4. Grant cho Cloud Build service account:

- Artifact Registry Writer
- Cloud Run Admin
- Service Account User

Với `Service Account User`, scope nên cho phép impersonate:

- `focusflow-api`
## Phase F: Deploy API

### Step 13: Tạo API trigger

1. Mở **Cloud Build > Triggers**.
2. Create trigger.
3. Configuration path: `deploy/gcp/cloudbuild.yaml`.
4. Save.
5. Run trigger.

### Step 14: Kiểm tra Cloud Run API config

Mở `focusflow-api` và xác nhận:

```text
Region:       asia-southeast1
CPU:          2
Memory:       2 GiB
Concurrency:  4
Timeout:      3600 seconds
Min:          0
Max:          10
Service acct: focusflow-api
```

API service được public ở Cloud Run IAM layer để desktop không cần Google
service-account key. Application layer vẫn yêu cầu `X-API-Key`.

### Step 15: Health check

Copy API URL và chạy:

```bash
curl https://YOUR_API_URL/healthz
curl https://YOUR_API_URL/readyz
```

Mong đợi:

```json
{"status":"ok"}
{"status":"ready"}
```

Nếu `/readyz` fail, mở Cloud Run Logs và tìm model artifact/loading error.

Sau khi deploy, lấy URL mà không thay đổi cấu hình:

```bash
gcloud run services describe focusflow-api \
  --project=my-thesis-496702 \
  --region=asia-southeast1 \
  --format='value(status.url)'
```

Điền output vào `FOCUSFLOW_CLOUD_API_URL` trong `.env`.

## Phase I: End-to-end verification

### Step 16: Cấu hình desktop

Local terminal:

```bash
export FOCUSFLOW_CLOUD_API_KEY="<giá trị focusflow-api-key>"
python main.py
```

Trong Settings:

```text
Inference Mode: hybrid
Cloud API URL:  https://YOUR_API_URL
```

Start một session ngắn.

### Step 17: Kiểm tra Firestore

Mở Firestore collection `focusflow_sessions`.

Trong document session phải có:

- `device_id`
- `status`
- `started_at`
- `last_seen_at`
- sau End: `ended_at`
- `summary`
- `report_status`
- `report_started_at`
- `report_completed_at`

### Step 18: Kiểm tra Pub/Sub

Mở topic metrics của `focusflow-session-events`.

Sau End Session phải có publish count tăng.

### Step 19: Kiểm tra report metadata

Refresh Firestore document.

Mong đợi:

```text
report_status: completed
report_started_at: ...
report_completed_at: ...
```

## Phase G: Production hygiene

### Step 20: Budget

Mở **Billing > Budgets & alerts**.

Tạo alert:

- 50%
- 80%
- 100%

### Step 21: Monitoring

Tạo alert policy:

- Cloud Run 5xx;
- p95 latency cao;
- max instances gần giới hạn;
- Pub/Sub publish failures.

### Step 22: Không làm

- Không deploy vào `mcp-shared-bot-497416`.
- Không upload `.env`.
- Không download service account JSON key cho desktop.
- Không lưu API key trong `data/settings.json`.
- Không lưu raw frame hoặc feature stream vào Firestore.
