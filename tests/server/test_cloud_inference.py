import numpy as np
import pytest

from server.core.inference import CloudInferenceEngine
from shared.contracts import RAW_FRAME_FEATURE_DIM, SEQUENCE_LENGTH, TelemetryPacket


def test_cloud_inference_uses_real_triple_xgb_product_model() -> None:
    rng = np.random.default_rng(42)
    packet = TelemetryPacket(
        session_id="session-1",
        device_id="device-1",
        sequence_number=1,
        raw_feature_sequence=rng.random((SEQUENCE_LENGTH, RAW_FRAME_FEATURE_DIM), dtype=np.float32).tolist(),
        face_found=True,
    )

    response = CloudInferenceEngine().predict(packet)

    assert response.model_name == "triple_xgb_depth_robust_fusion"
    assert response.model_version == "triple_xgb_depth_robust_target_band_product"
    assert response.state in {"FOCUSED", "DISTRACTED"}
    assert set(response.components) == {
        "final_xgb",
        "boost_xgb",
        "targeted_xgb",
    }
    assert response.class_labels == ["very_low", "low", "medium", "high"]
    assert len(response.class_probabilities) == 4
    assert response.predicted_class in {0, 1, 2, 3}
    assert response.predicted_label in set(response.class_labels)
    assert response.focus_score == pytest.approx(
        response.class_probabilities[2] + response.class_probabilities[3],
        abs=1e-6,
    )
    expected_state = "FOCUSED" if response.predicted_class in {2, 3} else "DISTRACTED"
    assert response.state == expected_state
    assert response.decision["decision_rule"] == "argmax_4class"
    assert response.inference_latency_ms is not None
    assert response.inference_latency_ms >= 0.0
    assert 0.0 <= response.focus_score <= 1.0
    assert response.decision["source"] == "triple_xgb_depth_robust_target_band_product"
