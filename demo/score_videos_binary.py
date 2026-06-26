from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import cv2
import numpy as np
import onnxruntime as ort
import xgboost as xgb

from demo.validate_videos import natural_key, read_video_metadata
from tracking.buffer import FeatureSequenceBuffer
from tracking.detector import FaceFeatureDetector
from utils.logger import setup_logging


DEFAULT_WEIGHTS = {"gru": 0.3, "tcn": 0.3, "xgboost": 0.4}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score demo videos with the legacy binary late-fusion model.")
    parser.add_argument("--input", type=Path, default=Path("demo/Data"))
    parser.add_argument("--output", type=Path, default=Path("demo/results/video-scorecard-binary.json"))
    parser.add_argument("--manifest-output", type=Path, default=Path("demo/results/video-manifest-binary-focus80.json"))
    parser.add_argument("--target-total", type=int, default=100)
    parser.add_argument("--target-focus-ratio", type=float, default=0.80)
    parser.add_argument("--threshold", type=float, default=0.54)
    parser.add_argument("--max-windows-per-video", type=int, default=6)
    parser.add_argument("--window-stride-valid-frames", type=int, default=30)
    parser.add_argument("--camera-distance-scale", type=float, default=0.18)
    parser.add_argument("--gru-model", type=Path, default=Path("models/late_fusion/engagement_gru.onnx"))
    parser.add_argument("--tcn-model", type=Path, default=Path("models/late_fusion/engagement_tcn.onnx"))
    parser.add_argument("--xgb-model", type=Path, default=Path("models/late_fusion/engagement_xgb.json"))
    parser.add_argument("--xgb-preprocessor", type=Path, default=Path("models/late_fusion/engagement_xgb.preprocess.npz"))
    return parser


class BinaryLateFusionInferencer:
    def __init__(
        self,
        *,
        gru_model: Path,
        tcn_model: Path,
        xgb_model: Path,
        xgb_preprocessor: Path,
        weights: dict[str, float] | None = None,
        threshold: float = 0.54,
    ) -> None:
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.threshold = float(threshold)
        self.gru = ort.InferenceSession(str(gru_model), providers=["CPUExecutionProvider"])
        self.tcn = ort.InferenceSession(str(tcn_model), providers=["CPUExecutionProvider"])
        self.gru_input = self.gru.get_inputs()[0].name
        self.tcn_input = self.tcn.get_inputs()[0].name

        self.xgb = xgb.Booster()
        self.xgb.load_model(str(xgb_model))
        prep = np.load(xgb_preprocessor, allow_pickle=False)
        self.xgb_mean = prep["mean"]
        self.xgb_scale = prep["scale"]

    @staticmethod
    def _onnx_probability(session: ort.InferenceSession, input_name: str, enriched: np.ndarray) -> float:
        batch = np.asarray(enriched, dtype=np.float32)[None, :, :]
        output = session.run(None, {input_name: batch})[0]
        return float(np.asarray(output, dtype=np.float32).reshape(-1)[0])

    def _xgb_probability(self, enriched: np.ndarray) -> float:
        raise RuntimeError(
            "The binary GRU/TCN/XGBoost scorer is archived and cannot consume "
            "the production depth_robust_v2 feature schema. Use demo/score_videos.py "
            "for the calibrated DeepForest product model."
        )
        if features.shape[1] != self.xgb_mean.shape[0]:
            raise ValueError(f"Expected {self.xgb_mean.shape[0]} XGB features, got {features.shape[1]}")
        scaled = (features - self.xgb_mean) / self.xgb_scale
        pred = self.xgb.predict(xgb.DMatrix(scaled))
        return float(np.asarray(pred, dtype=np.float32).reshape(-1)[0])

    def predict(self, enriched: np.ndarray) -> dict:
        enriched = np.asarray(enriched, dtype=np.float32)
        if enriched.shape != (30, 90):
            raise ValueError(f"Expected enriched shape (30, 90), got {enriched.shape}")

        gru_prob = self._onnx_probability(self.gru, self.gru_input, enriched)
        tcn_prob = self._onnx_probability(self.tcn, self.tcn_input, enriched)
        xgb_prob = self._xgb_probability(enriched)
        probability = (
            self.weights["gru"] * gru_prob
            + self.weights["tcn"] * tcn_prob
            + self.weights["xgboost"] * xgb_prob
        )
        state = "FOCUS" if probability >= self.threshold else "NON_FOCUS"
        return {
            "probability": float(probability),
            "state": state,
            "components": {
                "gru": gru_prob,
                "tcn": tcn_prob,
                "xgboost": xgb_prob,
            },
        }


def _is_valid_feature(feature: np.ndarray) -> bool:
    feature = np.asarray(feature, dtype=np.float32).reshape(-1)
    return feature.shape == (30,) and np.isfinite(feature).all() and not np.allclose(feature, 0.0)


def _score_video(
    video_path: Path,
    detector: FaceFeatureDetector,
    inferencer: BinaryLateFusionInferencer,
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

    buffer = FeatureSequenceBuffer(sequence_length=30, frame_feature_dim=30)
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
            windows.append(result)
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

    probabilities = [window["probability"] for window in windows]
    focus_windows = sum(1 for window in windows if window["state"] == "FOCUS")
    focus_ratio = focus_windows / len(windows)
    video_state = "FOCUS" if focus_ratio >= 0.5 else "NON_FOCUS"
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
            "focus_windows": focus_windows,
            "non_focus_windows": len(windows) - focus_windows,
            "focus_ratio": focus_ratio,
            "mean_probability": float(mean(probabilities)),
            "min_probability": float(min(probabilities)),
            "max_probability": float(max(probabilities)),
            "video_state": video_state,
            "window_predictions": windows,
        },
        None,
    )


def _write_balanced_manifest(
    scorecard: list[dict],
    skipped: list[dict],
    args: argparse.Namespace,
) -> None:
    target_focus = int(round(args.target_total * args.target_focus_ratio))
    target_non_focus = args.target_total - target_focus
    focus = [item for item in scorecard if item["video_state"] == "FOCUS"]
    non_focus = [item for item in scorecard if item["video_state"] != "FOCUS"]
    focus_sorted = sorted(
        focus,
        key=lambda item: (item["focus_ratio"], item["mean_probability"], item["windows"]),
        reverse=True,
    )
    non_focus_sorted = sorted(
        non_focus,
        key=lambda item: (item["focus_ratio"], item["mean_probability"], item["windows"]),
    )
    selected_focus = focus_sorted[:target_focus]
    selected_non_focus = non_focus_sorted[:target_non_focus]
    if len(selected_focus) < target_focus:
        print(f"warning: not enough binary focus videos: {len(selected_focus)} < {target_focus}")
    if len(selected_non_focus) < target_non_focus:
        print(f"warning: not enough binary non-focus videos: {len(selected_non_focus)} < {target_non_focus}")

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
                "target_group": "focus" if item["video_state"] == "FOCUS" else "non_focus",
                "measured_state": item["video_state"],
                "mean_probability": item["mean_probability"],
                "focus_ratio": item["focus_ratio"],
                "windows": item["windows"],
                "valid_frames": item["valid_frames"],
            }
        )

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input),
        "selection_method": "legacy_binary_late_fusion_score_non_overlapping_30_valid_frame_windows",
        "model_version": "late_fusion_binary_gru_tcn_xgb",
        "threshold": args.threshold,
        "weights": DEFAULT_WEIGHTS,
        "scorecard": str(args.output),
        "target_total": args.target_total,
        "target_focus": target_focus,
        "target_non_focus": target_non_focus,
        "actual_focus": len(selected_focus),
        "actual_non_focus": len(selected_non_focus),
        "focus_ratio": len(selected_focus) / max(1, len(entries)),
        "entries": entries,
        "skipped": skipped,
    }
    args.manifest_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    raise SystemExit(
        "This is an archived binary-model experiment. It is intentionally disabled "
        "because production now uses the distinct 168D DeepForest pipeline."
    )
    setup_logging()
    args = build_parser().parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)

    videos = sorted(args.input.glob("*.mp4"), key=natural_key)
    detector = FaceFeatureDetector(
        draw_landmarks=False,
        camera_distance_scale=args.camera_distance_scale,
    )
    inferencer = BinaryLateFusionInferencer(
        gru_model=args.gru_model,
        tcn_model=args.tcn_model,
        xgb_model=args.xgb_model,
        xgb_preprocessor=args.xgb_preprocessor,
        threshold=args.threshold,
    )

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
                    f"{scored['video_state']} mean={scored['mean_probability']:.3f} "
                    f"focus={scored['focus_windows']}/{scored['windows']}",
                    flush=True,
                )
            elif skipped_item is not None:
                skipped.append(skipped_item)
                print(f"[{index:03d}/{len(videos):03d}] skip {video_path.name}", flush=True)
    finally:
        detector.close()

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input),
        "model_version": "late_fusion_binary_gru_tcn_xgb",
        "threshold": args.threshold,
        "weights": DEFAULT_WEIGHTS,
        "scored_count": len(scorecard),
        "focus_count": sum(1 for item in scorecard if item["video_state"] == "FOCUS"),
        "non_focus_count": sum(1 for item in scorecard if item["video_state"] != "FOCUS"),
        "skipped": skipped,
        "scorecard": sorted(scorecard, key=lambda item: natural_key(Path(item["source_video"]))),
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_balanced_manifest(scorecard, skipped, args)
    print(f"scorecard={args.output}")
    print(f"manifest={args.manifest_output}")


if __name__ == "__main__":
    main()
