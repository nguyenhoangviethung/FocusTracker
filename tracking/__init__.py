"""Tracking layer for FocusFlow AI.

Exports are resolved lazily so model/unit tests do not import camera-only
dependencies such as MediaPipe unless they actually need webcam tracking.
"""

__all__ = [
    "FaceFeatureDetector",
    "FeatureSequenceBuffer",
    "FocusSessionTracker",
    "ProductInferencer",
    "TripleXGBDepthRobustInferencer",
    "TrackerConfig",
]


def __getattr__(name: str):
    if name == "FeatureSequenceBuffer":
        from tracking.buffer import FeatureSequenceBuffer

        return FeatureSequenceBuffer
    if name == "FaceFeatureDetector":
        from tracking.detector import FaceFeatureDetector

        return FaceFeatureDetector
    if name in {"ProductInferencer", "TripleXGBDepthRobustInferencer"}:
        from tracking.inference import ProductInferencer, TripleXGBDepthRobustInferencer

        return {
            "ProductInferencer": ProductInferencer,
            "TripleXGBDepthRobustInferencer": TripleXGBDepthRobustInferencer,
        }[name]
    if name in {"FocusSessionTracker", "TrackerConfig"}:
        from tracking.tracker import FocusSessionTracker, TrackerConfig

        return {
            "FocusSessionTracker": FocusSessionTracker,
            "TrackerConfig": TrackerConfig,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
