from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from demo.validate_videos import collect_videos
from tracking.buffer import FeatureSequenceBuffer
from utils.logger import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract feature fixtures from demo videos.")
    parser.add_argument("--manifest", type=Path, default=Path("demo/results/video-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("demo/features"))
    parser.add_argument("--limit", type=int, default=100)
    return parser


def _iter_manifest_entries(manifest_path: Path, limit: int):
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in payload.get("entries", [])[:limit]:
            yield item
        return
    generated = collect_videos(Path("demo/Data"), limit)
    for item in generated.entries:
        yield item.to_dict()


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        from tracking.detector import FaceFeatureDetector
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "mediapipe is required for feature extraction. Install requirements/dev.txt "
            "before running demo.extract_features."
        ) from exc

    detector = FaceFeatureDetector(draw_landmarks=False)
    try:
        for item in _iter_manifest_entries(args.manifest, args.limit):
            source_video = Path(item["source_video"])
            capture = cv2.VideoCapture(str(source_video))
            if not capture.isOpened():
                print(f"skip={source_video} reason=unreadable")
                continue

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
                print(f"skip={source_video} reason=insufficient_frames")
                continue

            client_id = f"demo-client-{int(item['index']):03d}"
            fixture = {
                "source_video": str(source_video),
                "client_id": client_id,
                "sequence_number": 1,
                "captured_at": item.get("created_at") or "",
                "face_found": face_found,
                "frame_count": frame_count,
                "fps": item.get("fps", 0.0),
                "raw_feature_sequence": sequence.tolist(),
            }
            out_path = args.output / f"client-{int(item['index']):03d}.jsonl"
            out_path.write_text(json.dumps(fixture, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote={out_path}")
    finally:
        detector.close()


if __name__ == "__main__":
    main()
