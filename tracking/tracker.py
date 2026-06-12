from __future__ import annotations

from dataclasses import dataclass
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

import cv2

from edge.cloud_client import CloudClientConfig, FocusFlowCloudClient
from shared.contracts import SessionCreate, SessionSummary, TelemetryPacket
from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from tracking.inference import ONNXEngagementInferencer
from utils.logger import get_logger


logger = get_logger("tracker")


INFERENCE_EVERY_N_FRAMES = 3
PREVIEW_EVERY_N_FRAMES = 2
VALID_INFERENCE_MODES = {"local", "cloud", "hybrid"}


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
    session_duration_seconds: int = 25 * 60

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrackerConfig":
        inference_mode = str(payload.get("inference_mode") or "local").strip().lower()
        if inference_mode not in VALID_INFERENCE_MODES:
            inference_mode = "local"
        return cls(
            camera_index=_to_int(payload.get("camera_index"), 0),
            demo_video_path=str(payload.get("demo_video_path") or "").strip(),
            show_landmarks=_to_bool(payload.get("show_landmarks"), True),
            camera_distance_scale=_to_float(payload.get("camera_distance_scale"), 0.18),
            engagement_threshold=_to_float(payload.get("engagement_threshold"), 0.54),
            smoothing_window=max(3, min(5, _to_int(payload.get("smoothing_window"), 5))),
            inference_mode=inference_mode,
            cloud_api_url=str(
                payload.get("cloud_api_url")
                or os.getenv("FOCUSFLOW_CLOUD_API_URL", "")
            ).strip(),
            cloud_api_key=str(
                payload.get("cloud_api_key")
                or os.getenv("FOCUSFLOW_CLOUD_API_KEY", "")
            ).strip(),
            device_id=str(
                payload.get("device_id")
                or os.getenv("FOCUSFLOW_DEVICE_ID", "")
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
        self._cloud_packets: queue.Queue[TelemetryPacket] = queue.Queue(maxsize=2)
        self._cloud_responses: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=4)
        self._cloud_session_id = ""
        self._cloud_sequence = 0
        self._cloud_client: FocusFlowCloudClient | None = None

    @property
    def cloud_session_id(self) -> str:
        return self._cloud_session_id

    def start(self) -> None:
        self._stop_event.clear()
        self._pause_event.clear()
        if self.config.inference_mode in {"cloud", "hybrid"}:
            self._network_thread = threading.Thread(
                target=self._network_loop,
                name="focusflow-network",
                daemon=True,
            )
            self._network_thread.start()
        self._camera_thread = threading.Thread(target=self._camera_loop, name="focusflow-camera", daemon=True)
        self._camera_thread.start()
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
        for thread in [self._camera_thread, self._network_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=1.5)
        logger.info("FocusSessionTracker stopped")

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
        detector: FaceFeatureDetector | None = None
        cap: cv2.VideoCapture | None = None
        fps_counter = _FpsCounter()
        frame_index = 0
        last_ai_result: dict[str, Any] | None = None

        try:
            inferencer = None
            if self.config.inference_mode in {"local", "hybrid"}:
                inferencer = ONNXEngagementInferencer(
                    threshold=self.config.engagement_threshold,
                    smoothing_window=self.config.smoothing_window,
                )
            detector = FaceFeatureDetector(
                draw_landmarks=self.config.show_landmarks,
                camera_distance_scale=self.config.camera_distance_scale,
            )
            buffer = FeatureSequenceBuffer(
                sequence_length=30,
                frame_feature_dim=30,
            )

            while not self._stop_event.is_set():
                loop_started_at = time.perf_counter()
                if self._pause_event.is_set():
                    if cap is not None:
                        cap.release()
                        cap = None
                        buffer.clear()
                        if inferencer is not None:
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
                raw_sequence = buffer.raw_sequence()
                ai_result: dict[str, Any] = {
                    "probability": 0.0,
                    "focus_score": 0.0,
                    "state": "WARMING_UP",
                    "ready": False,
                }
                if enriched is not None:
                    should_infer = last_ai_result is None or frame_index % INFERENCE_EVERY_N_FRAMES == 0
                    if (
                        should_infer
                        and raw_sequence is not None
                        and self.config.inference_mode in {"cloud", "hybrid"}
                    ):
                        self._queue_cloud_packet(raw_sequence, detection.face_found)

                    cloud_result = self._latest_cloud_result()
                    if cloud_result is not None:
                        last_ai_result = cloud_result
                        ai_result = dict(cloud_result)
                    elif detection.face_found and inferencer is not None:
                        if should_infer:
                            last_ai_result = inferencer.predict(enriched)
                        ai_result = dict(last_ai_result)
                    elif detection.face_found and last_ai_result is not None:
                        ai_result = dict(last_ai_result)
                    elif not detection.face_found:
                        ai_result = {
                            "probability": 0.0,
                            "raw_probability": 0.0,
                            "focus_score": 0.0,
                            "state": "NO_FACE",
                            "ready": True,
                        }
                        last_ai_result = ai_result

                probability = float(ai_result.get("focus_score", 0.0))
                model_ready = bool(ai_result.get("ready", False))
                if model_ready:
                    state = (
                        "FOCUSED"
                        if str(ai_result.get("state", "DISTRACTED")) == "ENGAGED"
                        else "DISTRACTED"
                    )
                else:
                    state = "WARMING_UP"
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
                        "inference_source": ai_result.get(
                            "inference_source",
                            "local" if inferencer is not None else "cloud",
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
            self._put(
                {
                    "type": "network_status",
                    "status": "disabled",
                    "message": "Cloud mode requires URL, API key, and device ID.",
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
                        duration_seconds=self.config.session_duration_seconds,
                    )
                )
                self._cloud_session_id = str(record["session_id"])
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

        if self._cloud_session_id and not self._stop_event.is_set():
            client.run_telemetry_loop(
                self._cloud_session_id,
                self._cloud_packets,
                self._cloud_responses,
                self._stop_event,
            )

    def _queue_cloud_packet(self, raw_sequence, face_found: bool) -> None:
        if not self._cloud_session_id:
            return
        self._cloud_sequence += 1
        packet = TelemetryPacket(
            session_id=self._cloud_session_id,
            device_id=self.config.device_id,
            sequence_number=self._cloud_sequence,
            raw_feature_sequence=raw_sequence.tolist(),
            face_found=face_found,
            configuration={"engagement_threshold": self.config.engagement_threshold},
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
                    "state": payload.get("ai_state", "DISTRACTED"),
                    "inference_source": "cloud",
                }
        return latest

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
