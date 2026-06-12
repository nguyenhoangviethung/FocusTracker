from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from server.app import create_app


def test_password_register_login_and_google_login(monkeypatch) -> None:
    monkeypatch.setenv("FOCUSFLOW_ENV", "development")
    monkeypatch.setenv("FOCUSFLOW_REPOSITORY", "memory")
    monkeypatch.setenv("FOCUSFLOW_EVENT_BACKEND", "logging")
    monkeypatch.setenv("FOCUSFLOW_API_KEY", "test-secret")
    monkeypatch.setenv("FOCUSFLOW_GOOGLE_OAUTH_CLIENT_ID", "test-client-id")

    with TestClient(create_app()) as client:
        headers = {"X-API-Key": "test-secret"}

        registered = client.post(
            "/v1/auth/password/register",
            json={
                "username": "student01",
                "password": "super-secret-pass",
                "display_name": "Student One",
            },
            headers=headers,
        )
        assert registered.status_code == 201
        assert registered.json()["auth_provider"] == "password"
        assert registered.json()["username"] == "student01"

        logged_in = client.post(
            "/v1/auth/password/login",
            json={"username": "student01", "password": "super-secret-pass"},
            headers=headers,
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["display_name"] == "Student One"

        monkeypatch.setattr(
            "server.api.routes.extract_google_profile",
            lambda token, audience: {
                "sub": "google-subject",
                "email": "person@example.edu",
                "name": "Google Person",
                "jti": "token-jti",
                "aud": audience,
                "iat": int(datetime.now(tz=timezone.utc).timestamp()),
                "exp": int(datetime.now(tz=timezone.utc).timestamp()) + 3600,
            },
        )
        google_login = client.post(
            "/v1/auth/google",
            json={"id_token": "fake-id-token"},
            headers=headers,
        )
        assert google_login.status_code == 200
        assert google_login.json()["auth_provider"] == "google"
        assert google_login.json()["email"] == "person@example.edu"
