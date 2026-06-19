from utils.session_storage import is_meaningful_session_record


def test_meaningful_session_requires_real_focus_data() -> None:
    assert not is_meaningful_session_record(
        {
            "timestamp": "2026-06-19T00:00:00Z",
            "duration_seconds": 0,
            "focused_seconds": 0,
            "average_focus": 0.0,
            "minute_focus_scores": [],
        }
    )


def test_meaningful_session_accepts_real_summary() -> None:
    assert is_meaningful_session_record(
        {
            "timestamp": "2026-06-19T00:00:00Z",
            "duration_seconds": 1500,
            "focused_seconds": 840,
            "average_focus": 0.56,
            "minute_focus_scores": [0.51, 0.58, 0.59],
        }
    )
