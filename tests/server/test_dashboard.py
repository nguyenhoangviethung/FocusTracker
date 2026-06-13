from __future__ import annotations

from fastapi.testclient import TestClient

from server.api.routes import DashboardSnapshotCache
from server.app import app


def test_dashboard_routes_are_available() -> None:
    with TestClient(app) as client:
        html = client.get("/dashboard")
        assert html.status_code == 200
        assert "FocusFlow AI Server Dashboard" in html.text
        assert "Camera wall" in html.text
        assert "Session history" in html.text
        assert "live_metrics" in html.text
        assert "setInterval(() => window.refreshDashboard().catch(console.error), 3000)" in html.text
        assert "/dashboard/api/summary?limit=100" in html.text

        summary = client.get("/dashboard/api/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert "ready" in payload
        assert "recent_sessions" in payload
        assert "repository_backend" in payload
        assert payload["firestore_query_limit"] == 24
        assert payload["dashboard_cache_seconds"] == 3.0


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
