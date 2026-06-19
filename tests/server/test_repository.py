from datetime import timedelta

from server.repositories.sessions import InMemorySessionRepository
from shared.contracts import SessionCreate, SessionSummary, utc_now


def test_in_memory_session_lifecycle() -> None:
    repository = InMemorySessionRepository()
    record = repository.create(
        SessionCreate(device_id="device-1", duration_seconds=1500)
    )
    assert record.session_id.startswith("session_")

    stored = repository.get(record.session_id)
    assert stored is not None
    assert stored["status"] == "active"

    completed = repository.complete(
        record.session_id,
        SessionSummary(
            duration_seconds=120,
            focused_seconds=90,
            average_focus=0.75,
            distraction_count=2,
            focus_streak_seconds=45,
            completed=False,
        ),
    )
    assert completed is not None
    assert completed["status"] == "cancelled"
    assert completed["summary"]["average_focus"] == 0.75
    assert completed["report_status"] == "completed"
    assert completed["report_started_at"] == completed["report_completed_at"]

    repeated = repository.complete(
        record.session_id,
        SessionSummary(
            duration_seconds=999,
            focused_seconds=0,
            average_focus=0.0,
            distraction_count=0,
            focus_streak_seconds=0,
            completed=True,
        ),
    )
    assert repeated is not None
    assert repeated["ended_at"] == completed["ended_at"]
    assert repeated["summary"] == completed["summary"]


def test_in_memory_repository_expires_stale_sessions_with_bounded_duration() -> None:
    repository = InMemorySessionRepository()
    record = repository.create(
        SessionCreate(device_id="device-1", duration_seconds=1500)
    )
    started_at = utc_now() - timedelta(hours=3)
    last_seen_at = started_at + timedelta(minutes=8)
    repository.update(
        record.session_id,
        {
            "started_at": started_at.isoformat(),
            "last_seen_at": last_seen_at.isoformat(),
        },
    )

    expired_ids = repository.expire_stale(utc_now() - timedelta(minutes=10))
    stored = repository.get(record.session_id)

    assert expired_ids == [record.session_id]
    assert stored is not None
    assert stored["status"] == "cancelled"
    assert stored["cancellation_reason"] == "stale_timeout"
    assert stored["summary"]["duration_seconds"] == 8 * 60
    assert stored["ended_at"] == last_seen_at.isoformat()
