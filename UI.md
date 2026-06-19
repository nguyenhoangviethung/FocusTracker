# FocusFlow UI/UX And Scale Demo Specification

Tài liệu này là bản thiết kế giao diện và kịch bản demo cho đồ án FocusFlow.
Các sơ đồ dùng ký tự ASCII để có thể trình bày trực tiếp trong terminal,
Markdown viewer hoặc slide mà không phụ thuộc công cụ thiết kế.

## 0. Client snapshot hiện tại (2026-06-18)

Phần này ghi lại trạng thái client PyQt6 đang được chốt tạm thời. Nếu các mockup
cũ bên dưới còn nhắc GRU/TCN hoặc threshold binary, dùng section này làm nguồn
đọc nhanh cho UI hiện tại.

### 0.1 Navigation hiện tại

```text
-------------------+----------------------------------------------------------+
| FOCUSFLOW         | PAGE CONTENT                                             |
|                   |                                                          |
| Home              | Pomodoro setup, duration, recent activity                |
| Active            | Main running session: camera, 4-class model, trend       |
| AI Vision         | Vision diagnostics / local preview explanation           |
| Report            | Session summary and local/cloud completion history       |
| Settings          | Theme, camera, focus goals, sounds, security             |
|                   |                                                          |
| Theme toggle      | Light/Dark, palette-aware controls                       |
+-------------------+----------------------------------------------------------+
```

The desktop keeps `python main.py` as the only entrypoint. The UI is PyQt6 only.

### 0.2 Theme and color rules

The app supports both Light and Dark modes. Controls must use
`ThemeManager.palette()` tokens instead of hard-coded dark/light colors.

Important theme tokens:

```text
bg_app, bg_sidebar, bg_card
text_primary, text_secondary
accent_focus, accent_warn
btn_neutral, btn_neutral_hover
input, border
```

Known UX rule from the current implementation:

- `QComboBox` and its popup `QListView` must be styled explicitly from the
  current palette. The popup can otherwise keep a native dark palette while the
  app is in Light mode.
- `ui/theme.py` exposes `combo_box_stylesheet()` and
  `combo_popup_stylesheet()`.
- `HomePage` and `SettingsPage` apply those styles directly to each combo and
  `combo.view()`.
- Missing model component telemetry must render as `--`, not `0.0%`, because
  `0.0%` implies a real model output.

### 0.3 Home screen hiện tại

```text
+------------------------------------------------------------------------------+
| Hello User                                             PREMIUM                |
| Start a new session and track focus locally or through the cloud.            |
+------------------------------------------------------------------------------+
| Focus Time          Sessions             Avg Score            Day Streak      |
| <cloud/user stats if available, otherwise placeholders>                       |
+------------------------------------------------------------------------------+
| POMODORO SETUP                         | RECENT ACTIVITY                     |
| Duration [25 Mins v]                   | Thu 18/06, 02:59 PM  1m focused... |
| [ START SESSION ]                      | Wed 17/06, 04:03 AM  4m focused... |
+------------------------------------------------------------------------------+
```

Behavior:

- Duration comes from settings and can be changed before starting.
- Start Session passes `pomodoro_minutes` into the active session page.
- Recent activity is loaded in a background worker from the cloud auth/stats
  API when a username is present. If it cannot load, placeholders remain.

### 0.4 Active Session screen hiện tại

```text
+------------------------------------------------------------------------------+
|                               25:00                                          |
|                         STATUS: FOCUSED/DISTRACTED                           |
+--------------------------------------+---------------------------------------+
| AI CAMERA                            | 4-CLASS XGB FUSION                    |
| +----------------------------------+ | Final XGB    : 77.7%                 |
| | local webcam/video preview only  | | Boost XGB    : 91.6%                 |
| | optional landmarks               | | Targeted XGB : 77.2%                 |
| +----------------------------------+ |                                       |
| Signal: 64.8% | face found | FPS     | FOCUS TREND                           |
| State : AI=ENGAGED/DISTRACTED        | Guide line: 50% telemetry guide       |
| Cloud: connected/reconnecting/...    |                                       |
+--------------------------------------+---------------------------------------+
|                         [ PAUSE ] [ END ]                                    |
+------------------------------------------------------------------------------+
```

Runtime behavior:

- Frames remain local. The preview is never sent to cloud.
- Camera/tracker work happens outside the UI thread.
- The feature buffer waits for 30 frames before a sample is ready.
- Local/cloud responses use the same 4-class response shape where possible.
- `focus_score = P(class 2) + P(class 3)` is telemetry for signal/trend only.
- The final AI state comes from `prediction_4class = argmax(probabilities)`.
  Classes `2` and `3` map to `ENGAGED`; classes `0` and `1` map to
  `DISTRACTED`.
- The UI maps `ENGAGED` to final `FOCUSED`, unless the face-presence guard
  returns `NO_FACE`.

Component display safeguards:

- The canonical component keys are `final_xgb`, `boost_xgb`, `targeted_xgb`.
- `ui/component_metrics.py` also accepts legacy cloud keys
  `gru`, `tcn`, `xgboost` so a not-yet-redeployed server does not break the UI.
- If a packet lacks component data, the UI keeps the last valid component
  values. It does not reset all three rows to `0.0%`.
- If no component has ever been received, the UI shows `--`.

Latency display in AI Vision:

- `Client Loop Latency`: one tracker loop on the desktop, including camera read,
  feature extraction, buffering, and local bookkeeping.
- `Model Inference Latency`: model compute time only. In local mode this is the
  local inferencer time; in cloud mode this is the server processing time
  echoed back by the response.
- `Cloud Round-Trip Latency`: websocket send-to-receive time for cloud mode.
  It shows `--` when no cloud response has been received.

Recent client fixes:

- Cloud round-trip latency is cached on the AI Vision screen so it does not
  disappear on the next telemetry tick when that packet omits the field.
- The Report page now surfaces a `Focus Timeline` card before the summary
  panel, so the chart is visible earlier in the layout.
- Report history only keeps meaningful sessions with real duration and focus
  data. Empty login-only records are filtered out before render and before
  local cache write.
- Closing the auth dialog with `X` now exits the app instead of continuing into
  the main window when sign-in was not successful.

### 0.5 Settings screen hiện tại

```text
+------------------------------------------------------------------------------+
| Settings                                                                     |
+------------------------------------------------------------------------------+
| Appearance & Device Preferences                                              |
| Theme Mode: ( ) Light (x) Dark                                               |
| [ ] Auto-hide camera preview when starting session                           |
| [x] Show facial landmarks on camera preview                                  |
| Webcam Device: [ Webcam 0 (Default) v ]                                      |
|                                                                              |
| Focus & Work Goals                                                           |
| Daily Focus Goal:             [ 120 Mins v ]                                 |
| Default Pomodoro Duration:    [ 25 Mins v ]                                  |
|                                                                              |
| Notifications & Sound Alerts                                                 |
| [x] Play sound when session completes                                        |
| [ ] Play warning sound when distraction is detected                          |
|                                                                              |
| Security                                                                     |
| Current Password, New Password, Change Password                              |
+------------------------------------------------------------------------------+
```

Notes:

- Settings currently keeps a legacy `engagement_threshold` in settings storage
  for compatibility, but the 4-class model does not use it for inference.
- Theme changes must refresh both widgets and popup views.

### 0.6 Client-to-cloud runtime flow

```text
Start Session
  -> FocusSessionTracker starts camera worker
  -> network worker creates POST /v1/sessions
  -> websocket opens /v1/ws/sessions/{session_id}?device_id=...
  -> camera worker extracts 30-value raw features per frame
  -> FeatureSequenceBuffer builds raw sequence (30, 30)
  -> cloud/hybrid sends raw_feature_sequence only
  -> server enriches to (30, 90)
  -> fixed_triple_xgb_fusion returns 4-class probabilities
  -> UI renders focus score, argmax state, component probabilities
  -> End Session posts summary and report completion metadata
```

Hybrid mode:

- Prefer cloud response when available.
- Use local model when cloud is unavailable or reconnecting.
- Reconnect status is shown in the Cloud label.
- Bounded queues drop stale packets rather than growing memory.

### 0.7 Files to read first next time

```text
ui/theme.py                       palette + global styles + combo popup styles
ui/component_metrics.py           component schema normalization for UI
ui/screens/home_page.py           Home session start and recent activity
ui/screens/active_session_page.py running session UI and summary creation
ui/screens/settings_page.py       settings controls and theme-aware combos
tracking/tracker.py               camera/local/cloud/hybrid orchestration
tracking/inference.py             4-class local fallback inference
edge/cloud_client.py              REST + WebSocket transport
shared/contracts.py               v1 wire contracts
server/core/inference.py          cloud model adapter
```

## 1. Mục tiêu của buổi demo

Buổi demo phải chứng minh được bốn điểm:

1. Client xử lý webcam/video tại edge và không gửi ảnh lên cloud.
2. Cloud nhận chuỗi đặc trưng `(30, 30)` và trả kết quả late-fusion.
3. Hệ thống vẫn hoạt động khi mạng chập chờn nhờ reconnect và local fallback.
4. Cloud có thể phục vụ nhiều client đồng thời và tự tăng số instance.

Không dùng số lượng video để tuyên bố số người dùng production tuyệt đối.
Kết quả demo chỉ là benchmark trên cấu hình Cloud Run và máy phát tải đã ghi
trong báo cáo.

## 2. Dữ liệu demo

Nguồn video thực tế của repository:

```text
demo/Data/
```

Lưu ý: filesystem phân biệt chữ hoa và chữ thường. Không dùng `demo/data/`.

Repository hiện có 251 file MP4, tổng dung lượng khoảng 149 MB. Kịch bản chuẩn
chọn 100 video đầu tiên theo natural sort:

```text
demo/Data/01.mp4
demo/Data/02.mp4
...
demo/Data/100.mp4
```

Nếu một file hỏng hoặc không đọc được, runner phải ghi `SKIPPED`, chọn file hợp
lệ tiếp theo và vẫn giữ tổng số mẫu mục tiêu là 100.

Mỗi virtual client có:

```text
device_id  = demo-client-001 ... demo-client-100
video_path = một file MP4 riêng
session_id = do Cloud API cấp
```

## 3. Trải nghiệm demo tổng thể

```text
+----------------------+       TLS REST/WebSocket       +----------------------+
| PYQT6 CLIENT         | -----------------------------> | CLOUD RUN API        |
|                      |                                |                      |
| Video/Webcam         |  Only feature sequence        | Validate contract    |
| MediaPipe            |  shape = (30, 30)             | Enrich to (30, 90)   |
| Feature buffer       |  no image/video               | GRU + TCN + XGBoost  |
| Local fallback       | <----------------------------- | Return focus result  |
+----------+-----------+                                +----------+-----------+
           |                                                       |
           | local session UX                                      |
           v                                                       v
+----------------------+                                +----------------------+
| CLIENT REPORT        |                                | OBSERVABILITY        |
| Focus trend          |                                | Cloud Run metrics    |
| Session summary      |                                | Logs / Firestore     |
| Recent history       |                                | Pub/Sub metrics      |
+----------------------+                                +----------------------+
```

## 4. Client information architecture

```text
+-------------------+----------------------------------------------------------+
| FOCUSFLOW         | PAGE CONTENT                                             |
|                   |                                                          |
| [1] Home          | Home                                                     |
| [2] Active        | Active Session                                           |
| [3] AI Vision     | AI Vision Diagnostics                                    |
| [4] Report        | Session Report                                           |
| [5] Settings      | Settings                                                 |
|                   |                                                          |
| Theme: Dark       | Cloud: CONNECTED                                         |
+-------------------+----------------------------------------------------------+
```

Navigation rules:

- `Home` prepares a session or selects one demo video.
- `Active` is the primary presentation screen.
- `AI Vision` explains edge feature extraction.
- `Report` proves session lifecycle and persistence.
- `Settings` switches `local`, `cloud`, or `hybrid`.

## 4.1 Client sign-in

Vì client cần định danh người dùng trước khi tạo session, thêm một màn đăng
nhập Google trước `Home`.

```text
+------------------------------------------------------------------------------+
| FocusFlow AI                                                                 |
| Sign in with Google to tag sessions to a stable user identity.              |
+------------------------------------------------------------------------------+
| Google account                                                               |
| [ user@domain.edu                                                     ]      |
|                                                                              |
| [ Sign in with Google ]   [ Continue offline ]                               |
|                                                                              |
| Privacy: Google sign-in only returns user identity metadata.                 |
| Raw video never leaves the desktop.                                          |
+------------------------------------------------------------------------------+
```

Sau khi đăng nhập thành công, header toàn app hiển thị:

```text
Signed in as user@domain.edu  |  role=student  |  user_id=google-subject-id
```

`user_id` được đính vào session metadata và report, còn `X-API-Key` vẫn là
khóa ứng dụng dùng để gọi Cloud Run.

## 5. Client screen: Home

```text
+------------------------------------------------------------------------------+
| Ready to Focus?                                                              |
| Start a session and track focus locally or through the cloud.                |
+------------------------------------------------------------------------------+
| POMODORO SETUP                                                               |
|                                                                              |
| Duration                                             [ 25 Mins             v] |
| Demo video                                          [ Select .mp4 File     ] |
| Selected source                                     demo/Data/01.mp4         |
| Inference mode                                      HYBRID                   |
| Cloud status                                        READY                    |
|                                                                              |
|                         [ START SESSION ]                                    |
+------------------------------------------------------------------------------+
| Privacy: Frames stay on this device. Only numerical features are transmitted.|
+------------------------------------------------------------------------------+
```

UX states:

- `READY`: URL, key and model are available.
- `LOCAL ONLY`: cloud is disabled, local inference remains available.
- `RECONNECTING`: session may start in hybrid mode with local fallback.
- `INVALID VIDEO`: selected file cannot be opened.

## 6. Client screen: Active Session

Đây là màn hình chính khi demo một client thật.

```text
+------------------------------------------------------------------------------+
|                               09:42                                          |
|                           STATUS: FOCUSED                                    |
|                     Cloud source | Session active                            |
+--------------------------------------+---------------------------------------+
| AI CAMERA                            | LATE-FUSION MODEL                     |
|                                      |                                       |
| +----------------------------------+ | GRU       : 78.4%                     |
| |                                  | | TCN       : 74.1%                     |
| |      LOCAL VIDEO PREVIEW         | | XGBoost   : 81.7%                     |
| |      landmarks optional          | |                                       |
| |                                  | | Fused     : 78.9%                     |
| +----------------------------------+ | Source    : CLOUD                     |
|                                      | Latency   : 86 ms                      |
| Signal: 78.9% | face found | 29 FPS |                                       |
| AI state: FOCUSED                    | FOCUS TREND                           |
| Privacy: frame is not uploaded       | 100 |       __                        |
|                                      |  50 | __---/  \___--                  |
|                                      |   0 +---------------- time            |
+--------------------------------------+---------------------------------------+
|          [ PAUSE ]            [ END SESSION ]                                |
+------------------------------------------------------------------------------+
```

Màu trạng thái:

- `FOCUSED`: xanh lá.
- `DISTRACTED`: đỏ.
- `NO_FACE`: vàng/cam.
- `WARMING_UP`: xám.
- `PAUSED`: xanh dương nhạt.

Không nên hiển thị “cloud scale” bằng một con số tự bịa trên client. Client chỉ
hiển thị nguồn inference, latency của chính nó và tình trạng kết nối.

## 7. Client screen: Network degradation

```text
+------------------------------------------------------------------------------+
|                               09:16                                          |
|                        STATUS: FOCUSED                                       |
+------------------------------------------------------------------------------+
| Cloud: RECONNECTING in 4.2s                                                  |
| Inference source: LOCAL FALLBACK                                             |
| Last cloud latency: 121 ms                                                   |
| Pending telemetry queue: 1 / bounded                                         |
|                                                                              |
| The session continues. Old samples are dropped when the queue is full.       |
+------------------------------------------------------------------------------+
```

Luồng demo mất mạng:

1. Đang chạy mode `hybrid`, tắt Wi-Fi trong vài giây.
2. UI chuyển sang `RECONNECTING` và `LOCAL FALLBACK`.
3. Đồng hồ, camera và thống kê vẫn tiếp tục.
4. Bật lại mạng.
5. WebSocket reconnect và nguồn inference trở lại `CLOUD`.

## 8. Client screen: AI Vision Diagnostics

```text
+--------------------------------------+---------------------------------------+
| CAMERA FEED                          | EDGE TELEMETRY                        |
|                                      |                                       |
| +----------------------------------+ | Throughput       29.7 FPS             |
| |                                  | | Feature window   30 / 30              |
| |       FRAME IN LOCAL RAM         | | EAR              0.29                 |
| |       FACE LANDMARK VIEW         | | MAR              0.08                 |
| |                                  | | Pitch            -2.4 deg             |
| +----------------------------------+ | Yaw               4.1 deg              |
+--------------------------------------+---------------------------------------+
| MODEL OUTPUT                                                                 |
| GRU 78.4% | TCN 74.1% | XGBoost 81.7% | Fused 78.9% | FOCUSED              |
+------------------------------------------------------------------------------+
|                  [ START CAMERA DEMO ] [ STOP CAMERA ]                        |
+------------------------------------------------------------------------------+
```

Màn hình này dùng để giải thích privacy-by-design:

```text
Video frame -> MediaPipe -> 30 numbers/frame -> frame discarded
                                       |
                                       +-> 30-frame sequence -> cloud
```

## 9. Client screen: Session Report

```text
+------------------------------------------------------------------------------+
| Session Report                                                               |
| Session summary and local history.                                           |
+----------------------+----------------------+--------------------------------+
| Focus Score          | Duration             | Distractions                   |
| 78.9%                | 10 mins              | 3 transitions                  |
+----------------------+----------------------+--------------------------------+
| SESSION TIMELINE                              | RECENT HISTORY                |
|                                               |                               |
| Minute 01  82.0%                              | 78.9% | 10 min | Open         |
| Minute 02  76.1%                              | 73.4% | 10 min | Open         |
| Minute 03  79.8%                              | 81.2% | 10 min | Open         |
| ...                                           |                               |
|                                               |                               |
| Report status: completed                      |                               |
+-----------------------------------------------+-------------------------------+
```

## 10. Client screen: Settings

```text
+------------------------------------------------------------------------------+
| Settings                                                                     |
+------------------------------------------------------------------------------+
| APPEARANCE                                                                   |
| Theme                                      ( ) Light  (x) Dark                |
+------------------------------------------------------------------------------+
| AI VISION CONFIGURATION                                                      |
| Inference mode                            [ hybrid                         v] |
| Cloud API URL                             [ https://...run.app             ] |
| Camera distance scale                     [ 0.180                          ] |
|                                                                              |
| API key is loaded from environment and is never displayed.                   |
|                                                    [ SAVE SETTINGS ]          |
+------------------------------------------------------------------------------+
```

## 11. Server dashboard

Dashboard server là màn hình quan sát dành cho demo scale. Nó chỉ hiển thị
telemetry, session state và số liệu quan sát được, không hiển thị raw video.

```text
+------------------------------------------------------------------------------------------------+
| FOCUSFLOW CLOUD CONTROL ROOM                         LIVE | last 60 seconds                    |
+------------------+------------------+------------------+----------------------+----------------+
| Active clients   | Requests/sec     | p95 latency      | Error rate           | Face-found %    |
| 100              | 96.8             | 142 ms           | 0.2%                 | 91.5%           |
+------------------+------------------+------------------+----------------------+----------------+
| CLOUD RUN INSTANCES                    | CLIENT STATES                        | SESSION STATES |
|  8 |                         ___        | Focused       71                     | Active   100   |
|  6 |                  _______/           | Distracted    23                     | Ended     12   |
|  4 |          _______/                  | No face        6                     | Reconn     3   |
|  2 |  _______/                          | Reconnecting   0                     | Invalid    0   |
|  0 +-------------------------- time     |                                      |                |
+----------------------------------------+--------------------------------------+----------------+
| LATENCY DISTRIBUTION                   | THROUGHPUT                           | CLOUD HEALTH  |
| p50  73 ms                             | Sent       1,000 packets              | Ready   yes   |
| p95 142 ms                             | Success       998 packets              | API key yes   |
| p99 221 ms                             | Failed          2 packets              | Pub/Sub ok    |
+----------------------------------------+--------------------------------------+----------------+
```

### 11.1 camera wall preview

Đây là khu vực quan trọng nhất khi demo scale. Mỗi ô đại diện cho một camera
ảo hoặc một session replay, chỉ chứa thông số, không chứa hình ảnh. Ở local
chỉ render preview nhỏ; khi cần đủ 100 ô thì mở qua Cloud Run và truyền tham số
`?limit=100`:

```text
+------------------------------------------------------------------------------------------------+
| CAMERA WALL | each tile = device_id + fps + latency + face + state + queue                |
+------------------------------------------------------------------------------------------------+
| [001] FOC 28.9fps  81ms face=Y q=0 | [002] DIS 27.4fps  98ms face=Y q=0 | [003] FOC 29.1fps 76ms|
| [004] FOC 28.2fps  84ms face=Y q=0 | [005] NOF  0.0fps   -- face=N q=0 | [006] REC  1.0fps 130ms|
| [007] FOC 29.5fps  73ms face=Y q=0 | [008] DIS 26.7fps 101ms face=Y q=1 | [009] FOC 28.8fps 79ms|
| ... 91 tiles nữa theo cùng layout ...                                                         |
| [100] FOC 29.0fps  77ms face=Y q=0                                                            |
+------------------------------------------------------------------------------------------------+
```

Trong bản demo, dashboard có thể chuyển giữa:

```text
1. Overview
2. camera wall
3. Instance / latency charts
4. Session completion table
```

Mỗi tile nên có màu:

- xanh lá: `FOCUSED`
- đỏ: `DISTRACTED`
- vàng: `NO_FACE`
- xanh dương: `RECONNECTING`
- xám: `IDLE`

## 12. Kiến trúc demo 100 virtual clients

Không mở 100 cửa sổ PyQt6. Mỗi virtual client là một worker headless có cùng
contract và lifecycle với desktop thật.

```text
                         LOAD GENERATOR MACHINE
+------------------------------------------------------------------------------+
| demo/Data/01.mp4 -> MediaPipe -> VirtualClient-001 -> REST + WebSocket        |
| demo/Data/02.mp4 -> MediaPipe -> VirtualClient-002 -> REST + WebSocket        |
| ...                                                                          |
| demo/Data/100.mp4 -> MediaPipe -> VirtualClient-100 -> REST + WebSocket       |
|                                                                              |
| Scheduler | rate limiter | result collector | JSON/CSV benchmark report      |
+--------------------------------------+---------------------------------------+
                                       |
                                       | TLS, only `(30,30)` feature sequences
                                       v
+------------------------------------------------------------------------------+
| GOOGLE CLOUD RUN: focusflow-api                                               |
|                                                                              |
| +------------+  +------------+  +------------+       +------------+          |
| | Instance 1 |  | Instance 2 |  | Instance 3 |  ...  | Instance N |          |
| | model once |  | model once |  | model once |       | model once |          |
| +------+-----+  +------+-----+  +------+-----+       +------+-----+          |
|        +---------------+--------------------+----------------+                |
|                                |                                             |
|                      +---------+----------+                                  |
|                      | Firestore sessions |                                  |
|                      | Pub/Sub completion |                                  |
|                      +--------------------+                                  |
+------------------------------------------------------------------------------+
```

Mỗi virtual client thực hiện:

```text
1. POST /v1/sessions
2. Open /v1/ws/sessions/{session_id}?device_id=demo-client-NNN
3. Read its assigned MP4
4. Extract the same 30 raw features used by the desktop
5. Build one `(30,30)` sliding window
6. Send packet and wait for matching inference response
7. Record latency, state, score and errors
8. Repeat according to the configured send rate
9. POST /v1/sessions/{session_id}/complete
10. Close and write one client result
```

## 13. Hai tầng benchmark bắt buộc

### A. End-to-end video validation

Mục đích: chứng minh pipeline thật đọc được bộ 100 video.

```text
100 MP4 -> OpenCV/MediaPipe -> features -> cloud -> predictions -> summaries
```

Chạy với concurrency vừa sức máy local, ví dụ `5`, `10`, rồi `20`. Nếu chạy
100 MediaPipe workers cùng lúc trên một laptop, CPU/RAM local sẽ là nút thắt và
không phản ánh đúng khả năng Cloud Run.

Chỉ số cần ghi:

- số video đọc thành công;
- số video bị skip;
- FPS extract trung bình;
- số feature windows tạo ra;
- tỷ lệ API/WebSocket thành công;
- latency end-to-end bao gồm cả edge processing.

### B. Cloud scalability replay

Mục đích: đo riêng khả năng scale của server.

Trước buổi demo, chạy MediaPipe một lần để tạo fixture từ 100 video:

```text
demo/Data/*.mp4
        |
        v
demo/features/client-001.jsonl
demo/features/client-002.jsonl
...
demo/features/client-100.jsonl
```

Mỗi dòng JSONL chứa một `raw_feature_sequence` hợp lệ và `face_found`. Fixture
không chứa frame ảnh. Khi demo scale, 100 virtual clients replay các fixture
đồng thời nên tải local rất nhẹ và phần đo chủ yếu phản ánh network + server.

```text
100 precomputed feature streams
        |
        +-> 100 concurrent sessions
        +-> 100 WebSocket connections
        +-> configurable packets/second
        +-> deterministic payload and expected schema
```

Đây là cách benchmark đúng hơn so với decode 100 video đồng thời trên cùng máy.

## 14. Các mức tải trình diễn

Không nhảy thẳng lên 100 client. Dùng staircase test để nhìn thấy autoscaling:

```text
+------------+---------+----------+-------------------------------------------+
| Stage      | Clients | Duration | Mục tiêu                                  |
+------------+---------+----------+-------------------------------------------+
| Warm-up    |       1 |    30 s  | kiểm tra API key, model và contract        |
| Baseline   |       5 |    30 s  | lấy latency nền                           |
| Small      |      10 |    45 s  | chứng minh nhiều session                  |
| Medium     |      25 |    60 s  | bắt đầu quan sát concurrency              |
| High       |      50 |    60 s  | quan sát instance count                   |
| Peak       |     100 |    90 s  | benchmark mục tiêu                        |
| Cool-down  |       0 |    60 s  | quan sát scale-down                       |
+------------+---------+----------+-------------------------------------------+
```

Ramp-up nên có jitter `0-500 ms` giữa các client để mô phỏng người dùng thật.
Ngoài staircase test, có thể chạy spike test `10 -> 100` để trình bày phản ứng
khi lớp học cùng bắt đầu một lúc.

## 15. Tần suất gửi telemetry

Video 10 giây không đồng nghĩa phải gửi 30 request mỗi giây. Client thật gửi
một sequence đã gom 30 frames và chờ response trước khi gửi packet tiếp theo.

Profile đề xuất:

```text
REALTIME:  1 packet/client/second
STRESS:    2 packets/client/second
BURST:     5 packets/client/second trong tối đa 20 giây
```

Với 100 client:

```text
REALTIME ~= 100 inference packets/second
STRESS   ~= 200 inference packets/second
BURST    ~= 500 inference packets/second
```

Các con số trên là tải đầu vào mục tiêu, không phải throughput đã đạt. Báo cáo
phải dùng throughput thực đo từ client collector và Cloud Monitoring.

## 16. Điều kiện Cloud Run trước khi demo 100 clients

Cấu hình mục tiêu cho benchmark tối thiểu 100 clients trong
`deploy/gcp/cloudbuild.yaml`:

```text
CPU             2
Memory          2 GiB
Concurrency     8
Min instances   1
Max instances   16
```

WebSocket là request sống lâu và chiếm một concurrency slot. Với cấu hình trên,
capacity danh nghĩa chỉ khoảng:

```text
8 concurrent requests/instance * 16 instances = 128 active requests
```

Profile này có đủ slot danh nghĩa cho 100 WebSocket clients và 28 slot dự
phòng. Đây chưa phải bằng chứng throughput; trước demo vẫn phải chạy staircase
benchmark để xác nhận latency và CPU.

```text
PROFILE 100: concurrency=8, max-instances=16
             capacity danh nghĩa=128 connections

PROFILE 200: concurrency=8, max-instances=32
             capacity danh nghĩa=256 connections
```

Concurrency được giữ ở mức 8 vì model hiện tại khóa inference theo từng
instance. Tăng concurrency quá cao sẽ làm request xếp hàng thay vì tăng
throughput. Không tự thay cấu hình production ngay trong buổi demo; deploy
profile đã test trước và ghi rõ chi phí/quota.

Phải kiểm tra thêm:

- Cloud Run quota cho region `asia-southeast1`;
- max instances và budget alert;
- cold-start time do mỗi instance load model một lần;
- Secret Manager và service account;
- API `/readyz`;
- 100 session IDs tạo thành công;
- máy phát tải có đường truyền ổn định.

## 17. Server dashboard data sources

Dashboard không nên tự suy đoán instance count. Mỗi ô phải có nguồn dữ liệu:

```text
+----------------------+-------------------------------------------------------+
| UI metric            | Source                                                |
+----------------------+-------------------------------------------------------+
| Active clients       | load runner connected-client counter                  |
| Sent/success/failed  | load runner result collector                          |
| p50/p95/p99 latency  | timestamps measured by load runner                    |
| Request count        | Cloud Run request_count                               |
| Request latency      | Cloud Run request_latencies                           |
| Instance count       | Cloud Run container/instance metrics                  |
| CPU/memory           | Cloud Monitoring container metrics                    |
| Completed sessions   | Firestore query or completion counter                 |
| Published events     | Pub/Sub topic metrics                                 |
+----------------------+-------------------------------------------------------+
```

Trong phase đầu, “server dashboard” có thể là hai cửa sổ cạnh nhau:

```text
+-----------------------------------+------------------------------------------+
| LOCAL LOAD RUNNER TUI             | GOOGLE CLOUD MONITORING                  |
| active=100 success=99.8%          | instance count / latency / CPU           |
| p50=... p95=... p99=...           | request count / errors                   |
+-----------------------------------+------------------------------------------+
```

Cách này dễ triển khai và đáng tin hơn việc xây dashboard riêng nhưng số liệu
không nối với Cloud Monitoring.

## 18. Load runner TUI design

```text
+------------------------------------------------------------------------------+
| FocusFlow Scale Demo | target=https://...run.app | profile=REALTIME          |
+------------------------------------------------------------------------------+
| Stage: PEAK 100 clients     Elapsed: 00:47 / 01:30     Seed: 20250612         |
|                                                                              |
| Clients   [##################################################] 100/100        |
| Connected [################################################# ]  99/100        |
| Success   [################################################# ]  99.8%          |
+------------------------------------------------------------------------------+
| PACKETS              | LATENCY             | CLOUD RESPONSE STATES           |
| Sent       4,702      | p50       78 ms     | FOCUSED        3,341            |
| Success    4,694      | p95      151 ms     | DISTRACTED     1,102            |
| Failed         8      | p99      248 ms     | NO_FACE          251            |
| Reconnects      3     | max      611 ms     | validation_err     0            |
+------------------------------------------------------------------------------+
| RECENT EVENTS                                                                |
| 14:05:31 client-043 reconnected in 2.1s                                      |
| 14:05:33 client-087 response 200 ms                                          |
| 14:05:35 stage remains healthy                                               |
+------------------------------------------------------------------------------+
| [Q] stop gracefully   Results: demo/results/run-20250612T140400.json          |
+------------------------------------------------------------------------------+
```

TUI phải cập nhật tại chỗ, không in một dòng log cho mỗi packet vì 100 client sẽ
làm terminal khó đọc. Log chi tiết ghi vào file riêng.

## 19. Kịch bản trình bày trước hội đồng

### Cảnh 1: Một client thật

Thời lượng: khoảng 2 phút.

```text
Người trình bày:
"Đây là video mẫu được xử lý tại edge. Khung hình chỉ xuất hiện ở ứng dụng
desktop. Cloud chỉ nhận ma trận đặc trưng 30x30."
```

Thao tác:

1. Mở desktop ở mode `hybrid`.
2. Chọn `demo/Data/01.mp4`.
3. Start session.
4. Chỉ vào FPS, face state và ba component model.
5. Chỉ vào `Source: CLOUD`.
6. Mở Cloud Run log của đúng request.
7. End session và mở report.

### Cảnh 2: Chứng minh privacy

Thời lượng: khoảng 45 giây.

1. Mở AI Vision Diagnostics.
2. Giải thích frame nằm ở client.
3. Mở một telemetry payload mẫu.
4. Chỉ ra payload có `(30,30)` float và không có image bytes/base64.

### Cảnh 3: 100 video, end-to-end

Thời lượng: khoảng 2 phút.

1. Chạy validation với 100 video và concurrency đã benchmark trước.
2. TUI hiển thị tiến độ `processed/100`.
3. Mở báo cáo tổng hợp số video thành công, FPS và lỗi.
4. Không cần chờ toàn bộ nếu đã có report pre-run; có thể chạy một subset live
   và đối chiếu report của lần chạy đủ 100 video.

### Cảnh 4: Scale cloud bằng replay

Thời lượng: khoảng 3 phút.

1. Mở Cloud Monitoring ở biểu đồ instance count, latency và request count.
2. Chạy staircase `1 -> 5 -> 10 -> 25 -> 50 -> 100`.
3. Đặt TUI load runner cạnh Cloud Monitoring.
4. Chỉ ra active clients, success rate, p95 và instance count tăng.
5. Sau peak, stop graceful và kiểm tra 100 session completions.

### Cảnh 5: Network resilience

Thời lượng: khoảng 1 phút.

1. Chạy một desktop client hybrid.
2. Ngắt mạng ngắn.
3. Chỉ ra local fallback và reconnect.
4. Khôi phục mạng và quan sát source trở lại cloud.

## 20. Cách dùng video 10 giây trong load test dài

Không decode lặp lại 100 video trong peak test. Quy trình đúng:

```text
PREPARE ONCE
video 10 s -> feature windows -> JSONL fixture

REPLAY MANY
JSONL fixture -> loop from first window -> send at configured rate
```

Khi fixture đi đến cuối trong một session 90 giây:

1. quay lại window đầu;
2. tạo `message_id` mới;
3. tăng `sequence_number`;
4. giữ nguyên `device_id` và `session_id`;
5. ghi `fixture_loop_count` vào kết quả benchmark local.

Việc lặp fixture phục vụ kiểm thử tải, không được dùng để tính độ chính xác mô
hình như thể đó là 90 giây dữ liệu độc lập.

## 21. CLI dự kiến cho bộ công cụ demo

Các command dưới đây là contract UX cho phần implementation sau:

```bash
# Kiểm tra và chọn 100 video hợp lệ
python -m demo.validate_videos \
  --input demo/Data \
  --limit 100 \
  --natural-sort \
  --output demo/results/video-manifest.json

# Extract feature fixture một lần
python -m demo.extract_features \
  --manifest demo/results/video-manifest.json \
  --output demo/features \
  --workers 5

# End-to-end test từ video thật
python -m demo.run_video_clients \
  --manifest demo/results/video-manifest.json \
  --clients 100 \
  --concurrency 10 \
  --api-url "$FOCUSFLOW_CLOUD_API_URL" \
  --api-key-env FOCUSFLOW_CLOUD_API_KEY

# Pure cloud scale replay
python -m demo.run_scale \
  --features demo/features \
  --stages 1:30,5:30,10:45,25:60,50:60,100:90 \
  --rate 1 \
  --seed 20250612 \
  --api-url "$FOCUSFLOW_CLOUD_API_URL" \
  --api-key-env FOCUSFLOW_CLOUD_API_KEY
```

API key chỉ đọc từ environment. Không đưa secret vào command history, fixture,
JSON report hoặc ảnh chụp màn hình.

## 22. Cấu trúc output benchmark

```text
demo/
|-- Data/                         # MP4 source, đã tồn tại
|-- features/                     # generated, no images
|   |-- client-001.jsonl
|   |-- ...
|   `-- client-100.jsonl
`-- results/
    |-- video-manifest.json
    |-- run-20250612T140400.json
    |-- run-20250612T140400.csv
    `-- run-20250612T140400-summary.txt
```

Summary mẫu:

```text
FocusFlow Scale Benchmark
-------------------------
Git commit:             <commit SHA>
Cloud Run revision:     <revision>
Image digest:           <sha256>
Region:                 asia-southeast1
Runner machine:         <CPU/RAM/OS>
Profile:                REALTIME
Target clients:         100
Connected clients:      <measured>
Packets sent:           <measured>
Success rate:           <measured>
p50/p95/p99 latency:    <measured>
Reconnect count:        <measured>
Cloud instance peak:    <measured from Monitoring>
Run started/ended UTC:  <timestamps>
```

Không điền số giả vào report mẫu. Mọi trường `<measured>` phải được lấy từ lần
chạy thực tế.

## 23. Tiêu chí demo thành công

Ngưỡng đề xuất, cần chốt lại sau benchmark thử:

```text
+-----------------------------+-----------------------------------------------+
| Tiêu chí                    | Điều kiện đề xuất                             |
+-----------------------------+-----------------------------------------------+
| Video manifest              | đủ 100 file hợp lệ                            |
| Contract validation         | 100% packet đúng schema                       |
| Session creation            | >= 99% thành công                             |
| Inference success           | >= 99% packet có response                     |
| p95 latency REALTIME        | < 500 ms                                      |
| Unhandled server 5xx        | < 1%                                          |
| Session completion          | >= 99/100                                     |
| Raw image uploaded          | 0                                             |
| Client queue                | bounded, không tăng vô hạn                     |
| Cloud autoscaling evidence  | instance metric thay đổi khi tải tăng         |
+-----------------------------+-----------------------------------------------+
```

Nếu không đạt ngưỡng, báo đúng bottleneck:

- runner CPU cao: giảm MediaPipe concurrency hoặc dùng fixture replay;
- network packet loss: chạy lại trên mạng ổn định hoặc dùng local Cloud Run
  proxy trong rehearsal;
- Cloud Run đạt max instances: tăng max sau khi kiểm tra quota/budget;
- latency tăng theo concurrency: giảm concurrency/instance;
- cold start cao: warm-up trước peak và báo riêng cold/warm latency.

## 24. UX khi load test gặp lỗi

```text
+------------------------------------------------------------------------------+
| STAGE DEGRADED                                                               |
| 92/100 connected | 8 reconnecting | p95 681 ms | errors 1.7%                 |
|                                                                              |
| Suggested diagnosis: Cloud Run max capacity or unstable runner network.      |
| Test continues for evidence. No result is hidden.                            |
|                                                                              |
| [C] continue   [S] stop gracefully   [D] dump diagnostics                    |
+------------------------------------------------------------------------------+
```

Runner phải stop gracefully:

1. dừng tạo packet mới;
2. complete các session còn kết nối;
3. đóng WebSocket;
4. flush result file;
5. in đường dẫn report;
6. trả exit code khác `0` nếu không đạt acceptance criteria.

## 25. Demo khi Internet không ổn định

Chuẩn bị ba lớp bằng chứng:

```text
LIVE
  Chạy desktop và một staircase ngắn.

RECORDED EVIDENCE
  Video quay màn hình một lần chạy đủ 100 clients cùng Cloud Monitoring.

SIGNED ARTIFACTS
  JSON/CSV report có git SHA, revision, image digest và timestamps.
```

Nếu mạng hỏng trong buổi bảo vệ:

1. không giả vờ đây là kết quả live;
2. trình bày report và recording của lần benchmark gần nhất;
3. chạy local Docker với fixture để chứng minh contract và runner;
4. giải thích phần cloud bằng revision/image digest đã lưu.

## 26. Checklist trước giờ demo

```text
[ ] Git commit trong report khớp source đang trình bày
[ ] Cloud Run revision khớp image digest cần demo
[ ] /readyz trả {"status":"ready"}
[ ] API key có trong environment, không xuất hiện trên màn hình
[ ] 100 video manifest hợp lệ
[ ] 100 feature fixtures đã tạo
[ ] Chạy thử 1 client end-to-end
[ ] Chạy thử stage 10 clients
[ ] Cloud Monitoring dashboard đã mở đúng project/region
[ ] Firestore collection đã mở
[ ] Budget alert và max instances đã kiểm tra
[ ] Report directory còn đủ dung lượng
[ ] Screen recording dự phòng đã sẵn sàng
[ ] Desktop đang ở mode hybrid
[ ] Tắt notification và che thông tin cá nhân
```

## 27. Câu kết khi trình bày

```text
"Một client thật chứng minh pipeline edge-to-cloud và privacy.
Một trăm feature streams được tạo từ một trăm video thật chứng minh hành vi
đa client. Staircase benchmark cùng Cloud Monitoring cho thấy hệ thống tăng
instance theo tải. Các con số được trình bày là kết quả đo của revision này,
không phải ước lượng lý thuyết."
```

## 28. Phạm vi implementation tiếp theo

Thiết kế này dự kiến cần các module:

```text
demo/
|-- __init__.py
|-- validate_videos.py
|-- extract_features.py
|-- virtual_client.py
|-- run_video_clients.py
|-- run_scale.py
|-- metrics.py
|-- tui.py
`-- schemas.py
```

Không thêm 100 PyQt windows và không gửi video lên server. Load runner phải tái
sử dụng `shared/contracts.py`, logic feature extraction hiện có và lifecycle
REST/WebSocket hiện tại để kết quả demo đại diện đúng cho ứng dụng.
