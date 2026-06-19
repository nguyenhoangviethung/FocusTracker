# FocusFlow UI Snapshot

Tài liệu này mô tả giao diện desktop FocusFlow AI hiện tại trong repo,
để lần sau mở lại không phải đọc toàn bộ code.

Phiên bản này phản ánh luồng **cloud-only** hiện tại:

- webcam và feature extraction chạy ở client;
- raw frame không gửi lên cloud;
- model quyết định cuối cùng nằm trên cloud;
- desktop chỉ hiển thị telemetry, preview cục bộ và lịch sử phiên.

## 0. Tổng quan nhanh

```text
PyQt6 desktop
  -> Auth dialog
  -> Sidebar shell
  -> Dashboard / Live Session / Vision Settings / History / App Settings
  -> Cloud API for stats, session lifecycle and inference
```

### 0.1 Sidebar hiện tại

```text
+----------------------+
| ▶ FocusFlow          |
| Not signed in        |
|                      |
| + New Session        |
| Dashboard            |
| Live Session         |
| Vision Settings      |
| History              |
| App Settings         |
|                      |
| System Status        |
| Ready for inference  |
| No active session    |
|                      |
| Light/Dark Toggle    |
| Logout               |
+----------------------+
```

Sidebar highlight đổi theo page đang mở. Nút `Logout` đóng app sau khi xóa
thông tin đăng nhập khỏi settings.

## 1. Đăng nhập

App mở bằng hộp thoại đăng nhập `FocusFlow Sign In`.

```text
+--------------------------------------------------------------+
| Sign in to FocusFlow                                         |
| Use username/password or Google sign-in to tag sessions.     |
|                                                              |
| [ Username / Password ]  [ Google OAuth ]                    |
|                                                              |
| Username      [ student01              ]                     |
| Password      [ ********              ]                     |
| Display name  [ Optional display name  ]                     |
| [ Sign in ] [ Create account ]                               |
|                                                              |
| [ Sign in with Google ]                                      |
|                                                              |
| [ Continue Offline ]                                         |
+--------------------------------------------------------------+
```

Ghi chú:

- `Continue Offline` chỉ bỏ qua đăng nhập, app vẫn mở.
- Khi đăng nhập thành công, sidebar sẽ hiển thị danh tính người dùng.
- `X` ở hộp thoại đăng nhập đóng app thay vì tự vào màn chính.

## 2. Dashboard

Dashboard là màn hình đầu tiên sau khi vào app.

```text
+------------------------------------------------------------------------------+
| Hello User                                             ★ PREMIUM             |
| Start a new session and track focus locally or through the cloud.            |
+------------------------------------------------------------------------------+
| Focus Time          Sessions             Avg Score            Day Streak      |
| 1h 20m              14                  78.2%               6               |
+------------------------------------------------------------------------------+
| POMODORO SETUP                         | RECENT ACTIVITY                     |
| Duration [25 Mins v]                   | Thu 18/06, 02:59 PM  1m focused... |
| [ START SESSION ]                      | Wed 17/06, 04:03 AM  4m focused... |
+------------------------------------------------------------------------------+
```

Hành vi:

- `Duration` lấy từ settings hiện tại.
- `START SESSION` mở màn Live Session.
- Recent activity được load từ cloud API khi có `auth_username`.
- Nếu chưa có dữ liệu, các số liệu để placeholder `-`.

Màu hiện tại của card summary là nền xanh gradient, còn các card còn lại theo
theme sáng/tối của app.

## 3. Live Session

Đây là màn chính khi đang chạy một session thật.

```text
+------------------------------------------------------------------------------+
|                                25:00                                          |
|                          STATUS: FOCUSED / DISTRACTED                         |
+--------------------------------------+---------------------------------------+
| AI CAMERA                            | 4-CLASS XGB FUSION                    |
| [ Hide / Show ]                      | Final XGB    : 77.7%                 |
| [ local preview frame ]              | Boost XGB    : 91.6%                 |
| Signal: 64.8% | face found | FPS     | Targeted XGB : 77.2%                 |
| State : AI=ENGAGED/DISTRACTED        |                                       |
| Cloud: connecting / session_created   | FOCUS TREND                           |
|                                      | [ chart ]                             |
+--------------------------------------+---------------------------------------+
|                          [ PAUSE ] [ END ]                                   |
+------------------------------------------------------------------------------+
```

### 3.1 Camera card

- preview là hình cục bộ từ webcam/video;
- preview có nút `Hide/Show`;
- `Signal` hiển thị focus score, face state và FPS;
- `State` hiển thị `AI=...`;
- `Cloud` hiển thị trạng thái session/network.

### 3.2 Model card

- tiêu đề `4-CLASS XGB FUSION`;
- ba dòng component: `Final XGB`, `Boost XGB`, `Targeted XGB`;
- chart `FOCUS TREND` ở bên dưới;
- `PAUSE` tạm dừng tracker;
- `END` kết thúc session.

### 3.3 Runtime behavior

- frames được giữ local;
- model quyết định cuối cùng nằm trên cloud;
- buffer chờ 30 frames trước khi có sample;
- `focus_score = P(class 2) + P(class 3)` chỉ là telemetry;
- final state lấy từ `argmax` của 4-class probabilities;
- `ENGAGED` map thành `FOCUSED`, còn `0/1` map thành `DISTRACTED`;
- nếu frame lỗi hoặc feature lỗi, frame đó bị bỏ qua trước khi vào buffer.

## 4. AI Vision Settings

Màn này là debug panel cho telemetry và camera feed.

```text
+--------------------------------------+---------------------------------------+
| CAMERA FEED                          | TELEMETRY                             |
| [ local preview ]                    | Throughput: 21.0 FPS                 |
|                                      | Client Loop Latency: 41.5 ms         |
|                                      | Model Inference Latency: 10.5 ms     |
|                                      | Cloud Round-Trip Latency: 150.3 ms   |
|                                      | Pitch: -0.3° | Yaw: -0.0°            |
|                                      | EAR [bar]                            |
|                                      | MAR [bar]                            |
|                                      | Confidence [bar]                     |
+--------------------------------------+---------------------------------------+
| MODEL OUTPUT: Confidence / VOTE                                             |
| [ START CAMERA DEMO ] [ STOP CAMERA ]                                       |
+------------------------------------------------------------------------------+
```

Lưu ý:

- `Client Loop Latency` là thời gian 1 vòng lặp client.
- `Model Inference Latency` là thời gian infer trả về từ cloud.
- `Cloud Round-Trip Latency` là send-to-receive của websocket.
- các số latency được cache trên UI để không nhảy về `--` nếu packet sau thiếu
  field.

## 5. History

History hiện có bố cục 2 cột:

- bên trái: report chi tiết và timeline;
- bên phải: recent history theo chiều dọc, có filter và bulk actions.

```text
+------------------------------------------------------------------------------+
| Session Report                                                               |
| Session summary and local history.                                           |
+----------------------+----------------------+--------------------------------+
| Focus Score          | Duration             | Distractions                   |
| 78.9%                | 10 mins              | 3 transitions                  |
+----------------------+----------------------+--------------------------------+
| Focus Timeline                        | Recent History                     |
| [ chart ]                             | Filters                            |
| Timeline:                             | [ search box ]                     |
| Min 01: 82.0%                         | [ All statuses v ]                 |
| Min 02: 76.1%                         | [ All focus v ]                    |
| Min 03: 79.8%                         | [ All durations v ]                |
| Report status: completed              | [ Select All ] [ Clear Selection ] |
|                                       | [ Delete Selected ] [ Reset ]      |
|                                       |                                    |
|                                       | 78.9% | 10 min | Open | Delete     |
|                                       | 73.4% | 10 min | Open | Delete     |
|                                       | 81.2% | 25 min | Open | Delete     |
+---------------------------------------+------------------------------------+
```

### 5.1 Filter hiện tại

- search theo timestamp, status, session id, score, duration;
- status filter: `All statuses`, `completed`, `pending`;
- focus filter: `All focus`, `>= 50%`, `>= 70%`, `>= 80%`;
- duration filter: `All durations`, `>= 5 mins`, `>= 15 mins`, `>= 30 mins`;
- `Select All` chỉ chọn các session đang hiển thị theo filter;
- `Clear Selection` bỏ chọn toàn bộ;
- `Delete Selected` xóa hàng loạt;
- `Open` mở report của một session;
- `Delete` xóa một session riêng lẻ.

### 5.2 Dữ liệu hiển thị

- history chỉ giữ các session meaningful;
- session login-only hoặc rỗng bị bỏ qua;
- nếu đang xem một session bị xóa, report details sẽ reset về trạng thái trống.

## 6. App Settings

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
|                                                                              |
| [ Save Settings ]                                                            |
+------------------------------------------------------------------------------+
```

Ghi chú:

- app hiện không còn cho chọn `local/cloud/hybrid` trong settings;
- inference mode được cố định về cloud;
- combobox và popup phải được style đúng theo theme sáng/tối;
- phần security cho đổi mật khẩu nếu đang đăng nhập bằng password account.

## 7. Theme rules

- `QComboBox` và popup `QListView` phải lấy style từ `ThemeManager`;
- dark/light toggle phải cập nhật cả widget lẫn popup;
- sidebar, card, text secondary, accent focus/warn đều đi theo palette;
- UI tránh dùng màu hard-code ngoài các chỗ rất cục bộ như badge hoặc preview.

## 8. Current runtime notes

- desktop luôn chạy cloud inference;
- camera preview không upload;
- model component telemetry có thể là `final_xgb`, `boost_xgb`, `targeted_xgb`;
- nếu component bị thiếu, UI giữ giá trị cũ thay vì nhảy về `0.0%`;
- nếu frame hoặc feature vector lỗi, frame đó bị drop trước khi vào buffer;
- crash trước đây ở AI Vision do `_format_latency()` đã được sửa.

## 9. File nên đọc khi sửa UI

```text
ui/app_window.py              shell + navigation + session lifecycle
ui/components/navigation.py   sidebar current labels and actions
ui/screens/home_page.py       dashboard
ui/screens/active_session_page.py
                              live session camera/model layout
ui/screens/ai_vision_page.py  telemetry panel
ui/screens/report_page.py     history, filters, bulk delete
ui/screens/settings_page.py    settings controls
ui/theme.py                   palette and combo box styles
```

