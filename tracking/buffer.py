from __future__ import annotations

from collections import deque
import logging

import numpy as np

from utils.logger import get_logger


logger = get_logger("buffer")


def enrich_raw_sequence(
    raw_sequence: np.ndarray,
    expected_frame_feature_dim: int = 30,
) -> np.ndarray:
    """Expand raw facial features with velocity and sequence-level std."""
    raw_frames = np.asarray(raw_sequence, dtype=np.float32)
    if raw_frames.ndim != 2:
        raise ValueError(f"Expected a 2D raw sequence, got shape {raw_frames.shape}")
    if raw_frames.shape[1] != expected_frame_feature_dim:
        raise ValueError(
            f"Expected frame feature dim {expected_frame_feature_dim}, got {raw_frames.shape[1]}"
        )

    raw_frames = np.nan_to_num(raw_frames, nan=0.0, posinf=0.0, neginf=0.0)
    velocity = np.zeros_like(raw_frames, dtype=np.float32)
    velocity[1:] = raw_frames[1:] - raw_frames[:-1]
    std_vector = np.std(raw_frames, axis=0).astype(np.float32, copy=False)
    std_matrix = np.tile(std_vector, (raw_frames.shape[0], 1)).astype(np.float32, copy=False)
    return np.concatenate([raw_frames, velocity, std_matrix], axis=-1).astype(
        np.float32,
        copy=False,
    )


class FeatureSequenceBuffer:
    """Maintains a sliding raw-feature window and enriches it for inference."""

    def __init__(self, sequence_length: int = 60, frame_feature_dim: int = 30) -> None:
        logger.debug(f"Initializing FeatureSequenceBuffer (sequence_length={sequence_length}, frame_feature_dim={frame_feature_dim})")
        self.sequence_length = sequence_length
        self.frame_feature_dim = frame_feature_dim
        self._buffer: deque[np.ndarray] = deque(maxlen=sequence_length)
        logger.info(f"Buffer initialized: will accumulate {sequence_length} frames x {frame_feature_dim}dim features")

    def __len__(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        logger.debug("Clearing buffer")
        self._buffer.clear()

    @property
    def is_full(self) -> bool:
        return len(self._buffer) == self.sequence_length

    def raw_sequence(self) -> np.ndarray | None:
        if not self.is_full:
            return None
        return np.stack(self._buffer, axis=0).astype(np.float32, copy=True)

    def append(self, frame_feature: np.ndarray) -> np.ndarray | None:
        feature = np.asarray(frame_feature, dtype=np.float32).reshape(-1)
        if feature.shape[0] != self.frame_feature_dim:
            logger.error(f"Shape mismatch: expected {self.frame_feature_dim}, got {feature.shape[0]}")
            raise ValueError(
                f"Expected frame feature dim {self.frame_feature_dim}, got {feature.shape[0]}"
            )

        self._buffer.append(feature)
        buffer_fill = len(self._buffer) / self.sequence_length * 100
        logger.debug(f"Frame appended to buffer: {len(self._buffer)}/{self.sequence_length} ({buffer_fill:.1f}%)")
        
        if not self.is_full:
            return None

        enriched = self._enriched_chunk()
        logger.debug(f"Buffer full! Enriched chunk shape: {enriched.shape}")
        return enriched

    def _enriched_chunk(self) -> np.ndarray:
        raw_frames = np.stack(self._buffer, axis=0).astype(np.float32, copy=False)
        logger.debug(f"Raw frames stacked: shape={raw_frames.shape}")
        enriched_chunk = enrich_raw_sequence(raw_frames, self.frame_feature_dim)
        expected_shape = (self.sequence_length, self.frame_feature_dim * 3)
        
        if enriched_chunk.shape != expected_shape:
            logger.error(f"Enrichment shape mismatch: expected {expected_shape}, got {enriched_chunk.shape}")
            raise ValueError(f"Expected enriched shape {expected_shape}, got {enriched_chunk.shape}")

        logger.debug(f"Enrichment complete: shape={enriched_chunk.shape}, dtype={enriched_chunk.dtype}, range=[{enriched_chunk.min():.3f}, {enriched_chunk.max():.3f}]")
        return enriched_chunk
