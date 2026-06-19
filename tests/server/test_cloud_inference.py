import numpy as np

from server.core.inference import CloudInferenceEngine
from shared.contracts import TelemetryPacket


def test_cloud_inference_uses_real_product_4class_model() -> None:
    rng = np.random.default_rng(42)
    packet = TelemetryPacket(
        session_id="session-1",
        device_id="device-1",
        sequence_number=1,
        raw_feature_sequence=rng.random((30, 30), dtype=np.float32).tolist(),
        face_found=True,
    )

    response = CloudInferenceEngine().predict(packet)

    assert response.model_name == "fixed_triple_xgb_fusion"
    assert response.model_version == "product_4class_fixed_triple_xgb"
    assert response.state in {"FOCUSED", "DISTRACTED"}
    assert "final_xgb" in response.components
    assert "boost_xgb" in response.components
    assert "targeted_xgb" in response.components
    assert response.class_labels == ["very_low", "low", "medium", "high"]
    assert len(response.class_probabilities) == 4
    assert response.predicted_class in {0, 1, 2, 3}
    assert response.predicted_label in set(response.class_labels)
    expected_state = "FOCUSED" if response.predicted_class in {2, 3} else "DISTRACTED"
    assert response.state == expected_state
    assert response.decision["decision_rule"] == "argmax_4class"
    assert response.inference_latency_ms is not None
    assert response.inference_latency_ms >= 0.0
    assert 0.0 <= response.focus_score <= 1.0
    assert response.decision["source"] == "product_4class_model"
