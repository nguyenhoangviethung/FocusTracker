import numpy as np
from tracking.buffer import (
    DEPTH_ROBUST_V2_ENRICHED_FEATURE_DIM,
    DEPTH_ROBUST_V2_FRAME_FEATURE_DIM,
    FeatureSequenceBuffer,
    SEQUENCE_LENGTH,
)


def test_depth_robust_buffer_contract() -> None:
    buffer = FeatureSequenceBuffer(
        sequence_length=SEQUENCE_LENGTH,
        frame_feature_dim=DEPTH_ROBUST_V2_FRAME_FEATURE_DIM,
    )

    rng = np.random.default_rng(42)
    enriched_chunk = None
    for _ in range(SEQUENCE_LENGTH):
        frame_feature = rng.random(DEPTH_ROBUST_V2_FRAME_FEATURE_DIM, dtype=np.float32)
        enriched_chunk = buffer.append(frame_feature)

    assert enriched_chunk is not None
    assert enriched_chunk.shape == (SEQUENCE_LENGTH, DEPTH_ROBUST_V2_ENRICHED_FEATURE_DIM)
