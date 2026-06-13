from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import cycle
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from demo.schemas import utc_now_iso
from tracking.buffer import FeatureSequenceBuffer, enrich_raw_sequence
from tracking.inference import ONNXEngagementInferencer


def natural_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", path.stem)
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        elif part:
            key.append(part.lower())
    key.append(path.suffix.lower())
    return key


def read_video_metadata(path: Path) -> tuple[int, float, float]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot open video: {path}")
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        duration = float(frame_count / fps) if frame_count > 0 and fps > 0 else 0.0
        return frame_count, fps, duration
    finally:
        capture.release()


def extract_raw_sequence(path: Path) -> dict[str, Any]:
    try:
        from tracking.detector import FaceFeatureDetector
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mediapipe is required for demo video selection. Install requirements/dev.txt first."
        ) from exc

    detector = FaceFeatureDetector(draw_landmarks=False)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        detector.close()
        raise RuntimeError(f"Cannot open video: {path}")

    buffer = FeatureSequenceBuffer(sequence_length=30, frame_feature_dim=30)
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
        detector.close()

    raw_sequence = buffer.raw_sequence()
    if raw_sequence is None:
        raise RuntimeError(f"Unable to build a 30-frame sequence from {path}")

    frame_total, fps, duration = read_video_metadata(path)
    return {
        "face_found": face_found,
        "frame_count": frame_count,
        "frame_total": frame_total,
        "fps": fps,
        "duration_seconds": duration,
        "raw_sequence": raw_sequence,
    }


def score_video(inferencer: ONNXEngagementInferencer, path: Path) -> dict[str, Any]:
    extracted = extract_raw_sequence(path)
    enriched = enrich_raw_sequence(extracted["raw_sequence"])
    prediction = inferencer.predict(enriched)
    return {
        "source_video": str(path),
        "face_found": bool(extracted["face_found"]),
        "frame_count": int(extracted["frame_count"]),
        "frame_total": int(extracted["frame_total"]),
        "fps": float(extracted["fps"]),
        "duration_seconds": float(extracted["duration_seconds"]),
        "state": str(prediction["state"]),
        "focus_score": float(prediction["focus_score"]),
        "model_version": str(prediction.get("model_version", "")),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select 100 demo videos with a focus/distracted mix."
    )
    parser.add_argument("--input", type=Path, default=Path("demo/Data"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("demo/results/focus-demo-manifest.json"))
    parser.add_argument(
        "--focus-state",
        default="ENGAGED",
        help="State treated as focus for selection.",
    )
    parser.add_argument(
        "--distracted-ratio",
        type=float,
        default=0.2,
        help="Target fraction of selected videos that should be distracted.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    started = perf_counter()
    candidates = sorted(args.input.glob("*.mp4"), key=natural_key)
    if not candidates:
        raise SystemExit(f"No mp4 files found in {args.input}")

    inferencer = ONNXEngagementInferencer(smoothing_window=1)
    scored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    try:
        for index, video in enumerate(candidates, start=1):
            try:
                item = score_video(inferencer, video)
                item["natural_order"] = index
                scored.append(item)
                print(
                    f"scanned={index}/{len(candidates)} state={item['state']} "
                    f"score={item['focus_score']:.3f} video={video.name}"
                )
            except Exception as exc:
                skipped.append({"source_video": str(video), "reason": str(exc)})
                print(f"skip={video.name} reason={exc}")
    finally:
        inferencer.reset()

    focus_state = str(args.focus_state).upper().strip()
    focus_candidates = [item for item in scored if item["state"].upper() == focus_state]
    distracted_candidates = [item for item in scored if item["state"].upper() != focus_state]

    focus_candidates.sort(key=lambda item: (-float(item["focus_score"]), item["natural_order"]))
    distracted_candidates.sort(key=lambda item: (-float(item["focus_score"]), item["natural_order"]))

    distracted_target = int(round(args.limit * float(args.distracted_ratio)))
    distracted_target = max(0, min(args.limit, distracted_target))
    focus_target = args.limit - distracted_target

    if not focus_candidates:
        raise SystemExit(f"No videos were scored as {focus_state}; cannot build a focus-first demo set.")
    if not distracted_candidates:
        raise SystemExit("No distracted videos were found; cannot satisfy the requested 20% distracted mix.")

    selected: list[dict[str, Any]] = []
    focus_iter = cycle(focus_candidates)
    distracted_iter = cycle(distracted_candidates)

    focus_selected = 0
    distracted_selected = 0
    focus_seen: set[str] = set()
    distracted_seen: set[str] = set()

    while len(selected) < args.limit:
        if focus_selected < focus_target:
            item = next(focus_iter)
            focus_selected += 1
            source_video = str(item["source_video"])
            selection_reason = "focus" if source_video not in focus_seen else "focus-reuse"
            focus_seen.add(source_video)
            selected.append({**item, "selection_reason": selection_reason})
            if len(selected) >= args.limit:
                break
        if distracted_selected < distracted_target:
            item = next(distracted_iter)
            distracted_selected += 1
            source_video = str(item["source_video"])
            selection_reason = "distracted" if source_video not in distracted_seen else "distracted-reuse"
            distracted_seen.add(source_video)
            selected.append({**item, "selection_reason": selection_reason})

    entries: list[dict[str, Any]] = []
    for new_index, item in enumerate(selected[: args.limit], start=1):
        entries.append(
            {
                "index": new_index,
                "source_video": item["source_video"],
                "duration_seconds": item["duration_seconds"],
                "frame_count": item["frame_total"],
                "fps": item["fps"],
                "selected": True,
                "local_state": item["state"],
                "focus_score": round(float(item["focus_score"]), 6),
                "selection_reason": item.get("selection_reason", ""),
            }
        )

    payload = {
        "created_at": utc_now_iso(),
        "input_dir": str(args.input),
        "limit": args.limit,
        "selection_mode": "focus-distracted-mix",
        "focus_state": focus_state,
        "distracted_ratio": float(args.distracted_ratio),
        "focus_target": focus_target,
        "distracted_target": distracted_target,
        "scanned_count": len(scored),
        "focus_count": len(focus_candidates),
        "distracted_count": len(distracted_candidates),
        "selected_count": len(entries),
        "entries": entries,
        "skipped": skipped,
        "generated_seconds": round(perf_counter() - started, 3),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    focus_included = sum(1 for item in entries if item["local_state"].upper() == focus_state)
    distracted_included = sum(1 for item in entries if item["local_state"].upper() != focus_state)
    print(
        f"selected={len(entries)} focus={focus_included} distracted={distracted_included} "
        f"scanned={len(scored)} skipped={len(skipped)} output={args.output}"
    )


if __name__ == "__main__":
    main()
