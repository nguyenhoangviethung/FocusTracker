from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from google_auth_oauthlib.flow import InstalledAppFlow

from shared.contracts import AuthProfile
from utils.logger import get_logger


logger = get_logger("auth_client")


class AuthClient:
    def __init__(self, api_url: str, api_key: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key.strip()

    def _request_json(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        logger.info("Auth API request: %s %s%s", method, self.api_url, path)
        req = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and path.startswith("/v1/auth/"):
                raise RuntimeError(
                    "Cloud API auth endpoint is missing. Deploy the latest server revision."
                ) from exc
            raise RuntimeError(body or f"HTTP {exc.code}") from exc

    def register_password(self, username: str, password: str, display_name: str | None = None) -> AuthProfile:
        payload = {
            "username": username,
            "password": password,
            "display_name": display_name,
        }
        return AuthProfile.model_validate(
            self._request_json("POST", "/v1/auth/password/register", payload)
        )

    def login_password(self, username: str, password: str) -> AuthProfile:
        payload = {"username": username, "password": password}
        return AuthProfile.model_validate(
            self._request_json("POST", "/v1/auth/password/login", payload)
        )

    def login_google(self, scopes: tuple[str, ...]) -> AuthProfile:
        client_id = os.getenv("FOCUSFLOW_GOOGLE_OAUTH_CLIENT_ID", "").strip()
        client_secret = os.getenv("FOCUSFLOW_GOOGLE_OAUTH_SECRET", "").strip()
        auth_uri = os.getenv(
            "FOCUSFLOW_GOOGLE_OAUTH_AUTH_URI",
            "https://accounts.google.com/o/oauth2/auth",
        ).strip()
        token_uri = os.getenv(
            "FOCUSFLOW_GOOGLE_OAUTH_TOKEN_URI",
            "https://oauth2.googleapis.com/token",
        ).strip()
        redirect_uris = tuple(
            item.strip()
            for item in os.getenv("FOCUSFLOW_GOOGLE_OAUTH_REDIRECT_URIS", "http://localhost").split(",")
            if item.strip()
        )

        if not client_id or not client_secret:
            raise RuntimeError("Google OAuth env is missing client_id/client_secret")
        if not redirect_uris:
            raise RuntimeError("Google OAuth env is missing redirect_uris")
        if not self.api_url:
            raise RuntimeError("Cloud API URL is not configured")

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": auth_uri,
                "token_uri": token_uri,
                "redirect_uris": list(redirect_uris),
            }
        }

        flow = InstalledAppFlow.from_client_config(client_config, scopes=list(scopes))
        flow.run_local_server(
            host="127.0.0.1",
            port=0,
            authorization_prompt_message="Please visit this URL to authorize this application: {url}",
            success_message="Login complete. You may close this tab.",
            open_browser=True,
        )

        credentials = flow.credentials
        id_token = str(getattr(credentials, "id_token", "") or "").strip()
        if not id_token:
            raise RuntimeError("Google OAuth flow did not return an id_token")

        return AuthProfile.model_validate(
            self._request_json("POST", "/v1/auth/google", {"id_token": id_token})
        )
