from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import cv2

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from demo.schemas import utc_now_iso


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


def _pick_fourcc(source: Path) -> int:
    suffix = source.suffix.lower()
    if suffix == ".avi":
        return cv2.VideoWriter_fourcc(*"XVID")
    return cv2.VideoWriter_fourcc(*"mp4v")


def extend_video(source: Path, destination: Path, factor: int) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {source}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if frame_width <= 0 or frame_height <= 0:
        capture.release()
        raise RuntimeError(f"Invalid frame size for video: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(destination), _pick_fourcc(destination), fps, (frame_width, frame_height))
    if not writer.isOpened():
        capture.release()
        raise RuntimeError(f"Cannot open writer for: {destination}")

    frame_count = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_count += 1
            for _ in range(max(1, factor)):
                writer.write(frame)
    finally:
        capture.release()
        writer.release()

    extended_frames = frame_count * max(1, factor)
    extended_duration = float(extended_frames / fps) if fps > 0 else 0.0
    return {
        "source_video": str(source),
        "output_video": str(destination),
        "source_frames": frame_count,
        "extended_frames": extended_frames,
        "fps": fps,
        "source_duration_seconds": float(frame_count / fps) if frame_count > 0 and fps > 0 else 0.0,
        "extended_duration_seconds": extended_duration,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extend demo videos by repeating frames in-place.")
    parser.add_argument("--input", type=Path, default=Path("demo/Data"))
    parser.add_argument("--output", type=Path, default=Path("demo/Data-x20"))
    parser.add_argument("--factor", type=int, default=20)
    parser.add_argument("--manifest", type=Path, default=Path("demo/results/extended-video-manifest.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    factor = max(1, int(args.factor))
    candidates = sorted(args.input.glob("*.mp4"), key=natural_key)
    if not candidates:
        raise SystemExit(f"No mp4 files found in {args.input}")

    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, source in enumerate(candidates, start=1):
        destination = args.output / source.name
        try:
            result = extend_video(source, destination, factor)
            result["index"] = index
            results.append(result)
            print(
                f"wrote={destination.name} source={result['source_duration_seconds']:.1f}s "
                f"extended={result['extended_duration_seconds']:.1f}s"
            )
        except Exception as exc:
            skipped.append({"source_video": str(source), "reason": str(exc)})
            print(f"skip={source.name} reason={exc}")

    payload = {
        "created_at": utc_now_iso(),
        "input_dir": str(args.input),
        "output_dir": str(args.output),
        "factor": factor,
        "selected_count": len(results),
        "skipped_count": len(skipped),
        "entries": results,
        "skipped": skipped,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"selected={len(results)} skipped={len(skipped)} manifest={args.manifest}")


if __name__ == "__main__":
    main()
