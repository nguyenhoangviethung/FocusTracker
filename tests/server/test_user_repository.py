from __future__ import annotations

import pytest

from server.repositories.users import InMemoryUserRepository


def test_in_memory_user_repository_password_and_google_paths() -> None:
    repo = InMemoryUserRepository()

    created = repo.create_password_user("student01", "hash", "salt", "Student One")
    assert created["username"] == "student01"
    assert created["user_id"].startswith("user_password_")

    fetched = repo.get_by_username("student01")
    assert fetched is not None
    assert fetched["display_name"] == "Student One"
    assert repo.get_many([created["user_id"], "missing-user"]) == {
        created["user_id"]: created
    }

    updated = repo.login_password_user("student01")
    assert updated is not None
    assert updated["auth_provider"] == "password"

    google_user = repo.upsert_google_user("google-subject", "person@example.edu", "Google Person")
    assert google_user["auth_provider"] == "google"
    assert google_user["user_id"].startswith("user_google_")
    assert google_user["username"] == "person@example.edu"
    assert repo.get_by_google_subject("google-subject")["email"] == "person@example.edu"

    updated_google_user = repo.upsert_google_user("google-subject", "person@example.edu", "Google Person")
    assert updated_google_user["username"] == "person@example.edu"

    with pytest.raises(ValueError):
        repo.create_password_user("student01", "hash", "salt", "Student One")
