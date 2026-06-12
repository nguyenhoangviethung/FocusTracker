from server.repositories.sessions import InMemorySessionRepository
from shared.contracts import SessionCreate, SessionSummary


def test_in_memory_session_lifecycle() -> None:
    repository = InMemorySessionRepository()
    record = repository.create(
        SessionCreate(device_id="device-1", duration_seconds=1500)
    )

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
