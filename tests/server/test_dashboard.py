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
        assert "live_metrics" in html.text
        assert "setInterval(() => refreshDashboard().catch(console.error), 3000)" in html.text
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
