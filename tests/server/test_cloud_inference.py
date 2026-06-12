import numpy as np

from server.core.inference import CloudInferenceEngine
from shared.contracts import TelemetryPacket


def test_cloud_inference_uses_real_late_fusion_model() -> None:
    rng = np.random.default_rng(42)
    packet = TelemetryPacket(
        session_id="session-1",
        device_id="device-1",
        sequence_number=1,
        raw_feature_sequence=rng.random((30, 30), dtype=np.float32).tolist(),
        face_found=True,
    )

    response = CloudInferenceEngine().predict(packet)

    assert response.model_name == "late_fusion_gru_tcn_xgb"
    assert response.state in {"FOCUSED", "DISTRACTED"}
    assert set(response.components) == {"gru", "tcn", "xgboost"}
    assert 0.0 <= response.focus_score <= 1.0
    assert response.decision["source"] == "late_fusion_model"
