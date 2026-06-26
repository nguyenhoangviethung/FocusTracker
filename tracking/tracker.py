from __future__ import annotations

from dataclasses import dataclass
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from collections import deque

from edge.cloud_client import CloudClientConfig, FocusFlowCloudClient
from shared.contracts import SessionCreate, SessionSummary, TelemetryPacket
from tracking.buffer import DEPTH_ROBUST_V2_FRAME_FEATURE_DIM, FeatureSequenceBuffer, SEQUENCE_LENGTH
from utils.logger import get_logger


logger = get_logger("tracker")


INFERENCE_EVERY_N_FRAMES = 3
PREVIEW_EVERY_N_FRAMES = 2
CLOUD_TELEMETRY_INTERVAL_SECONDS = 1.0
FOCUS_THRESHOLD = 0.5
@dataclass(slots=True)
class TrackerConfig:
    camera_index: int = 0
    demo_video_path: str = ""
    show_landmarks: bool = True
    camera_distance_scale: float = 0.085
    engagement_threshold: float = 0.54
    smoothing_window: int = 5
    inference_mode: str = "local"
    cloud_api_url: str = ""
    cloud_api_key: str = ""
    device_id: str = ""
    user_id: str = ""
    session_duration_seconds: int = 25 * 60

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrackerConfig":
        return cls(
            camera_index=_to_int(payload.get("camera_index"), 0),
            demo_video_path=str(payload.get("demo_video_path") or "").strip(),
            show_landmarks=_to_bool(payload.get("show_landmarks"), True),
            camera_distance_scale=_to_float(payload.get("camera_distance_scale"), 0.18),
            engagement_threshold=_to_float(payload.get("engagement_threshold"), 0.54),
            smoothing_window=max(3, min(5, _to_int(payload.get("smoothing_window"), 5))),
            inference_mode=_normalize_inference_mode(
                os.getenv("FOCUSFLOW_INFERENCE_MODE", "") or payload.get("inference_mode")
            ),
            cloud_api_url=str(
                os.getenv("FOCUSFLOW_CLOUD_API_URL", "")
                or payload.get("cloud_api_url")
            ).strip(),
            cloud_api_key=str(
                os.getenv("FOCUSFLOW_CLOUD_API_KEY", "")
                or os.getenv("FOCUSFLOW_API_KEY", "")
                or payload.get("cloud_api_key")
            ).strip(),
            device_id=str(
                payload.get("device_id")
                or os.getenv("FOCUSFLOW_DEVICE_ID", "")
            ).strip(),
            user_id=str(
                payload.get("auth_user_id")
                or payload.get("user_id")
                or ""
            ).strip(),
            session_duration_seconds=max(
                1,
                _to_int(
                    payload.get("session_duration_seconds"),
                    _to_int(payload.get("pomodoro_minutes"), 25) * 60,
                ),
            ),
        )

    def capture_source(self) -> int | str:
        if self.demo_video_path:
            return self.demo_video_path
        return self.camera_index

class FocusSessionTracker:
    """Runs the vision pipeline and streams UI-safe telemetry through a queue."""

    def __init__(
        self,
        config: TrackerConfig,
        output_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        self.config = config
        self.output_queue = output_queue
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._camera_thread: threading.Thread | None = None
        self._network_thread: threading.Thread | None = None
        self._local_thread: threading.Thread | None = None
        self._local_packets: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)
        self._local_responses: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2)
        self._cloud_packets: queue.Queue[TelemetryPacket] = queue.Queue(maxsize=2)
        self._cloud_responses: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=4)
        self._cloud_session_id = ""
        self._cloud_sequence = 0
        self._last_cloud_packet_at = 0.0
        self._cloud_client: FocusFlowCloudClient | None = None
        self._recent_features: deque[np.ndarray] = deque(maxlen=5)

    @property
    def cloud_session_id(self) -> str:
        return self._cloud_session_id

    def start(self) -> None:
        self._stop_event.clear()
        self._pause_event.clear()
        if self._uses_local_inference:
            self._local_thread = threading.Thread(
                target=self._local_inference_loop,
                name="focusflow-local-inference",
                daemon=True,
            )
            self._local_thread.start()
        self._network_thread = threading.Thread(
            target=self._network_loop,
            name="focusflow-network",
            daemon=True,
        )
        self._network_thread.start()
        self._camera_thread = threading.Thread(target=self._camera_loop, name="focusflow-camera", daemon=True)
        self._camera_thread.start()
        logger.info(
            "FocusSessionTracker started mode=%s cloud_url_configured=%s "
            "cloud_key_configured=%s device_id=%s user_id=%s",
            self.config.inference_mode,
            bool(self.config.cloud_api_url),
            bool(self.config.cloud_api_key),
            self.config.device_id or "missing",
            self.config.user_id or "anonymous",
        )

    def pause(self) -> None:
        self._pause_event.set()
        self._put({"type": "status", "message": "Tracking paused"})

    def resume(self) -> None:
        self._pause_event.clear()
        self._put({"type": "status", "message": "Tracking resumed"})

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        for thread in [self._camera_thread, self._local_thread, self._network_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=1.5)
        logger.info("FocusSessionTracker stopped")

    @property
    def _uses_local_inference(self) -> bool:
        return self.config.inference_mode in {"local", "hybrid"}

    @property
    def _uses_cloud_inference(self) -> bool:
        return self.config.inference_mode in {"cloud", "hybrid"}

    def complete_cloud_session(self, summary: dict[str, Any]) -> None:
        if self._cloud_client is None or not self._cloud_session_id:
            return
        payload = SessionSummary(
            duration_seconds=max(0, _to_int(summary.get("total_seconds"), 0)),
            focused_seconds=max(0, _to_int(summary.get("focused_seconds"), 0)),
            average_focus=max(
                0.0,
                min(1.0, _to_float(summary.get("average_score"), 0.0)),
            ),
            distraction_count=max(0, _to_int(summary.get("distraction_count"), 0)),
            focus_streak_seconds=max(
                0.0,
                _to_float(summary.get("focus_streak_seconds"), 0.0),
            ),
            completed=_to_bool(summary.get("completed"), False),
            minute_focus_scores=[
                max(0.0, min(1.0, _to_float(value, 0.0)))
                for value in summary.get("minute_scores", [])
            ],
        )
        threading.Thread(
            target=self._complete_cloud_request,
            args=(payload,),
            name="focusflow-cloud-complete",
            daemon=True,
        ).start()

    def _complete_cloud_request(self, summary: SessionSummary) -> None:
        try:
            assert self._cloud_client is not None
            self._cloud_client.complete_session(self._cloud_session_id, summary)
        except Exception:
            logger.warning("Unable to complete cloud session", exc_info=True)

    def _camera_loop(self) -> None:
        from tracking.detector import FaceFeatureDetector

        detector: FaceFeatureDetector | None = None
        cap: cv2.VideoCapture | None = None
        fps_counter = _FpsCounter()
        frame_index = 0
        last_ai_result: dict[str, Any] | None = None

        try:
            detector = FaceFeatureDetector(
                draw_landmarks=self.config.show_landmarks,
                camera_distance_scale=self.config.camera_distance_scale,
            )
            buffer = FeatureSequenceBuffer(
                sequence_length=SEQUENCE_LENGTH,
                frame_feature_dim=DEPTH_ROBUST_V2_FRAME_FEATURE_DIM,
            )

            while not self._stop_event.is_set():
                loop_started_at = time.perf_counter()
                if self._pause_event.is_set():
                    if cap is not None:
                        cap.release()
                        cap = None
                        buffer.clear()
                        self._recent_features.clear()
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
                try:
                    detection = detector.extract(frame)
                except Exception as exc:
                    logger.warning("Skipping unreadable frame", exc_info=True)
                    self._put(
                        {
                            "type": "status",
                            "message": f"Skipped bad frame: {exc.__class__.__name__}",
                        }
                    )
                    continue

                if not self._is_valid_feature_vector(detection.feature):
                    logger.warning("Skipping invalid feature vector from detector")
                    continue

                if not self._is_feature_stable(detection.feature):
                    logger.warning("Skipping unstable feature vector that differs too much from recent frames")
                    continue

                if not detection.face_found:
                    ai_result = {
                        "probability": 0.0,
                        "raw_probability": 0.0,
                        "focus_score": 0.0,
                        "state": "NO_FACE",
                        "ready": True,
                    }
                    probability = 0.0
                    model_ready = True
                    state = "NO_FACE"
                    latency_ms = (time.perf_counter() - loop_started_at) * 1000.0
                    self._put(
                        {
                            "type": "telemetry",
                            "frame": detection.frame if frame_index % PREVIEW_EVERY_N_FRAMES == 0 else None,
                            "feature": detection.feature.tolist(),
                            "face_found": detection.face_found,
                            "latency_ms": latency_ms,
                            "client_loop_latency_ms": latency_ms,
                            "model_inference_latency_ms": 0.0,
                            "cloud_roundtrip_latency_ms": None,
                            "logit": None,
                            "probability": probability,
                            "raw_probability": probability,
                            "focus_score": probability,
                            "ai_state": ai_result.get("state", "NO_FACE"),
                            "model_ready": model_ready,
                            "components": None,
                            "weights": None,
                            "inference_source": "edge" if self._uses_local_inference else "cloud",
                            "state": state,
                            "fps": fps_counter.tick(),
                        }
                    )
                    continue

                enriched = buffer.append(detection.feature)
                self._recent_features.append(np.asarray(detection.feature, dtype=np.float32).reshape(-1).copy())
                raw_sequence = buffer.raw_sequence()
                ai_result: dict[str, Any] = {
                    "probability": 0.0,
                    "focus_score": 0.0,
                    "state": "WARMING_UP",
                    "ready": False,
                }
                if enriched is not None:
                    should_infer = frame_index % INFERENCE_EVERY_N_FRAMES == 0
                    if should_infer:
                        if self._uses_local_inference:
                            self._queue_local_sequence(enriched)
                        if self._uses_cloud_inference and raw_sequence is not None:
                            self._queue_cloud_packet(raw_sequence, detection.face_found)

                    local_result = self._latest_local_result()
                    cloud_result = self._latest_cloud_result()
                    # Hybrid is edge-first: cloud responses are a synchronized
                    # comparison path and a recovery path if local loading fails.
                    selected_result = (
                        local_result if self._uses_local_inference and local_result is not None
                        else cloud_result if self._uses_cloud_inference and cloud_result is not None
                        else None
                    )
                    if selected_result is not None:
                        last_ai_result = selected_result
                        ai_result = dict(selected_result)
                    elif last_ai_result is not None:
                        ai_result = dict(last_ai_result)

                probability = float(ai_result.get("focus_score", ai_result.get("probability", 0.0)))
                model_ready = bool(ai_result.get("ready", False))
                if model_ready:
                    raw_state = str(ai_result.get("state", "DISTRACTED"))
                    if raw_state in {"FOCUSED", "DISTRACTED", "NO_FACE"}:
                        state = raw_state
                    else:
                        state = "FOCUSED" if raw_state in {"ENGAGED", "FOCUSED"} else "DISTRACTED"
                else:
                    state = "WARMING_UP"
                latency_ms = (time.perf_counter() - loop_started_at) * 1000.0
                model_inference_latency_ms = ai_result.get("model_inference_latency_ms")
                cloud_roundtrip_latency_ms = ai_result.get("cloud_roundtrip_latency_ms")
                self._put(
                    {
                        "type": "telemetry",
                        "frame": detection.frame if frame_index % PREVIEW_EVERY_N_FRAMES == 0 else None,
                        "feature": detection.feature.tolist(),
                        "face_found": detection.face_found,
                        "latency_ms": latency_ms,
                        "client_loop_latency_ms": latency_ms,
                        "model_inference_latency_ms": model_inference_latency_ms,
                        "cloud_roundtrip_latency_ms": cloud_roundtrip_latency_ms,
                        "probability": ai_result.get("probability", probability),
                        "raw_probability": ai_result.get("raw_probability", ai_result.get("probability", probability)),
                        "focus_score": probability,
                        "ai_state": ai_result.get("ai_state", ai_result.get("state", "WARMING_UP")),
                        "model_ready": model_ready,
                        "components": ai_result.get("components"),
                        "weights": ai_result.get("weights"),
                        "inference_source": ai_result.get(
                            "inference_source",
                            "cloud",
                        ),
                        "state": state,
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

    def _network_loop(self) -> None:
        if not self.config.cloud_api_url or not self.config.cloud_api_key or not self.config.device_id:
            if self.config.inference_mode == "local":
                self._put(
                    {
                        "type": "network_status",
                        "status": "local_only",
                        "message": "Edge inference is active; cloud sync is not configured.",
                    }
                )
                return
            missing = [
                name
                for name, value in (
                    ("Cloud API URL", self.config.cloud_api_url),
                    ("API key", self.config.cloud_api_key),
                    ("device ID", self.config.device_id),
                )
                if not value
            ]
            self._put(
                {
                    "type": "network_status",
                    "status": "disabled",
                    "message": f"Missing: {', '.join(missing)}.",
                }
            )
            return

        client = FocusFlowCloudClient(
            CloudClientConfig(
                base_url=self.config.cloud_api_url,
                api_key=self.config.cloud_api_key,
                device_id=self.config.device_id,
            )
        )
        self._cloud_client = client
        attempt = 0
        while not self._stop_event.is_set() and not self._cloud_session_id:
            try:
                record = client.create_session(
                    SessionCreate(
                        device_id=self.config.device_id,
                        user_id=self.config.user_id or None,
                        duration_seconds=self.config.session_duration_seconds,
                    )
                )
                self._cloud_session_id = str(record["session_id"])
                logger.info("Cloud session created session_id=%s", self._cloud_session_id)
                self._put(
                    {
                        "type": "network_status",
                        "status": "session_created",
                        "session_id": self._cloud_session_id,
                    }
                )
            except Exception as exc:
                attempt += 1
                delay = min(30.0, float(2 ** min(attempt, 5)))
                self._put(
                    {
                        "type": "network_status",
                        "status": "reconnecting",
                        "message": str(exc),
                        "retry_in_seconds": delay,
                    }
                )
                self._stop_event.wait(delay)

        if self._cloud_session_id and not self._stop_event.is_set() and self._uses_cloud_inference:
            client.run_telemetry_loop(
                self._cloud_session_id,
                self._cloud_packets,
                self._cloud_responses,
                self._stop_event,
            )
        elif self._cloud_session_id and not self._stop_event.is_set():
            self._put(
                {
                    "type": "network_status",
                    "status": "session_created",
                    "session_id": self._cloud_session_id,
                    "message": "Edge inference active; cloud stores lifecycle and summary only.",
                }
            )
            self._stop_event.wait()

    def _queue_cloud_packet(self, raw_sequence, face_found: bool) -> None:
        if not self._uses_cloud_inference or not self._cloud_session_id:
            return
        now = time.monotonic()
        if now - self._last_cloud_packet_at < CLOUD_TELEMETRY_INTERVAL_SECONDS:
            return
        self._last_cloud_packet_at = now
        self._cloud_sequence += 1
        packet = TelemetryPacket(
            session_id=self._cloud_session_id,
            device_id=self.config.device_id,
            sequence_number=self._cloud_sequence,
            raw_feature_sequence=raw_sequence.tolist(),
            face_found=face_found,
            configuration={
                "decision_rule": "argmax_4class",
                "feature_schema": "depth_robust_v2",
                "temporal_enrichment": "velocity_std",
            },
        )
        try:
            self._cloud_packets.put_nowait(packet)
        except queue.Full:
            try:
                self._cloud_packets.get_nowait()
            except queue.Empty:
                pass
            try:
                self._cloud_packets.put_nowait(packet)
            except queue.Full:
                pass

    def _queue_local_sequence(self, enriched_sequence: np.ndarray) -> None:
        try:
            self._local_packets.put_nowait(np.asarray(enriched_sequence, dtype=np.float32).copy())
        except queue.Full:
            try:
                self._local_packets.get_nowait()
            except queue.Empty:
                pass
            try:
                self._local_packets.put_nowait(np.asarray(enriched_sequence, dtype=np.float32).copy())
            except queue.Full:
                pass

    def _local_inference_loop(self) -> None:
        try:
            from tracking.inference import DeepForestInferencer

            inferencer = DeepForestInferencer()
        except Exception as exc:
            logger.exception("Unable to load edge DeepForest model")
            self._put(
                {
                    "type": "status",
                    "message": f"Edge model unavailable: {exc.__class__.__name__}",
                }
            )
            return

        while not self._stop_event.is_set():
            try:
                sequence = self._local_packets.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                prediction = inferencer.predict(sequence)
                focus_score = float(prediction.get("focus_score", prediction.get("probability", 0.0)))
                self._put_latest(
                    self._local_responses,
                    {
                        **prediction,
                        "probability": focus_score,
                        "focus_score": focus_score,
                        "state": "FOCUSED" if focus_score > FOCUS_THRESHOLD else "DISTRACTED",
                        "ai_state": prediction.get("state", "DISTRACTED"),
                        "inference_source": "edge",
                        "cloud_roundtrip_latency_ms": None,
                    },
                )
            except Exception:
                logger.exception("Edge DeepForest inference failed")
                self._put({"type": "status", "message": "Edge inference failed; waiting for next window."})

    def _latest_local_result(self) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        while True:
            try:
                latest = self._local_responses.get_nowait()
            except queue.Empty:
                return latest

    def _latest_cloud_result(self) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        while True:
            try:
                payload = self._cloud_responses.get_nowait()
            except queue.Empty:
                break
            if payload.get("type") == "network_status":
                self._put(payload)
                continue
            if "focus_score" in payload:
                latest = {
                    **payload,
                    "probability": payload.get("focus_score", 0.0),
                    "ready": True,
                    "state": payload.get("state", payload.get("ai_state", "DISTRACTED")),
                    "ai_state": payload.get("ai_state", "DISTRACTED"),
                    "inference_source": "cloud",
                }
        return latest

    @staticmethod
    def _put_latest(target: queue.Queue[Any], payload: Any) -> None:
        try:
            target.put_nowait(payload)
        except queue.Full:
            try:
                target.get_nowait()
            except queue.Empty:
                pass
            try:
                target.put_nowait(payload)
            except queue.Full:
                pass

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

    @staticmethod
    def _is_valid_feature_vector(feature: Any) -> bool:
        try:
            vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        except Exception:
            return False
        return vector.shape[0] == DEPTH_ROBUST_V2_FRAME_FEATURE_DIM and np.isfinite(vector).all()

    def _is_feature_stable(self, feature: Any) -> bool:
        vector = np.asarray(feature, dtype=np.float32).reshape(-1)
        if vector.shape[0] != DEPTH_ROBUST_V2_FRAME_FEATURE_DIM or not np.isfinite(vector).all():
            return False
        if len(self._recent_features) < 3:
            return True
        recent = np.stack(tuple(self._recent_features), axis=0)
        median = np.median(recent, axis=0)
        mean_abs_delta = float(np.mean(np.abs(vector - median)))
        max_abs_delta = float(np.max(np.abs(vector - median)))
        return mean_abs_delta <= 0.35 and max_abs_delta <= 2.5


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


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _normalize_inference_mode(value: Any) -> str:
    mode = str(value or "local").strip().lower()
    return mode if mode in {"local", "cloud", "hybrid"} else "local"


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
