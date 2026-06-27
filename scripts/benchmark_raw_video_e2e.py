from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, median
import sys
import time
from uuid import uuid4

import cv2
import httpx
import numpy as np
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.contracts import SessionCreate, SessionSummary, TelemetryPacket
from tracking.buffer import DEPTH_ROBUST_V2_FRAME_FEATURE_DIM, FeatureSequenceBuffer, SEQUENCE_LENGTH
from tracking.detector import FaceFeatureDetector
from tracking.inference import ProductInferencer


def percentile(values: list[float], value: float) -> float | None:
    return float(np.percentile(np.asarray(values, dtype=np.float64), value)) if values else None


def summarize(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean_ms": round(mean(values), 3) if values else None,
        "median_ms": round(median(values), 3) if values else None,
        "p95_ms": round(percentile(values, 95) or 0.0, 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure raw-video FocusFlow latency without hiding MediaPipe cost.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--windows", type=int, default=20)
    parser.add_argument("--stride", type=int, default=30, help="Valid frames between measured windows.")
    parser.add_argument("--cloud", action="store_true", help="Also measure session REST inference round trips.")
    parser.add_argument("--local-model", action="store_true", help="Measure model-side Triple XGB latency for evaluation only.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Video not found: {args.video}")
    if not args.cloud and not args.local_model:
        raise SystemExit("Select --cloud, --local-model, or both.")

    env = dotenv_values(".env")
    api_url = str(env.get("FOCUSFLOW_CLOUD_API_URL") or "").rstrip("/")
    api_key = str(env.get("FOCUSFLOW_CLOUD_API_KEY") or env.get("FOCUSFLOW_API_KEY") or "")
    if args.cloud and (not api_url or not api_key):
        raise SystemExit("Cloud benchmark needs FOCUSFLOW_CLOUD_API_URL and FOCUSFLOW_CLOUD_API_KEY in .env.")

    local_model = ProductInferencer() if args.local_model else None
    detector = FaceFeatureDetector(draw_landmarks=False)
    buffer = FeatureSequenceBuffer(SEQUENCE_LENGTH, DEPTH_ROBUST_V2_FRAME_FEATURE_DIM)
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise SystemExit(f"Cannot open video: {args.video}")

    client_loop_ms: list[float] = []
    extraction_ms: list[float] = []
    local_model_ms: list[float] = []
    cloud_roundtrip_ms: list[float] = []
    session_id = ""
    device_id = f"benchmark-{uuid4()}"
    http = httpx.Client(base_url=api_url, headers={"X-API-Key": api_key}, timeout=90.0) if args.cloud else None
    if http is not None:
        response = http.post("/v1/sessions", json=SessionCreate(device_id=device_id, duration_seconds=600).model_dump(mode="json"))
        response.raise_for_status()
        session_id = str(response.json()["session_id"])

    sequence_number = 0
    valid_since_window = 0
    windows = 0
    try:
        while windows < args.windows:
            ok, frame = capture.read()
            if not ok:
                break
            loop_started = time.perf_counter()
            extraction_started = time.perf_counter()
            detection = detector.extract(frame)
            extraction_ms.append((time.perf_counter() - extraction_started) * 1000.0)
            if not detection.face_found:
                continue
            enriched = buffer.append(detection.feature)
            valid_since_window += 1
            if enriched is None or valid_since_window < args.stride:
                continue
            valid_since_window = 0
            windows += 1
            client_loop_ms.append((time.perf_counter() - loop_started) * 1000.0)
            if local_model is not None:
                started = time.perf_counter()
                local_model.predict(enriched)
                local_model_ms.append((time.perf_counter() - started) * 1000.0)
            if http is not None:
                sequence_number += 1
                packet = TelemetryPacket(
                    session_id=session_id,
                    device_id=device_id,
                    sequence_number=sequence_number,
                    raw_feature_sequence=buffer.raw_sequence().tolist(),
                    face_found=True,
                    configuration={"feature_schema": "depth_robust_v2", "temporal_enrichment": "velocity_std"},
                )
                started = time.perf_counter()
                response = http.post("/v1/inference", json=packet.model_dump(mode="json"))
                response.raise_for_status()
                cloud_roundtrip_ms.append((time.perf_counter() - started) * 1000.0)
    finally:
        capture.release()
        detector.close()
        if http is not None and session_id:
            http.post(
                f"/v1/sessions/{session_id}/complete",
                json=SessionSummary(duration_seconds=1, focused_seconds=0, average_focus=0.0, distraction_count=0, focus_streak_seconds=0.0, completed=False).model_dump(mode="json"),
            )
            http.close()

    report = {
        "video": str(args.video),
        "feature_schema": "depth_robust_v2",
        "raw_shape": [SEQUENCE_LENGTH, DEPTH_ROBUST_V2_FRAME_FEATURE_DIM],
        "enriched_shape": [SEQUENCE_LENGTH, DEPTH_ROBUST_V2_FRAME_FEATURE_DIM * 3],
        "windows_completed": windows,
        "extraction": summarize(extraction_ms),
        "client_loop": summarize(client_loop_ms),
        "local_model": summarize(local_model_ms),
        "cloud_roundtrip": summarize(cloud_roundtrip_ms),
        "generated_at_epoch_seconds": time.time(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
