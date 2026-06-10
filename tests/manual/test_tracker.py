from __future__ import annotations

import argparse

import cv2
import numpy as np

from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from tracking.inference import ONNXEngagementInferencer
from utils.logger import setup_logging, get_logger


logger = get_logger("test_tracker")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone FocusFlow webcam tracker")
    parser.add_argument("--camera", type=int, default=0, help="Camera index to open")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Path to ONNX model file. Defaults to models/late_fusion/engagement_gru.onnx",
    )
    parser.add_argument("--show-landmarks", action="store_true", help="Draw FaceMesh landmarks on frame")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = until q)")
    parser.add_argument("--threshold", type=float, default=None, help="Override engagement threshold")
    parser.add_argument("--smoothing-window", type=int, default=None, help="Override probability smoothing window")
    return parser


def run_cli() -> None:
    setup_logging()
    args = build_parser().parse_args()
    logger.info("Starting tracker CLI (camera=%s)", args.camera)
    inferencer = ONNXEngagementInferencer(
        model_file=args.model,
        threshold=args.threshold,
        smoothing_window=args.smoothing_window,
    )
    spec = inferencer.spec
    detector = FaceFeatureDetector(draw_landmarks=args.show_landmarks, expected_feature_dim=spec.raw_feature_dim)
    buffer = FeatureSequenceBuffer(sequence_length=spec.sequence_length, frame_feature_dim=spec.raw_feature_dim)

    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        logger.error("Cannot open camera index %s", args.camera)
        raise RuntimeError(f"Cannot open camera index {args.camera}")

    frame_count = 0
    try:
        while capture.isOpened():
            success, frame = capture.read()
            if not success:
                continue

            detection = detector.extract(frame)
            enriched_chunk = buffer.append(detection.feature)
            state = "NO_FACE" if not detection.face_found else "WARMING_UP"
            focus_score = 0.0

            if enriched_chunk is not None:
                prediction = inferencer.predict(enriched_chunk)
                state = str(prediction["state"])
                focus_score = float(prediction["focus_score"])

            color = (0, 255, 0) if state == "ENGAGED" else (0, 0, 255)
            display_frame = detection.frame.copy() if args.show_landmarks else frame
            cv2.putText(display_frame, f"Focus: {focus_score:.2f}", (24, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
            cv2.putText(display_frame, f"State: {state}", (24, 88), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
            cv2.putText(
                display_frame,
                f"Spec: {spec.sequence_length}x{spec.raw_feature_dim} -> {spec.expected_input_shape()[0]}x{spec.expected_input_shape()[1]}",
                (24, 132),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (235, 235, 235),
                2,
            )

            cv2.imshow("FocusFlow AI - Tracker CLI", display_frame)
            frame_count += 1
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if args.max_frames > 0 and frame_count >= args.max_frames:
                break
    finally:
        capture.release()
        detector.close()
        cv2.destroyAllWindows()
        logger.info("Tracker CLI closed (frames=%s)", frame_count)


if __name__ == "__main__":
    run_cli()
