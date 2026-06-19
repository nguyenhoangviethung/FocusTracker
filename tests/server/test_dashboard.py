from __future__ import annotations

from server.api.dashboard_ui import render_dashboard_html
from server.api.routes import DashboardSnapshotCache
from server.app import app


def test_dashboard_routes_are_available() -> None:
    assert any(getattr(route, "path", None) == "/dashboard" for route in app.routes)

    html = render_dashboard_html("secret-key")
    assert "<!DOCTYPE html>" in html
    assert "FocusFlow Cloud Control Room" in html
    assert "Activity Trend" in html
    assert "Recent Sessions" in html
    assert "Session Inspector" in html
    assert "Deployment Snapshot" in html
    assert "Focus Distribution" in html
    assert "metricsChart" in html
    assert "focusDistChart" in html
    assert "refreshDashboard()" in html
    assert '"secret-key"' in html


def test_dashboard_snapshot_cache_batches_repeated_reads() -> None:
    cache = DashboardSnapshotCache(ttl_seconds=60.0)
    calls = 0

    def loader() -> dict:
        nonlocal calls
        calls += 1
        return {"recent_sessions": []}

    first, first_hit = cache.get_or_load(100, loader)
    second, second_hit = cache.get_or_load(100, loader)

    assert first == second
    assert first_hit is False
    assert second_hit is True
    assert calls == 1


def test_dashboard_snapshot_keeps_one_recent_session_per_user(monkeypatch) -> None:
    from server.api.routes import _dashboard_snapshot

    class DummyRepository:
        def list_recent(self, limit: int):
            return [
                {
                    "session_id": "session-new",
                    "user_id": "user-1",
                    "device_id": "device-1",
                    "status": "active",
                    "started_at": "2026-06-13T10:00:00Z",
                    "ended_at": None,
                },
                {
                    "session_id": "session-old",
                    "user_id": "user-1",
                    "device_id": "device-1",
                    "status": "completed",
                    "started_at": "2026-06-12T10:00:00Z",
                    "ended_at": "2026-06-12T10:30:00Z",
                },
                {
                    "session_id": "session-anon",
                    "user_id": "",
                    "device_id": "device-2",
                    "status": "active",
                    "started_at": "2026-06-13T09:00:00Z",
                    "ended_at": None,
                },
            ]

    class DummyUserRepository:
        def get_many(self, user_ids):
            return {
                "user-1": {
                    "user_id": "user-1",
                    "display_name": "Student 1",
                    "email": "student1@example.com",
                    "username": "student1",
                }
            }

    class DummyEngine:
        pass

    class DummySettings:
        environment = "development"
        repository_backend = "memory"
        event_backend = "logging"
        api_key = "secret"

    class DummyApp:
        state = type(
            "State",
            (),
            {
                "settings": DummySettings(),
                "session_repository": DummyRepository(),
                "user_repository": DummyUserRepository(),
                "inference_engine": DummyEngine(),
                "event_publisher": None,
            },
        )()

    class DummyRequest:
        app = DummyApp()

    snapshot = _dashboard_snapshot(DummyRequest(), limit=100)
    assert snapshot["recent_count"] == 2
    assert [item["session_id"] for item in snapshot["recent_sessions"]] == [
        "session-new",
        "session-anon",
    ]
