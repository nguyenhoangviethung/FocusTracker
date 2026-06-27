from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import cv2
import numpy as np

from demo.validate_videos import natural_key, read_video_metadata
from tracking.buffer import DEPTH_ROBUST_V2_FRAME_FEATURE_DIM, FeatureSequenceBuffer, SEQUENCE_LENGTH
from tracking.detector import FRAME_FEATURE_DIM, FaceFeatureDetector
from tracking.inference import MODEL_VERSION, ProductInferencer
from utils.logger import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score demo videos with the deployed calibrated 4-class Triple XGB model."
    )
    parser.add_argument("--input", type=Path, default=Path("demo/Data"))
    parser.add_argument("--scorecard-output", type=Path, default=Path("demo/results/video-scorecard.json"))
    parser.add_argument("--manifest-output", type=Path, default=Path("demo/results/video-manifest-focus80.json"))
    parser.add_argument("--target-total", type=int, default=100)
    parser.add_argument("--target-focus-ratio", type=float, default=0.80)
    parser.add_argument("--max-windows-per-video", type=int, default=6)
    parser.add_argument("--window-stride-valid-frames", type=int, default=30)
    parser.add_argument("--camera-distance-scale", type=float, default=0.18)
    return parser


def _is_valid_feature(feature: np.ndarray) -> bool:
    feature = np.asarray(feature, dtype=np.float32).reshape(-1)
    return feature.shape == (FRAME_FEATURE_DIM,) and np.isfinite(feature).all() and not np.allclose(feature, 0.0)


def _score_video(
    video_path: Path,
    detector: FaceFeatureDetector,
    inferencer: ProductInferencer,
    *,
    max_windows_per_video: int,
    window_stride_valid_frames: int,
) -> tuple[dict | None, dict | None]:
    try:
        frame_count, fps, duration = read_video_metadata(video_path)
    except Exception as exc:
        return None, {"source_video": str(video_path), "reason": f"metadata_error: {exc}"}

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return None, {"source_video": str(video_path), "reason": "unreadable"}

    buffer = FeatureSequenceBuffer(
        sequence_length=SEQUENCE_LENGTH,
        frame_feature_dim=DEPTH_ROBUST_V2_FRAME_FEATURE_DIM,
    )
    windows: list[dict] = []
    decoded_frames = 0
    valid_frames = 0
    frames_since_window = 0
    try:
        while len(windows) < max_windows_per_video:
            ok, frame = capture.read()
            if not ok:
                break
            decoded_frames += 1

            try:
                detection = detector.extract(frame)
            except Exception:
                continue

            if not detection.face_found or not _is_valid_feature(detection.feature):
                continue

            valid_frames += 1
            enriched = buffer.append(detection.feature)
            frames_since_window += 1
            if enriched is None or frames_since_window < window_stride_valid_frames:
                continue

            result = inferencer.predict(enriched)
            windows.append(
                {
                    "state": result["state"],
                    "focus_score": float(result["focus_score"]),
                    "prediction_4class": int(result["prediction_4class"]),
                    "prediction_label": result["prediction_label"],
                    "probabilities_4class": [float(value) for value in result["probabilities_4class"]],
                }
            )
            frames_since_window = 0
    finally:
        capture.release()

    if not windows:
        return None, {
            "source_video": str(video_path),
            "reason": "no_valid_30_frame_window",
            "frame_count": frame_count,
            "decoded_frames": decoded_frames,
            "valid_frames": valid_frames,
        }

    focus_scores = [window["focus_score"] for window in windows]
    engaged_windows = sum(1 for window in windows if window["state"] == "ENGAGED")
    engaged_ratio = engaged_windows / len(windows)
    video_state = "FOCUS" if engaged_ratio >= 0.5 else "NON_FOCUS"
    return (
        {
            "source_video": str(video_path),
            "video_id": video_path.stem,
            "duration_seconds": duration,
            "frame_count": frame_count,
            "fps": fps,
            "decoded_frames": decoded_frames,
            "valid_frames": valid_frames,
            "windows": len(windows),
            "engaged_windows": engaged_windows,
            "distracted_windows": len(windows) - engaged_windows,
            "engaged_ratio": engaged_ratio,
            "mean_focus_score": float(mean(focus_scores)),
            "min_focus_score": float(min(focus_scores)),
            "max_focus_score": float(max(focus_scores)),
            "video_state": video_state,
            "window_predictions": windows,
        },
        None,
    )


def _build_balanced_manifest(
    scorecard: list[dict],
    skipped: list[dict],
    *,
    input_dir: Path,
    target_total: int,
    target_focus_ratio: float,
    output_path: Path,
) -> dict:
    target_focus = int(round(target_total * target_focus_ratio))
    target_non_focus = target_total - target_focus

    focus = [item for item in scorecard if item["video_state"] == "FOCUS"]
    non_focus = [item for item in scorecard if item["video_state"] != "FOCUS"]
    focus_sorted = sorted(
        focus,
        key=lambda item: (item["engaged_ratio"], item["mean_focus_score"], item["windows"]),
        reverse=True,
    )
    non_focus_sorted = sorted(
        non_focus,
        key=lambda item: (item["engaged_ratio"], item["mean_focus_score"], item["windows"]),
    )

    selected_focus = focus_sorted[:target_focus]
    selected_non_focus = non_focus_sorted[:target_non_focus]
    if len(selected_focus) < target_focus:
        raise SystemExit(f"not enough focus videos: {len(selected_focus)} < {target_focus}")
    if len(selected_non_focus) < target_non_focus:
        raise SystemExit(f"not enough non-focus videos: {len(selected_non_focus)} < {target_non_focus}")

    entries = []
    for index, item in enumerate(selected_focus + selected_non_focus, start=1):
        entries.append(
            {
                "index": index,
                "client_id": f"demo-client-{index:03d}",
                "video_id": item["video_id"],
                "source_video": item["source_video"],
                "duration_seconds": item["duration_seconds"],
                "frame_count": item["frame_count"],
                "fps": item["fps"],
                "selected": True,
                "target_group": "focus" if index <= target_focus else "non_focus",
                "measured_state": item["video_state"],
                "mean_focus_score": item["mean_focus_score"],
                "engaged_ratio": item["engaged_ratio"],
                "windows": item["windows"],
                "valid_frames": item["valid_frames"],
            }
        )

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir),
        "selection_method": "local_model_score_non_overlapping_30_valid_frame_windows",
        "model_version": MODEL_VERSION,
        "scorecard": str(output_path),
        "target_total": target_total,
        "target_focus": target_focus,
        "target_non_focus": target_non_focus,
        "actual_focus": len(selected_focus),
        "actual_non_focus": len(selected_non_focus),
        "focus_ratio": len(selected_focus) / target_total,
        "entries": entries,
        "skipped": skipped,
    }


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    args.scorecard_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)

    videos = sorted(args.input.glob("*.mp4"), key=natural_key)
    detector = FaceFeatureDetector(
        draw_landmarks=False,
        camera_distance_scale=args.camera_distance_scale,
    )
    inferencer = ProductInferencer()

    scorecard: list[dict] = []
    skipped: list[dict] = []
    try:
        for index, video_path in enumerate(videos, start=1):
            scored, skipped_item = _score_video(
                video_path,
                detector,
                inferencer,
                max_windows_per_video=args.max_windows_per_video,
                window_stride_valid_frames=args.window_stride_valid_frames,
            )
            if scored is not None:
                scorecard.append(scored)
                print(
                    f"[{index:03d}/{len(videos):03d}] {video_path.name} "
                    f"{scored['video_state']} mean={scored['mean_focus_score']:.3f} "
                    f"engaged={scored['engaged_windows']}/{scored['windows']}",
                    flush=True,
                )
            elif skipped_item is not None:
                skipped.append(skipped_item)
                print(f"[{index:03d}/{len(videos):03d}] skip {video_path.name}", flush=True)
    finally:
        detector.close()

    score_payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input),
        "scored_count": len(scorecard),
        "focus_count": sum(1 for item in scorecard if item["video_state"] == "FOCUS"),
        "non_focus_count": sum(1 for item in scorecard if item["video_state"] != "FOCUS"),
        "skipped": skipped,
        "scorecard": sorted(scorecard, key=lambda item: natural_key(Path(item["source_video"]))),
    }
    args.scorecard_output.write_text(
        json.dumps(score_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = _build_balanced_manifest(
        scorecard,
        skipped,
        input_dir=args.input,
        target_total=args.target_total,
        target_focus_ratio=args.target_focus_ratio,
        output_path=args.scorecard_output,
    )
    args.manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"scorecard={args.scorecard_output}")
    print(f"manifest={args.manifest_output}")


if __name__ == "__main__":
    main()
