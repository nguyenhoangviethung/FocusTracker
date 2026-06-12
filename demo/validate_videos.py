from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import cv2

from demo.schemas import VideoManifest, VideoManifestEntry, utc_now_iso


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


def collect_videos(input_dir: Path, limit: int) -> VideoManifest:
    candidates = sorted(input_dir.glob("*.mp4"), key=natural_key)
    entries: list[VideoManifestEntry] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(entries) >= limit:
            break
        try:
            frame_count, fps, duration = read_video_metadata(candidate)
        except Exception as exc:
            skipped.append({"source_video": str(candidate), "reason": str(exc)})
            continue
        entries.append(
            VideoManifestEntry(
                index=len(entries) + 1,
                source_video=str(candidate),
                duration_seconds=duration,
                frame_count=frame_count,
                fps=fps,
            )
        )
    return VideoManifest(
        created_at=utc_now_iso(),
        input_dir=str(input_dir),
        limit=limit,
        entries=entries,
        skipped=skipped,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and select demo videos.")
    parser.add_argument("--input", type=Path, default=Path("demo/Data"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("demo/results/video-manifest.json"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = collect_videos(args.input, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"selected={len(manifest.entries)} skipped={len(manifest.skipped)} output={args.output}")


if __name__ == "__main__":
    main()

