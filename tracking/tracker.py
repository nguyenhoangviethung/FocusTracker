from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2

from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from tracking.hardcore import HardcoreDisciplineController, admin_permission_hint
from tracking.inference import ONNXEngagementInferencer
from tracking.os_tracker import ActiveWindowTracker
from utils.logger import get_logger


logger = get_logger("tracker")


FusionLogic = Callable[[float, dict[str, Any] | None, dict[str, Any]], dict[str, Any]]
DEFAULT_PRODUCTIVE_KEYWORDS = ("vscode", "github", "pdf", "docx", "figma")
DEFAULT_DISTRACTING_KEYWORDS = ("facebook", "netflix", "lol", "tiktok")
INFERENCE_EVERY_N_FRAMES = 3
PREVIEW_EVERY_N_FRAMES = 2


@dataclass(slots=True)
class TrackerConfig:
    camera_index: int = 0
    demo_video_path: str = ""
    show_landmarks: bool = True
    engagement_threshold: float = 0.54
    smoothing_window: int = 5
    os_ai_threshold: float = 0.45
    os_override_threshold: float = 0.60
    hardcore_enabled: bool = False
    hardcore_countdown_seconds: int = 30
    productive_keywords: tuple[str, ...] = DEFAULT_PRODUCTIVE_KEYWORDS
    distracting_keywords: tuple[str, ...] = DEFAULT_DISTRACTING_KEYWORDS

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrackerConfig":
        productive = _split_keywords(payload.get("productive_keywords"), DEFAULT_PRODUCTIVE_KEYWORDS)
        distracting = _split_keywords(payload.get("distracting_keywords"), DEFAULT_DISTRACTING_KEYWORDS)
        return cls(
            camera_index=_to_int(payload.get("camera_index"), 0),
            demo_video_path=str(payload.get("demo_video_path") or "").strip(),
            show_landmarks=_to_bool(payload.get("show_landmarks"), True),
            engagement_threshold=_to_float(payload.get("engagement_threshold"), 0.54),
            smoothing_window=max(3, min(5, _to_int(payload.get("smoothing_window"), 5))),
            os_ai_threshold=_to_float(payload.get("os_ai_threshold"), 0.45),
            os_override_threshold=_to_float(payload.get("os_override_threshold"), 0.60),
            hardcore_enabled=_to_bool(payload.get("hardcore_enabled"), False),
            hardcore_countdown_seconds=max(5, _to_int(payload.get("hardcore_countdown_seconds"), 30)),
            productive_keywords=productive,
            distracting_keywords=distracting,
        )

    def capture_source(self) -> int | str:
        if self.demo_video_path:
            return self.demo_video_path
        return self.camera_index

    def fusion_payload(self) -> dict[str, Any]:
        return {
            "engagement_threshold": self.engagement_threshold,
            "os_ai_threshold": self.os_ai_threshold,
            "os_override_threshold": self.os_override_threshold,
            "productive_keywords": self.productive_keywords,
            "distracting_keywords": self.distracting_keywords,
            "hardcore_enabled": self.hardcore_enabled,
            "hardcore_countdown_seconds": self.hardcore_countdown_seconds,
        }


class FocusSessionTracker:
    """Runs Phase 2 tracking workers and streams UI-safe telemetry through a queue."""

    def __init__(
        self,
        config: TrackerConfig,
        output_queue: queue.Queue[dict[str, Any]],
        fusion_logic: FusionLogic | None = None,
    ) -> None:
        self.config = config
        self.output_queue = output_queue
        self.fusion_logic = fusion_logic or _default_fusion_logic
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._camera_thread: threading.Thread | None = None
        self._os_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_os_snapshot: dict[str, Any] | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._pause_event.clear()
        self._camera_thread = threading.Thread(target=self._camera_loop, name="focusflow-camera", daemon=True)
        self._os_thread = threading.Thread(target=self._os_loop, name="focusflow-os", daemon=True)
        self._camera_thread.start()
        self._os_thread.start()
        logger.info("FocusSessionTracker started")

    def pause(self) -> None:
        self._pause_event.set()
        self._put({"type": "status", "message": "Tracking paused"})

    def resume(self) -> None:
        self._pause_event.clear()
        self._put({"type": "status", "message": "Tracking resumed"})

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        for thread in [self._camera_thread, self._os_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=1.5)
        logger.info("FocusSessionTracker stopped")

    def _camera_loop(self) -> None:
        detector: FaceFeatureDetector | None = None
        cap: cv2.VideoCapture | None = None
        fps_counter = _FpsCounter()
        frame_index = 0
        last_ai_result: dict[str, Any] | None = None

        try:
            inferencer = ONNXEngagementInferencer(
                threshold=self.config.engagement_threshold,
                smoothing_window=self.config.smoothing_window,
            )
            detector = FaceFeatureDetector(draw_landmarks=self.config.show_landmarks)
            buffer = FeatureSequenceBuffer(
                sequence_length=inferencer.spec.sequence_length,
                frame_feature_dim=inferencer.spec.raw_feature_dim,
            )

            while not self._stop_event.is_set():
                loop_started_at = time.perf_counter()
                if self._pause_event.is_set():
                    if cap is not None:
                        cap.release()
                        cap = None
                        buffer.clear()
                        inferencer.reset()
                    time.sleep(0.2)
                    continue

                if cap is None:
                    cap = self._open_capture()
                    if cap is None:
                        time.sleep(1.0)
                        continue

                ok, frame = cap.read()
                if not ok:
                    if self.config.demo_video_path:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    self._put({"type": "error", "source": "camera", "message": "Không đọc được webcam."})
                    time.sleep(0.5)
                    continue

                frame_index += 1
                detection = detector.extract(frame)
                enriched = buffer.append(detection.feature)
                ai_result: dict[str, Any] = {
                    "probability": 0.0,
                    "focus_score": 0.0,
                    "state": "WARMING_UP",
                    "ready": False,
                }
                if enriched is not None:
                    if detection.face_found:
                        should_infer = (
                            last_ai_result is None
                            or frame_index % INFERENCE_EVERY_N_FRAMES == 0
                        )
                        if should_infer:
                            last_ai_result = inferencer.predict(enriched)
                        ai_result = dict(last_ai_result)
                    else:
                        ai_result = {
                            "probability": 0.0,
                            "raw_probability": 0.0,
                            "focus_score": 0.0,
                            "state": "NO_FACE",
                            "ready": True,
                        }
                        last_ai_result = ai_result

                with self._lock:
                    os_snapshot = dict(self._latest_os_snapshot) if self._latest_os_snapshot else None

                probability = float(ai_result.get("focus_score", 0.0))
                model_ready = bool(ai_result.get("ready", False))
                if model_ready:
                    fusion = self.fusion_logic(probability, os_snapshot, self.config.fusion_payload())
                else:
                    fusion = {
                        "state": "WARMING_UP",
                        "source": "ai_buffer",
                        "reason": "Waiting for enough frames before first model inference.",
                        "ai_probability": probability,
                    }
                latency_ms = (time.perf_counter() - loop_started_at) * 1000.0
                self._put(
                    {
                        "type": "telemetry",
                        "frame": detection.frame if frame_index % PREVIEW_EVERY_N_FRAMES == 0 else None,
                        "feature": detection.feature.tolist(),
                        "face_found": detection.face_found,
                        "latency_ms": latency_ms,
                        "logit": ai_result.get("logit"),
                        "probability": ai_result.get("probability", probability),
                        "raw_probability": ai_result.get("raw_probability", ai_result.get("probability", probability)),
                        "late_fusion_probability": ai_result.get("late_fusion_probability"),
                        "neural_probability": ai_result.get("neural_probability"),
                        "fusion_strategy": ai_result.get("fusion_strategy"),
                        "focus_score": probability,
                        "ai_state": ai_result.get("state", "WARMING_UP"),
                        "model_ready": model_ready,
                        "components": ai_result.get("components"),
                        "weights": ai_result.get("weights"),
                        "state": fusion.get("state", "DISTRACTED"),
                        "fusion": fusion,
                        "os": os_snapshot,
                        "fps": fps_counter.tick(),
                    }
                )
        except Exception as exc:
            logger.exception("Camera tracking loop failed")
            self._put({"type": "error", "source": "camera", "message": str(exc)})
        finally:
            if cap is not None:
                cap.release()
            if detector is not None:
                detector.close()

    def _os_loop(self) -> None:
        tracker = ActiveWindowTracker(
            productive_keywords=self.config.productive_keywords,
            distraction_keywords=self.config.distracting_keywords,
            ai_focus_threshold=self.config.os_ai_threshold,
            heuristic_override_threshold=self.config.os_override_threshold,
        )
        discipline = HardcoreDisciplineController(
            countdown_seconds=self.config.hardcore_countdown_seconds,
        )
        if self.config.hardcore_enabled:
            self._put(
                {
                    "type": "hardcore",
                    "status": "armed",
                    "message": f"Hardcore đang bật. {admin_permission_hint()}",
                    "remaining_seconds": self.config.hardcore_countdown_seconds,
                }
            )
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                discipline.reset()
                time.sleep(0.3)
                continue
            try:
                snapshot = tracker.snapshot().as_dict()
                with self._lock:
                    self._latest_os_snapshot = snapshot
                self._put({"type": "os", "os": snapshot})
                if self.config.hardcore_enabled:
                    action = discipline.evaluate(
                        snapshot=snapshot,
                        distracting_keywords=self.config.distracting_keywords,
                        now=time.monotonic(),
                    )
                    if action is not None:
                        self._put(action.as_dict())
            except Exception as exc:
                logger.debug("OS tracker snapshot failed", exc_info=True)
                self._put({"type": "error", "source": "os", "message": str(exc)})
            time.sleep(1.0)

    def _open_capture(self) -> cv2.VideoCapture | None:
        source = self.config.capture_source()
        if isinstance(source, str) and not Path(source).exists():
            self._put({"type": "error", "source": "camera", "message": f"Không tìm thấy video: {source}"})
            return None

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            self._put({"type": "error", "source": "camera", "message": f"Không mở được nguồn camera/video: {source}"})
            cap.release()
            return None
        return cap

    def _put(self, payload: dict[str, Any]) -> None:
        try:
            self.output_queue.put_nowait(payload)
        except queue.Full:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.output_queue.put_nowait(payload)
            except queue.Full:
                pass


class _FpsCounter:
    def __init__(self) -> None:
        self._last = time.perf_counter()
        self._fps = 0.0

    def tick(self) -> float:
        now = time.perf_counter()
        elapsed = max(now - self._last, 1e-6)
        self._last = now
        instant = 1.0 / elapsed
        self._fps = instant if self._fps <= 0.0 else (self._fps * 0.8 + instant * 0.2)
        return self._fps


def _default_fusion_logic(ai_probability: float, os_snapshot: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    threshold = _to_float(config.get("engagement_threshold"), 0.54)
    state = "FOCUSED" if ai_probability >= threshold else "DISTRACTED"
    return {
        "state": state,
        "source": "ai",
        "reason": "Fallback AI-only fusion.",
        "ai_probability": ai_probability,
        "os_state": "UNKNOWN",
    }


def _split_keywords(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [item.strip().lower() for item in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(item).strip().lower() for item in value]
    else:
        items = list(default)
    cleaned = tuple(item for item in items if item)
    return cleaned or default


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
