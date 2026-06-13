from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter, sleep
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse, urlunparse

import cv2
import httpx
from websockets.sync.client import connect

from shared.contracts import SessionCreate, SessionSummary, TelemetryPacket, utc_now
from tracking.buffer import FeatureSequenceBuffer


class DemoStepError(RuntimeError):
    def __init__(self, stage: str, message: str, *, session_id: str | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.session_id = session_id


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)


@dataclass(slots=True)
class VirtualClientConfig:
    api_url: str
    api_key: str
    device_id: str
    request_timeout_seconds: float = 30.0


def websocket_url(base_url: str, session_id: str, device_id: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/v1/ws/sessions/{quote(session_id, safe='')}"
    query = f"device_id={quote(device_id, safe='')}"
    return urlunparse((scheme, parsed.netloc, path, "", query, ""))


def load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid fixture format: {path}")
    return payload


def _open_video_sequence(video_path: Path) -> dict[str, Any]:
    try:
        from tracking.detector import FaceFeatureDetector
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mediapipe is required for live video replay. Install requirements/dev.txt "
            "before running demo.run_video_clients."
        ) from exc

    detector = FaceFeatureDetector(draw_landmarks=False)
    try:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        buffer = FeatureSequenceBuffer(sequence_length=30, frame_feature_dim=30)
        sequence = None
        face_found = False
        frame_count = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frame_count += 1
                detection = detector.extract(frame)
                face_found = face_found or detection.face_found
                sequence = buffer.append(detection.feature)
                if sequence is not None:
                    break
        finally:
            capture.release()
        raw_sequence = buffer.raw_sequence()
        if raw_sequence is None:
            raise RuntimeError(f"Unable to build a 30-frame sequence from {video_path}")
        return {
            "face_found": face_found,
            "frame_count": frame_count,
            "raw_feature_sequence": raw_sequence.tolist(),
        }
    finally:
        detector.close()


def replay_session(
    config: VirtualClientConfig,
    *,
    raw_feature_sequence: list[list[float]],
    face_found: bool,
    session_duration_seconds: int,
    user_id: str | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    session_id = ""
    with httpx.Client(
        base_url=config.api_url.rstrip("/"),
        headers={"X-API-Key": config.api_key},
        timeout=config.request_timeout_seconds,
    ) as client:
        try:
            _log(log, "create_session:start")
            create_started = perf_counter()
            created = client.post(
                "/v1/sessions",
                json=SessionCreate(
                    device_id=config.device_id,
                    user_id=user_id,
                    duration_seconds=session_duration_seconds,
                ).model_dump(mode="json"),
            )
            created.raise_for_status()
            session_id = str(created.json()["session_id"])
            create_latency_ms = (perf_counter() - create_started) * 1000.0
            _log(log, f"create_session:ok latency_ms={create_latency_ms:.1f} session_id={session_id}")
        except Exception as exc:
            raise DemoStepError("create_session", f"{type(exc).__name__}: {exc}") from exc

    packet = TelemetryPacket(
        session_id=session_id,
        device_id=config.device_id,
        sequence_number=1,
        raw_feature_sequence=raw_feature_sequence,
        face_found=face_found,
        configuration={"demo": True},
    )

    try:
        _log(log, "websocket:open:start")
        ws_started = perf_counter()
        with connect(
            websocket_url(config.api_url, session_id, config.device_id),
            additional_headers={"X-API-Key": config.api_key},
            open_timeout=config.request_timeout_seconds,
            close_timeout=config.request_timeout_seconds,
        ) as websocket:
            _log(log, "websocket:open:ok")
            websocket.send(packet.model_dump_json())
            _log(log, "websocket:stream:sent")
            response = json.loads(websocket.recv())
            _log(log, "websocket:stream:recv")
        ws_latency_ms = (perf_counter() - ws_started) * 1000.0
    except Exception as exc:
        raise DemoStepError("websocket_stream", f"{type(exc).__name__}: {exc}", session_id=session_id) from exc

    summary = SessionSummary(
        duration_seconds=session_duration_seconds,
        focused_seconds=max(0, session_duration_seconds - 2),
        average_focus=float(response.get("focus_score", 0.0)),
        distraction_count=0,
        focus_streak_seconds=1.0,
        completed=True,
        minute_focus_scores=[float(response.get("focus_score", 0.0))],
    )

    try:
        _log(log, "complete_session:start")
        complete_started = perf_counter()
        with httpx.Client(
            base_url=config.api_url.rstrip("/"),
            headers={"X-API-Key": config.api_key},
            timeout=config.request_timeout_seconds,
        ) as client:
            completed = client.post(
                f"/v1/sessions/{quote(session_id, safe='')}/complete",
                json=summary.model_dump(mode="json"),
            )
            completed.raise_for_status()
        complete_latency_ms = (perf_counter() - complete_started) * 1000.0
        _log(log, f"complete_session:ok latency_ms={complete_latency_ms:.1f}")
    except Exception as exc:
        raise DemoStepError("complete_session", f"{type(exc).__name__}: {exc}", session_id=session_id) from exc

    return {
        "session_id": session_id,
        "response": response,
        "complete": completed.json(),
        "create_latency_ms": create_latency_ms,
        "ws_latency_ms": ws_latency_ms,
        "complete_latency_ms": complete_latency_ms,
    }


def replay_video_session(
    config: VirtualClientConfig,
    video_path: Path,
    *,
    user_id: str | None = None,
    packet_interval_seconds: float = 1.0,
    playback_speed: float = 1.0,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    try:
        from tracking.detector import FaceFeatureDetector
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mediapipe is required for live video replay. Install requirements/dev.txt "
            "before running demo.run_video_clients."
        ) from exc

    detector = FaceFeatureDetector(draw_landmarks=False)
    try:
        probe = cv2.VideoCapture(str(video_path))
        if not probe.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")
        fps = float(probe.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        total_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        probe.release()

        base_duration_seconds = (total_frames / fps) if total_frames > 0 else 10.0
        session_duration_seconds = max(1, int(round(base_duration_seconds)) or 1)
        buffer = FeatureSequenceBuffer(sequence_length=30, frame_feature_dim=30)
        face_found = False
        frame_count = 0
        packets: list[dict[str, Any]] = []
        latest_response: dict[str, Any] = {}
        next_send_at = max(0.0, float(packet_interval_seconds))

        with httpx.Client(
            base_url=config.api_url.rstrip("/"),
            headers={"X-API-Key": config.api_key},
            timeout=config.request_timeout_seconds,
        ) as client:
            try:
                _log(log, "create_session:start")
                create_started = perf_counter()
                created = client.post(
                    "/v1/sessions",
                    json=SessionCreate(
                        device_id=config.device_id,
                        user_id=user_id,
                        duration_seconds=session_duration_seconds,
                    ).model_dump(mode="json"),
                )
                created.raise_for_status()
                session_id = str(created.json()["session_id"])
                create_latency_ms = (perf_counter() - create_started) * 1000.0
                _log(log, f"create_session:ok latency_ms={create_latency_ms:.1f} session_id={session_id}")
            except Exception as exc:
                raise DemoStepError("create_session", f"{type(exc).__name__}: {exc}") from exc

        try:
            _log(log, "websocket:open:start")
            ws_started = perf_counter()
            playback_started = perf_counter()
            with connect(
                websocket_url(config.api_url, session_id, config.device_id),
                additional_headers={"X-API-Key": config.api_key},
                open_timeout=config.request_timeout_seconds,
                close_timeout=config.request_timeout_seconds,
            ) as websocket:
                _log(log, "websocket:open:ok")
                video_capture = cv2.VideoCapture(str(video_path))
                if not video_capture.isOpened():
                    raise RuntimeError(f"Cannot reopen video: {video_path}")
                try:
                    while True:
                        ok, frame = video_capture.read()
                        if not ok:
                            break
                        frame_count += 1
                        detection = detector.extract(frame)
                        face_found = face_found or detection.face_found
                        buffer.append(detection.feature)
                        raw_sequence = buffer.raw_sequence()
                        if raw_sequence is None:
                            continue

                        current_time = frame_count / fps if fps > 0 else frame_count / 30.0
                        if current_time + 1e-6 < next_send_at:
                            continue

                        packet = TelemetryPacket(
                            session_id=session_id,
                            device_id=config.device_id,
                            sequence_number=len(packets) + 1,
                            raw_feature_sequence=raw_sequence.tolist(),
                            face_found=face_found,
                            captured_at=utc_now(),
                            configuration={
                                "demo": True,
                                "realtime": True,
                                "interval_seconds": packet_interval_seconds,
                            },
                        )
                        _log(log, f"websocket:stream:send packet={len(packets) + 1} frame={frame_count}")
                        websocket.send(packet.model_dump_json())
                        latest_response = json.loads(websocket.recv())
                        packets.append(latest_response)
                        _log(log, f"websocket:stream:recv packet={len(packets)} state={latest_response.get('state')}")
                        next_send_at = current_time + max(0.1, float(packet_interval_seconds))

                        if playback_speed > 0:
                            target_elapsed = current_time / playback_speed
                            actual_elapsed = perf_counter() - playback_started
                            if target_elapsed > actual_elapsed:
                                sleep(min(target_elapsed - actual_elapsed, 0.25))
                finally:
                    video_capture.release()
            ws_latency_ms = (perf_counter() - ws_started) * 1000.0
        except Exception as exc:
            raise DemoStepError("websocket_stream", f"{type(exc).__name__}: {exc}", session_id=session_id) from exc
    finally:
        detector.close()

    if not packets:
        raise RuntimeError(f"No telemetry packets were sent for {video_path}")

    focus_scores = [float(item.get("focus_score", 0.0)) for item in packets]
    focused_count = sum(1 for item in packets if str(item.get("state", "")).upper() == "FOCUSED")
    summary = SessionSummary(
        duration_seconds=session_duration_seconds,
        focused_seconds=int(round((focused_count / len(packets)) * session_duration_seconds)),
        average_focus=float(sum(focus_scores) / len(focus_scores)) if focus_scores else 0.0,
        distraction_count=max(0, len(packets) - focused_count),
        focus_streak_seconds=float(min(session_duration_seconds, len(packets) * max(0.1, float(packet_interval_seconds)))),
        completed=True,
        minute_focus_scores=focus_scores,
    )

    try:
        _log(log, "complete_session:start")
        complete_started = perf_counter()
        with httpx.Client(
            base_url=config.api_url.rstrip("/"),
            headers={"X-API-Key": config.api_key},
            timeout=config.request_timeout_seconds,
        ) as client:
            completed = client.post(
                f"/v1/sessions/{quote(session_id, safe='')}/complete",
                json=summary.model_dump(mode="json"),
            )
            completed.raise_for_status()
        complete_latency_ms = (perf_counter() - complete_started) * 1000.0
        _log(log, f"complete_session:ok latency_ms={complete_latency_ms:.1f}")
    except Exception as exc:
        raise DemoStepError("complete_session", f"{type(exc).__name__}: {exc}", session_id=session_id) from exc

    return {
        "session_id": session_id,
        "response": latest_response,
        "complete": completed.json(),
        "create_latency_ms": create_latency_ms,
        "ws_latency_ms": (perf_counter() - ws_started) * 1000.0,
        "complete_latency_ms": complete_latency_ms,
        "packets_sent": len(packets),
        "frame_count": frame_count,
    }
