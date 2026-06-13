from __future__ import annotations

from demo.seed_users import build_seed_entries


def test_build_seed_entries_are_readable_and_stable() -> None:
    entries = build_seed_entries(3)

    assert len(entries) == 3
    assert entries[0].index == 1
    assert entries[0].user_id == "user_google_demo-user-001@example.edu"
    assert entries[0].email == "demo-user-001@example.edu"
    assert entries[0].display_name == "Demo User 001"
    assert entries[0].auth_provider == "google"
