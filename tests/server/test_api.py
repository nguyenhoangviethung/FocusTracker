import numpy as np
from fastapi.testclient import TestClient

from server.app import create_app


class FailingEventPublisher:
    def publish(self, event_type: str, payload: dict) -> str:
        raise RuntimeError("pubsub unavailable")


def test_session_inference_and_completion(monkeypatch) -> None:
    monkeypatch.setenv("FOCUSFLOW_ENV", "development")
    monkeypatch.setenv("FOCUSFLOW_REPOSITORY", "memory")
    monkeypatch.setenv("FOCUSFLOW_EVENT_BACKEND", "logging")
    monkeypatch.setenv("FOCUSFLOW_API_KEY", "test-secret")

    with TestClient(create_app()) as client:
        headers = {"X-API-Key": "test-secret"}

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        root = client.get("/")
        assert root.status_code == 200
        assert root.json() == {"status": "ok"}

        created = client.post(
            "/v1/sessions",
            json={"device_id": "device-1", "duration_seconds": 1500},
            headers=headers,
        )
        assert created.status_code == 201
        session_id = created.json()["session_id"]

        rng = np.random.default_rng(42)
        inferred = client.post(
            "/v1/inference",
            json={
                "session_id": session_id,
                "device_id": "device-1",
                "sequence_number": 1,
                "raw_feature_sequence": rng.random((30, 30), dtype=np.float32).tolist(),
                "face_found": True,
            },
            headers=headers,
        )
        assert inferred.status_code == 200
        assert set(inferred.json()["components"]) == {"gru", "tcn", "xgboost"}
        stored_after_rest = client.get(
            f"/v1/sessions/{session_id}",
            headers=headers,
        )
        assert stored_after_rest.status_code == 200
        assert stored_after_rest.json()["live_metrics"]["sequence_number"] == 1
        assert stored_after_rest.json()["live_metrics"]["face_found"] is True
        assert stored_after_rest.json()["live_metrics"]["state"] in {
            "FOCUSED",
            "DISTRACTED",
            "NO_FACE",
        }

        with client.websocket_connect(
            f"/v1/ws/sessions/{session_id}?device_id=device-1",
            headers=headers,
        ) as websocket:
            websocket.send_json(
                {
                    "session_id": session_id,
                    "device_id": "device-1",
                    "sequence_number": 2,
                    "raw_feature_sequence": rng.random(
                        (30, 30),
                        dtype=np.float32,
                    ).tolist(),
                    "face_found": True,
                }
            )
            streamed = websocket.receive_json()
            assert streamed["session_id"] == session_id
            assert set(streamed["components"]) == {"gru", "tcn", "xgboost"}

        stored_after_websocket = client.get(
            f"/v1/sessions/{session_id}",
            headers=headers,
        )
        assert stored_after_websocket.status_code == 200
        assert stored_after_websocket.json()["live_metrics"]["sequence_number"] == 2

        client.app.state.event_publisher = FailingEventPublisher()
        completed = client.post(
            f"/v1/sessions/{session_id}/complete",
            json={
                "duration_seconds": 120,
                "focused_seconds": 90,
                "average_focus": 0.75,
                "distraction_count": 2,
                "focus_streak_seconds": 45,
                "completed": False,
                "minute_focus_scores": [0.70, 0.80],
            },
            headers=headers,
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "cancelled"
        assert completed.json()["report_status"] == "completed"

        repeated = client.post(
            f"/v1/sessions/{session_id}/complete",
            json={
                "duration_seconds": 1,
                "focused_seconds": 0,
                "average_focus": 0.0,
                "distraction_count": 0,
                "focus_streak_seconds": 0,
                "completed": True,
            },
            headers=headers,
        )
        assert repeated.status_code == 200
        assert repeated.json()["ended_at"] == completed.json()["ended_at"]
        assert repeated.json()["summary"] == completed.json()["summary"]
