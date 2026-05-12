from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from tracking.inference import ONNXEngagementInferencer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone webcam + ONNX tracking test")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models") / "engagement_gru.onnx",
        help="Path to ONNX model",
    )
    parser.add_argument("--threshold", type=float, default=0.55, help="Engagement threshold")
    parser.add_argument("--smoothing", type=int, default=5, help="Smoothing window (3-5)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    detector = FaceFeatureDetector(draw_landmarks=True)
    buffer = FeatureSequenceBuffer(sequence_length=60, frame_feature_dim=30)
    inferencer = ONNXEngagementInferencer(
        model_file=args.model,
        threshold=args.threshold,
        smoothing_window=args.smoothing,
    )

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {args.camera}")

    print("Tracker started. Press 'q' to quit.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            detection = detector.extract(frame)
            enriched = buffer.append(detection.feature)

            state = "NO_FACE" if not detection.face_found else "WARMING_UP"
            score = 0.0
            if enriched is not None:
                prediction = inferencer.predict(enriched)
                state = str(prediction["state"])
                score = float(prediction["focus_score"])

            color = (70, 200, 80) if state == "ENGAGED" else (50, 90, 220)
            if state in {"NO_FACE", "WARMING_UP"}:
                color = (0, 185, 245)

            output = detection.frame
            cv2.putText(output, f"State: {state}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)
            cv2.putText(
                output,
                f"Focus score: {score * 100:.1f}%",
                (18, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (240, 245, 255),
                2,
            )
            cv2.putText(
                output,
                "Press q to quit",
                (18, output.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (180, 195, 220),
                1,
            )

            cv2.imshow("FocusFlow Tracker Test", output)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        cap.release()
        detector.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
