from __future__ import annotations

import asyncio
from datetime import timedelta
import re

from fastapi import HTTPException

from server.api.dashboard_ui import render_dashboard_html
from server.api.routes import (
    DashboardSnapshotCache,
    dashboard_batch_delete_sessions,
    dashboard_clear_all_sessions,
    dashboard_clear_stale_sessions,
    dashboard_create_session,
    dashboard_delete_session,
    dashboard_finalize_session,
    dashboard_update_session,
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


class DummyPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def publish(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class FailingPublisher:
    def publish(self, event_type: str, payload: dict) -> None:
        raise RuntimeError("Pub/Sub unavailable")


class MutableRepository:
    def __init__(self, records: list[dict]) -> None:
        self.records = {record["session_id"]: dict(record) for record in records}

    def get(self, session_id: str):
        record = self.records.get(session_id)
        return dict(record) if record else None

    def create(self, payload):
        from shared.contracts import SessionRecord
        record = SessionRecord(**payload.model_dump())
        self.records[record.session_id] = record.model_dump(mode="json")
        return record

    def list_recent(self, limit: int):
        records = sorted(
            self.records.values(),
            key=lambda record: str(record.get("started_at", "")),
            reverse=True,
        )
        return [dict(record) for record in records[:limit]]

    def delete(self, session_id: str) -> bool:
        return self.records.pop(session_id, None) is not None

    def update(self, session_id: str, updates: dict):
        record = self.records.get(session_id)
        if record is None:
            return None
        record.update(updates)
        return dict(record)

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
    def __init__(self, repository, cache: DummyCache | None = None, publisher=None) -> None:
        self.state = type(
            "State",
            (),
            {
                "settings": DummySettings(),
                "session_repository": repository,
                "user_repository": DummyUserRepository(),
                "inference_engine": DummyEngine(),
                "event_publisher": publisher,
                "dashboard_cache": cache,
                "query_limit": 100,
            },
        )()


class DummyRequest:
    def __init__(self, repository, cache: DummyCache | None = None, publisher=None) -> None:
        self.app = DummyApp(repository, cache, publisher)


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
    assert any(getattr(route, "path", None) == "/dashboard/api/sessions/clear-all" for route in app.routes)
    assert "/dashboard/api/sessions/batch-delete" in html
    assert '"secret-key"' in html


def test_dashboard_template_references_existing_dom_ids() -> None:
    html = render_dashboard_html("secret-key")
    declared_ids = set(re.findall(r'id="([^"]+)"', html))
    referenced_ids = set(re.findall(r"getElementById\('([^']+)'\)", html))

    assert referenced_ids - declared_ids == set()


def test_dashboard_delete_controls_use_safe_event_binding() -> None:
    html = render_dashboard_html("secret-key")

    assert 'data-delete-session="' in html
    assert "addEventListener('click'" in html
    assert "encodeURIComponent(sessionId)" in html
    assert "Delete Visible" in html
    assert "filteredSessions().map" in html
    assert 'onclick="deleteSession' not in html


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


def test_dashboard_snapshot_normalizes_legacy_firestore_live_metrics() -> None:
    from server.api.routes import _dashboard_snapshot

    repository = MutableRepository(
        [
            {
                "session_id": "legacy-session",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "completed",
                "started_at": "2026-06-17T04:03:58+00:00",
                "ended_at": "2026-06-17T04:10:04+00:00",
                "live_metrics": {
                    "ai_state": "DISTRACTED",
                    "components": {
                        "gru": {"probability": 0.5325, "state": "DISTRACTED"},
                        "tcn": {"probability": 0.3917, "state": "DISTRACTED"},
                        "xgboost": {"probability": 0.4812, "state": "DISTRACTED"},
                    },
                },
            }
        ]
    )

    snapshot = _dashboard_snapshot(DummyRequest(repository), limit=100)
    metrics = snapshot["recent_sessions"][0]["live_metrics"]

    assert metrics["state"] == "DISTRACTED"
    assert metrics["focus_score"] == (0.5325 + 0.3917 + 0.4812) / 3


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


def test_dashboard_batch_delete_rejects_malformed_payload() -> None:
    repository = MutableRepository([{"session_id": "s1", "started_at": "2026-06-19T01:00:00Z"}])

    try:
        asyncio.run(
            dashboard_batch_delete_sessions(
                DummyRequest(repository, DummyCache()),
                {"session_ids": "s1"},
                x_api_key="secret",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "session_ids must be a list"
    else:
        raise AssertionError("Expected malformed batch delete payload to be rejected")

    assert set(repository.records) == {"s1"}


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


def test_dashboard_update_settings() -> None:
    from server.api.routes import dashboard_update_settings
    class DummyCacheWithTtl:
        def __init__(self) -> None:
            self.ttl_seconds = 3.0
            self.cleared = False
        def clear(self) -> None:
            self.cleared = True

    class MutableApp:
        def __init__(self, cache) -> None:
            self.state = type(
                "State",
                (),
                {
                    "settings": DummySettings(),
                    "session_repository": None,
                    "user_repository": None,
                    "inference_engine": DummyEngine(),
                    "event_publisher": None,
                    "dashboard_cache": cache,
                    "query_limit": 100,
                },
            )()

    class MutableRequest:
        def __init__(self, cache) -> None:
            self.app = MutableApp(cache)

    cache = DummyCacheWithTtl()
    req = MutableRequest(cache)

    result = asyncio.run(
        dashboard_update_settings(
            req,
            {"cache_seconds": 5.0, "query_limit": 50},
            x_api_key="secret",
        )
    )

    assert result == {"status": "success", "cache_seconds": 5.0, "query_limit": 50}
    assert req.app.state.dashboard_cache.ttl_seconds == 5.0
    assert req.app.state.query_limit == 50
    assert cache.cleared is True


# ---------------------------------------------------------------------------
# dashboard_create_session tests
# ---------------------------------------------------------------------------


def test_dashboard_create_session_creates_active_session() -> None:
    repository = MutableRepository([])
    cache = DummyCache()

    result = asyncio.run(
        dashboard_create_session(
            DummyRequest(repository, cache),
            {"user_id": "test-user", "device_id": "test-device", "duration_seconds": 600},
            x_api_key="secret",
        )
    )

    assert result["status"] == "created"
    session_id = result["session_id"]
    assert session_id in repository.records
    record = repository.records[session_id]
    assert record["user_id"] == "test-user"
    assert record["device_id"] == "test-device"
    assert record["duration_seconds"] == 600
    assert record.get("ended_at") is None
    assert cache.cleared is True


def test_dashboard_create_session_with_completed_status_populates_summary() -> None:
    repository = MutableRepository([])
    cache = DummyCache()

    result = asyncio.run(
        dashboard_create_session(
            DummyRequest(repository, cache),
            {
                "user_id": "demo-user",
                "device_id": "demo-device",
                "duration_seconds": 1800,
                "status": "completed",
            },
            x_api_key="secret",
        )
    )

    assert result["status"] == "created"
    session_id = result["session_id"]
    record = repository.records[session_id]
    assert record["status"] == "completed"
    assert record["ended_at"] is not None
    summary = record["summary"]
    assert isinstance(summary, dict)
    assert summary["duration_seconds"] == 1800
    assert 0.0 < summary["average_focus"] <= 1.0
    assert len(summary["minute_focus_scores"]) == 30  # 1800 / 60
    assert record["report_status"] == "completed"


def test_dashboard_create_session_with_cancelled_status() -> None:
    repository = MutableRepository([])

    result = asyncio.run(
        dashboard_create_session(
            DummyRequest(repository, DummyCache()),
            {"status": "cancelled", "duration_seconds": 600},
            x_api_key="secret",
        )
    )

    session_id = result["session_id"]
    record = repository.records[session_id]
    assert record["status"] == "cancelled"
    assert record["ended_at"] is not None
    assert record["summary"]["completed"] is False


def test_dashboard_create_session_uses_defaults() -> None:
    repository = MutableRepository([])

    result = asyncio.run(
        dashboard_create_session(
            DummyRequest(repository, DummyCache()),
            {},
            x_api_key="secret",
        )
    )

    session_id = result["session_id"]
    record = repository.records[session_id]
    assert record["user_id"] == "admin-demo"
    assert record["device_id"] == "demo-device"
    assert record["duration_seconds"] == 1800
    assert record.get("ended_at") is None


def test_dashboard_create_session_rejects_bad_api_key() -> None:
    repository = MutableRepository([])

    try:
        asyncio.run(
            dashboard_create_session(
                DummyRequest(repository, DummyCache()),
                {"user_id": "user"},
                x_api_key="wrong-key",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected 401 for bad API key")

    assert len(repository.records) == 0


# ---------------------------------------------------------------------------
# dashboard_update_session tests
# ---------------------------------------------------------------------------


def test_dashboard_update_session_updates_user_and_device() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "old-user",
                "device_id": "old-device",
                "status": "active",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": None,
            }
        ]
    )
    cache = DummyCache()

    result = asyncio.run(
        dashboard_update_session(
            DummyRequest(repository, cache),
            "s1",
            {"user_id": "new-user", "device_id": "new-device"},
            x_api_key="secret",
        )
    )

    assert result == {"status": "updated", "session_id": "s1"}
    record = repository.records["s1"]
    assert record["user_id"] == "new-user"
    assert record["device_id"] == "new-device"
    assert cache.cleared is True


def test_dashboard_update_session_transitions_active_to_completed() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "active",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": None,
                "duration_seconds": 1800,
            }
        ]
    )

    asyncio.run(
        dashboard_update_session(
            DummyRequest(repository, DummyCache()),
            "s1",
            {"status": "completed"},
            x_api_key="secret",
        )
    )

    record = repository.records["s1"]
    assert record["status"] == "completed"
    assert record["ended_at"] is not None
    assert record["summary"] is not None
    assert record["report_status"] == "completed"


def test_dashboard_update_session_transitions_completed_back_to_active() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "completed",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": "2026-06-20T10:30:00Z",
                "summary": {"duration_seconds": 1800, "average_focus": 0.75},
                "report_status": "completed",
                "report_started_at": "2026-06-20T10:30:00Z",
                "report_completed_at": "2026-06-20T10:30:00Z",
            }
        ]
    )

    asyncio.run(
        dashboard_update_session(
            DummyRequest(repository, DummyCache()),
            "s1",
            {"status": "active"},
            x_api_key="secret",
        )
    )

    record = repository.records["s1"]
    assert record["status"] == "active"
    assert record["ended_at"] is None
    assert record["summary"] is None
    assert record["report_status"] is None


def test_dashboard_update_session_adds_notes_to_summary() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "completed",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": "2026-06-20T10:30:00Z",
                "summary": {"duration_seconds": 1800, "average_focus": 0.75},
            }
        ]
    )

    asyncio.run(
        dashboard_update_session(
            DummyRequest(repository, DummyCache()),
            "s1",
            {"notes": "Good focus session"},
            x_api_key="secret",
        )
    )

    record = repository.records["s1"]
    assert record["summary"]["notes"] == "Good focus session"
    assert record["summary"]["duration_seconds"] == 1800


def test_dashboard_update_session_returns_404_for_missing_session() -> None:
    repository = MutableRepository([])

    try:
        asyncio.run(
            dashboard_update_session(
                DummyRequest(repository, DummyCache()),
                "nonexistent",
                {"user_id": "user"},
                x_api_key="secret",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Session not found"
    else:
        raise AssertionError("Expected 404 for missing session")


def test_dashboard_update_session_rejects_bad_api_key() -> None:
    repository = MutableRepository(
        [{"session_id": "s1", "started_at": "2026-06-20T10:00:00Z"}]
    )

    try:
        asyncio.run(
            dashboard_update_session(
                DummyRequest(repository, DummyCache()),
                "s1",
                {"user_id": "hacker"},
                x_api_key="wrong",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected 401 for bad API key")


def test_dashboard_update_session_empty_payload_is_noop() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "original-user",
                "status": "active",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": None,
            }
        ]
    )

    result = asyncio.run(
        dashboard_update_session(
            DummyRequest(repository, DummyCache()),
            "s1",
            {},
            x_api_key="secret",
        )
    )

    assert result == {"status": "updated", "session_id": "s1"}
    assert repository.records["s1"]["user_id"] == "original-user"


# ---------------------------------------------------------------------------
# dashboard_finalize_session tests
# ---------------------------------------------------------------------------


def test_dashboard_finalize_session_generates_summary_and_publishes_event() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "active",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": None,
                "duration_seconds": 1800,
            }
        ]
    )
    publisher = DummyPublisher()
    cache = DummyCache()

    result = asyncio.run(
        dashboard_finalize_session(
            DummyRequest(repository, cache, publisher),
            "s1",
            {},
            x_api_key="secret",
        )
    )

    assert result == {"status": "finalized", "session_id": "s1"}

    record = repository.records["s1"]
    assert record["status"] == "completed"
    assert record["ended_at"] is not None
    summary = record["summary"]
    assert isinstance(summary, dict)
    assert summary["duration_seconds"] == 1800
    assert 0.0 < summary["average_focus"] <= 1.0
    assert len(summary["minute_focus_scores"]) == 30  # 1800 / 60
    assert summary["completed"] is True
    assert record["report_status"] == "completed"

    assert len(publisher.events) == 1
    event_type, payload = publisher.events[0]
    assert event_type == "session.completed"
    assert payload["session_id"] == "s1"
    assert payload["device_id"] == "device-1"
    assert isinstance(payload["summary"], dict)

    assert cache.cleared is True


def test_dashboard_finalize_session_with_custom_duration() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "active",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": None,
                "duration_seconds": 1800,
            }
        ]
    )
    publisher = DummyPublisher()

    asyncio.run(
        dashboard_finalize_session(
            DummyRequest(repository, DummyCache(), publisher),
            "s1",
            {"duration_seconds": 600, "completed": False},
            x_api_key="secret",
        )
    )

    record = repository.records["s1"]
    assert record["status"] == "cancelled"
    assert record["summary"]["duration_seconds"] == 600
    assert record["summary"]["completed"] is False
    assert len(record["summary"]["minute_focus_scores"]) == 10  # 600 / 60


def test_dashboard_finalize_session_returns_404_for_missing_session() -> None:
    repository = MutableRepository([])
    publisher = DummyPublisher()

    try:
        asyncio.run(
            dashboard_finalize_session(
                DummyRequest(repository, DummyCache(), publisher),
                "nonexistent",
                {},
                x_api_key="secret",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Session not found"
    else:
        raise AssertionError("Expected 404 for missing session")

    assert len(publisher.events) == 0


def test_dashboard_finalize_session_rejects_bad_api_key() -> None:
    repository = MutableRepository(
        [{"session_id": "s1", "started_at": "2026-06-20T10:00:00Z"}]
    )

    try:
        asyncio.run(
            dashboard_finalize_session(
                DummyRequest(repository, DummyCache(), DummyPublisher()),
                "s1",
                {},
                x_api_key="wrong",
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected 401 for bad API key")


def test_dashboard_finalize_session_survives_publisher_failure() -> None:
    repository = MutableRepository(
        [
            {
                "session_id": "s1",
                "user_id": "user-1",
                "device_id": "device-1",
                "status": "active",
                "started_at": "2026-06-20T10:00:00Z",
                "ended_at": None,
                "duration_seconds": 600,
            }
        ]
    )

    result = asyncio.run(
        dashboard_finalize_session(
            DummyRequest(repository, DummyCache(), FailingPublisher()),
            "s1",
            {},
            x_api_key="secret",
        )
    )

    assert result == {"status": "finalized", "session_id": "s1"}
    record = repository.records["s1"]
    assert record["status"] == "completed"
    assert record["summary"] is not None
