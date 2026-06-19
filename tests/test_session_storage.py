from utils.session_storage import delete_session_record, is_meaningful_session_record, load_session_history, save_session_history


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


def test_delete_session_record_removes_matching_timestamp() -> None:
    original = load_session_history()
    try:
        save_session_history(
            [
                {
                    "timestamp": "2026-06-19T00:00:00Z",
                    "duration_seconds": 120,
                    "focused_seconds": 90,
                    "average_focus": 0.75,
                    "minute_focus_scores": [0.7, 0.8],
                },
                {
                    "timestamp": "2026-06-18T00:00:00Z",
                    "duration_seconds": 180,
                    "focused_seconds": 120,
                    "average_focus": 0.66,
                    "minute_focus_scores": [0.6, 0.7, 0.68],
                },
            ]
        )

        assert delete_session_record("2026-06-19T00:00:00Z") is True
        remaining = load_session_history()
        assert len(remaining) == 1
        assert remaining[0]["timestamp"] == "2026-06-18T00:00:00Z"
    finally:
        save_session_history(original)
