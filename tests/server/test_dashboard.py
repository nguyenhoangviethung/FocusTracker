from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import app


def test_dashboard_routes_are_available() -> None:
    with TestClient(app) as client:
        html = client.get("/dashboard")
        assert html.status_code == 200
        assert "FocusFlow AI Server Dashboard" in html.text
        assert "100-camera wall" in html.text

        summary = client.get("/dashboard/api/summary")
        assert summary.status_code == 200
        payload = summary.json()
        assert "ready" in payload
        assert "recent_sessions" in payload
        assert "repository_backend" in payload
