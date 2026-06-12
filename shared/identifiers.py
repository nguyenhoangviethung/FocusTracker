from __future__ import annotations

from datetime import datetime, timezone


def _document_part(value: str, fallback: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    normalized = normalized.replace("/", "_slash_")
    if normalized in {"", ".", ".."}:
        return fallback
    return normalized


def new_session_id(device_id: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    compact = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    device = _document_part(device_id, "unknown-device")
    return f"session_{device}_{compact}"


def new_password_user_id(username: str) -> str:
    return f"user_password_{_document_part(username, 'unknown-user')}"


def new_google_user_id(email: str | None, subject: str) -> str:
    identity = email or subject
    return f"user_google_{_document_part(identity, 'unknown-user')}"
