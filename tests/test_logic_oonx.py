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
    assert inferencer._gru_normalizer is not None
    assert inferencer._tcn_normalizer is not None
    assert inferencer._gru_normalizer[0].shape == (spec.enriched_feature_dim,)
    assert inferencer._tcn_normalizer[0].shape == (spec.enriched_feature_dim,)

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
    assert np.isclose(components["gru"]["probability"], 0.6383630857233988, atol=1e-6)
    assert np.isclose(components["tcn"]["probability"], 0.5076513131339473, atol=1e-6)
    assert np.isclose(components["xgboost"]["probability"], 0.2610085904598236, atol=1e-6)
    assert np.isclose(prediction["probability"], 0.44820775770078986, atol=1e-6)
