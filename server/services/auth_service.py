from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2 import id_token

from shared.contracts import AuthProfile


PASSWORD_ITERATIONS = 390000
PASSWORD_ALGORITHM = "pbkdf2_sha256"


def _random_salt() -> str:
    return base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")


def hash_password(password: str, salt: str | None = None, iterations: int = PASSWORD_ITERATIONS) -> tuple[str, str, int]:
    salt_value = salt or _random_salt()
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        iterations,
    )
    encoded = base64.urlsafe_b64encode(derived).decode("ascii").rstrip("=")
    return encoded, salt_value, iterations


def verify_password(password: str, password_hash: str, salt: str, iterations: int) -> bool:
    derived, _, _ = hash_password(password, salt=salt, iterations=iterations)
    return hmac.compare_digest(derived, password_hash)


def extract_google_profile(id_token_str: str, audience: str) -> dict[str, Any]:
    claims = id_token.verify_oauth2_token(id_token_str, Request(), audience=audience)
    if not isinstance(claims, dict):
        raise ValueError("Invalid Google token claims")
    return claims


def profile_from_record(record: dict[str, Any]) -> AuthProfile:
    return AuthProfile(
        user_id=str(record.get("user_id") or ""),
        auth_provider=str(record.get("auth_provider") or "password"),
        username=record.get("username"),
        email=record.get("email"),
        display_name=record.get("display_name"),
        created_at=record.get("created_at"),
        last_login_at=record.get("last_login_at"),
    )
