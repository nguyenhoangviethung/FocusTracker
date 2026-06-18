import numpy as np
from tracking.buffer import FeatureSequenceBuffer
from tracking.inference import ONNXEngagementInferencer


def test_onnx_pipeline_smoke() -> None:
    inferencer = ONNXEngagementInferencer()
    spec = inferencer.spec

    assert spec.model_file.exists()
    assert spec.sequence_length == 30
    assert spec.raw_feature_dim == 30
    assert spec.enriched_feature_dim == 90

    buffer = FeatureSequenceBuffer(
        sequence_length=spec.sequence_length,
        frame_feature_dim=spec.raw_feature_dim,
    )

    rng = np.random.default_rng(42)
    enriched_chunk = None
    for _ in range(spec.sequence_length):
        frame_feature = rng.random(spec.raw_feature_dim, dtype=np.float32)
        enriched_chunk = buffer.append(frame_feature)

    assert enriched_chunk is not None
    assert enriched_chunk.shape == spec.expected_input_shape()

    prediction = inferencer.predict(enriched_chunk)
    assert 0.0 <= float(prediction["probability"]) <= 1.0
    assert prediction["state"] in {"ENGAGED", "DISTRACTED"}

    components = prediction["components"]
    assert "final_xgb" in components
    assert "boost_xgb" in components
    assert "targeted_xgb" in components

    # Check component probabilities
    for name in ["final_xgb", "boost_xgb", "targeted_xgb"]:
        assert 0.0 <= components[name]["probability"] <= 1.0
        assert len(components[name]["probabilities"]) == 4

    assert "probabilities_4class" in prediction
    assert len(prediction["probabilities_4class"]) == 4
    assert 0 <= prediction["prediction_4class"] < 4
    assert prediction["decision_rule"] == "argmax_4class"
    expected_state = "ENGAGED" if prediction["prediction_4class"] in {2, 3} else "DISTRACTED"
    assert prediction["state"] == expected_state
