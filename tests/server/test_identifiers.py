from __future__ import annotations

from datetime import datetime, timezone

from shared.identifiers import (
    new_google_user_id,
    new_password_user_id,
    new_session_id,
)


def test_document_identifiers_are_readable_and_deterministic() -> None:
    session_id = new_session_id(
        "demo-client-025",
        datetime(2026, 6, 12, 16, 25, tzinfo=timezone.utc),
    )
    password_user_id = new_password_user_id("student01")
    google_user_id = new_google_user_id("student@example.edu", "google-subject-123")

    assert session_id == "session_demo-client-025_20260612T162500000000Z"
    assert password_user_id == "user_password_student01"
    assert google_user_id == "user_google_student@example.edu"
