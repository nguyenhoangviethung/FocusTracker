# FocusFlow Documentation

Đọc theo thứ tự:

1. [ARCHITECTURE_GUIDE.md](ARCHITECTURE_GUIDE.md): hiểu hệ thống, model và
   trách nhiệm từng module.
2. [TEST_GUIDE.md](TEST_GUIDE.md): kiểm thử local, API, WebSocket và Docker.
3. [GCP_DEPLOY_GUIDE.md](GCP_DEPLOY_GUIDE.md): cấu hình Google Cloud Console
   và deploy API.
4. [DESKTOP_CLOUD_GUIDE.md](DESKTOP_CLOUD_GUIDE.md): kết nối desktop với
   Cloud Run và chạy demo end-to-end.
5. [AUTH_GUIDE.md](AUTH_GUIDE.md): cấu hình Google sign-in cho desktop client.
6. [../UI.md](../UI.md): snapshot UI hiện tại, navigation, theme Light/Dark,
   Active Session flow, và các bẫy UX/schema đã chốt.
7. [../GUIDE.md](../GUIDE.md): cách infer model production 4-class.

## Client snapshot nhanh

Các file nên đọc trước khi sửa desktop client:

```text
ui/theme.py                       palette Light/Dark + combo popup styles
ui/component_metrics.py           normalize component telemetry
ui/screens/home_page.py           Home, duration, recent activity
ui/screens/active_session_page.py Active Session, camera, model, trend, summary
ui/screens/settings_page.py       Settings, theme-aware combo boxes
tracking/tracker.py               camera/local/cloud/hybrid orchestration
tracking/inference.py             local 4-class fallback
edge/cloud_client.py              REST + WebSocket client
```

Model/UI hiện tại:

- model chính: `fixed_triple_xgb_fusion`;
- components: `final_xgb`, `boost_xgb`, `targeted_xgb`;
- decision: `argmax_4class`, không dùng threshold binary;
- `focus_score`: telemetry `P(medium) + P(high)` cho signal/trend;
- Light/Dark mode: dùng palette token, không hard-code màu control.

Tài liệu nguồn kiến trúc bắt buộc vẫn là
[AGENTS.md](../AGENTS.md). Guide giải thích cách vận hành, không thay đổi các
quyết định kiến trúc trong `AGENTS.md`.
