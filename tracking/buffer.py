from __future__ import annotations

from collections import deque

import numpy as np


class FeatureSequenceBuffer:
    """Maintains a 60-frame sliding window and enriches it to (60, 90)."""

    def __init__(self, sequence_length: int = 60, frame_feature_dim: int = 30) -> None:
        self.sequence_length = sequence_length
        self.frame_feature_dim = frame_feature_dim
        self._buffer: deque[np.ndarray] = deque(maxlen=sequence_length)

    def __len__(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()

    @property
    def is_full(self) -> bool:
        return len(self._buffer) == self.sequence_length

    def append(self, frame_feature: np.ndarray) -> np.ndarray | None:
        feature = np.asarray(frame_feature, dtype=np.float32).reshape(-1)
        if feature.shape[0] != self.frame_feature_dim:
            raise ValueError(
                f"Expected frame feature dim {self.frame_feature_dim}, got {feature.shape[0]}"
            )

        self._buffer.append(feature)
        if not self.is_full:
            return None

        return self._enriched_chunk()

    def _enriched_chunk(self) -> np.ndarray:
        raw_frames = np.stack(self._buffer, axis=0).astype(np.float32, copy=False)

        velocity = np.zeros_like(raw_frames, dtype=np.float32)
        velocity[1:] = raw_frames[1:] - raw_frames[:-1]

        std_vector = np.std(raw_frames, axis=0).astype(np.float32, copy=False)
        std_matrix = np.tile(std_vector, (self.sequence_length, 1)).astype(np.float32, copy=False)

        enriched_chunk = np.concatenate([raw_frames, velocity, std_matrix], axis=-1).astype(np.float32, copy=False)
        expected_shape = (self.sequence_length, self.frame_feature_dim * 3)
        if enriched_chunk.shape != expected_shape:
            raise ValueError(f"Expected enriched shape {expected_shape}, got {enriched_chunk.shape}")

        return enriched_chunk
