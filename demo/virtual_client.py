from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import cv2
import httpx
from websockets.sync.client import connect

from shared.contracts import SessionCreate, SessionSummary, TelemetryPacket
from tracking.buffer import FeatureSequenceBuffer


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
        if sequence is None:
            raise RuntimeError(f"Unable to build a 30-frame sequence from {video_path}")
        return {
            "face_found": face_found,
            "frame_count": frame_count,
            "raw_feature_sequence": sequence.tolist(),
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
) -> dict[str, Any]:
    with httpx.Client(
        base_url=config.api_url.rstrip("/"),
        headers={"X-API-Key": config.api_key},
        timeout=config.request_timeout_seconds,
    ) as client:
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

    packet = TelemetryPacket(
        session_id=session_id,
        device_id=config.device_id,
        sequence_number=1,
        raw_feature_sequence=raw_feature_sequence,
        face_found=face_found,
        configuration={"demo": True},
    )

    ws_started = perf_counter()
    with connect(
        websocket_url(config.api_url, session_id, config.device_id),
        additional_headers={"X-API-Key": config.api_key},
        open_timeout=config.request_timeout_seconds,
        close_timeout=config.request_timeout_seconds,
    ) as websocket:
        websocket.send(packet.model_dump_json())
        response = json.loads(websocket.recv())
    ws_latency_ms = (perf_counter() - ws_started) * 1000.0

    summary = SessionSummary(
        duration_seconds=session_duration_seconds,
        focused_seconds=max(0, session_duration_seconds - 2),
        average_focus=float(response.get("focus_score", 0.0)),
        distraction_count=0,
        focus_streak_seconds=1.0,
        completed=True,
        minute_focus_scores=[float(response.get("focus_score", 0.0))],
    )

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
) -> dict[str, Any]:
    extracted = _open_video_sequence(video_path)
    return replay_session(
        config,
        raw_feature_sequence=extracted["raw_feature_sequence"],
        face_found=bool(extracted["face_found"]),
        session_duration_seconds=60,
        user_id=user_id,
    )
