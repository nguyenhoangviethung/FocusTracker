from __future__ import annotations

import asyncio
from datetime import timedelta

from server.api.dashboard_ui import render_dashboard_html
from server.api.routes import (
    DashboardSnapshotCache,
    dashboard_batch_delete_sessions,
    dashboard_clear_all_sessions,
    dashboard_clear_stale_sessions,
    dashboard_delete_session,
)
from server.app import app
from shared.contracts import utc_now


class DummyCache:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


class DummySettings:
    environment = "development"
    repository_backend = "memory"
    event_backend = "logging"
    api_key = "secret"
    stale_session_timeout_seconds = 600
    stale_session_cleanup_interval_seconds = 60


class MutableRepository:
    def __init__(self, records: list[dict]) -> None:
        self.records = {record["session_id"]: dict(record) for record in records}

    def get(self, session_id: str):
        record = self.records.get(session_id)
        return dict(record) if record else None

    def list_recent(self, limit: int):
        records = sorted(
            self.records.values(),
            key=lambda record: str(record.get("started_at", "")),
            reverse=True,
        )
        return [dict(record) for record in records[:limit]]

    def delete(self, session_id: str) -> bool:
        return self.records.pop(session_id, None) is not None

    def expire_stale(self, cutoff, limit: int = 500) -> list[str]:
        from server.repositories.sessions import _expire_record_if_stale

        expired: list[str] = []
        now = utc_now()
        for record in self.list_recent(limit):
            stored = self.records[record["session_id"]]
            if _expire_record_if_stale(stored, cutoff, now):
                expired.append(record["session_id"])
        return expired


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


class DummyApp:
    def __init__(self, repository, cache: DummyCache | None = None) -> None:
        self.state = type(
            "State",
            (),
            {
                "settings": DummySettings(),
                "session_repository": repository,
                "user_repository": DummyUserRepository(),
                "inference_engine": DummyEngine(),
                "event_publisher": None,
                "dashboard_cache": cache,
            },
        )()


class DummyRequest:
    def __init__(self, repository, cache: DummyCache | None = None) -> None:
        self.app = DummyApp(repository, cache)


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
    assert "/dashboard/api/sessions/clear-all" in html
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


def test_dashboard_snapshot_keeps_all_recent_sessions_for_delete_operations() -> None:
    from server.api.routes import _dashboard_snapshot

    repository = MutableRepository(
        [
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
    )

    snapshot = _dashboard_snapshot(DummyRequest(repository), limit=100)

    assert snapshot["recent_count"] == 3
    assert [item["session_id"] for item in snapshot["recent_sessions"]] == [
        "session-new",
        "session-anon",
        "session-old",
    ]


def test_dashboard_delete_session_deletes_record_and_clears_cache() -> None:
    repository = MutableRepository([{"session_id": "s1", "started_at": "2026-06-19T01:00:00Z"}])
    cache = DummyCache()

    result = asyncio.run(
        dashboard_delete_session(
            DummyRequest(repository, cache),
            "s1",
            x_api_key="secret",
        )
    )

    assert result == {"status": "deleted", "session_id": "s1"}
    assert repository.get("s1") is None
    assert cache.cleared is True


def test_dashboard_batch_delete_deletes_existing_ids_only() -> None:
    repository = MutableRepository(
        [
            {"session_id": "s1", "started_at": "2026-06-19T01:00:00Z"},
            {"session_id": "s2", "started_at": "2026-06-19T02:00:00Z"},
        ]
    )
    cache = DummyCache()

    result = asyncio.run(
        dashboard_batch_delete_sessions(
            DummyRequest(repository, cache),
            {"session_ids": ["s1", "missing", "s2"]},
            x_api_key="secret",
        )
    )

    assert result == {"status": "deleted", "deleted_ids": ["s1", "s2"]}
    assert repository.records == {}
    assert cache.cleared is True


def test_dashboard_clear_stale_expires_only_old_active_sessions() -> None:
    old_started_at = (utc_now() - timedelta(minutes=20)).isoformat()
    fresh_started_at = utc_now().isoformat()
    repository = MutableRepository(
        [
            {"session_id": "old-active", "started_at": old_started_at, "ended_at": None},
            {"session_id": "fresh-active", "started_at": fresh_started_at, "ended_at": None},
            {"session_id": "old-complete", "started_at": old_started_at, "ended_at": old_started_at},
        ]
    )

    result = asyncio.run(
        dashboard_clear_stale_sessions(
            DummyRequest(repository, DummyCache()),
            x_api_key="secret",
        )
    )

    assert result["expired_ids"] == ["old-active"]
    assert repository.records["old-active"]["status"] == "cancelled"
    assert repository.records["old-active"]["ended_at"] is not None
    assert repository.records["old-active"]["cancellation_reason"] == "stale_timeout"
    assert set(repository.records) == {"old-active", "fresh-active", "old-complete"}


def test_dashboard_clear_all_deletes_every_recent_session() -> None:
    repository = MutableRepository(
        [
            {"session_id": "s1", "started_at": "2026-06-19T01:00:00Z"},
            {"session_id": "s2", "started_at": "2026-06-19T02:00:00Z"},
            {"session_id": "s3", "started_at": "2026-06-19T03:00:00Z"},
        ]
    )
    cache = DummyCache()

    result = asyncio.run(
        dashboard_clear_all_sessions(
            DummyRequest(repository, cache),
            x_api_key="secret",
        )
    )

    assert result == {"status": "cleared", "deleted_ids": ["s3", "s2", "s1"]}
    assert repository.records == {}
    assert cache.cleared is True
