from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
from pathlib import Path
from time import perf_counter

from demo.metrics import build_summary, write_summary_bundle
from demo.schemas import ClientResult
from demo.tui import ConsoleTUI
from demo.validate_videos import collect_videos
from demo.virtual_client import VirtualClientConfig, replay_video_session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live demo video clients against Cloud Run.")
    parser.add_argument("--api-url", default=os.getenv("FOCUSFLOW_CLOUD_API_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("FOCUSFLOW_CLOUD_API_KEY", ""))
    parser.add_argument("--input", type=Path, default=Path("demo/Data"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("demo/results"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.api_url or not args.api_key:
        raise SystemExit("Missing --api-url / --api-key or environment values")

    manifest = collect_videos(args.input, args.limit)
    tui = ConsoleTUI(prefix="video-runner")
    results: list[ClientResult] = []
    started_all = perf_counter()

    def worker(entry) -> ClientResult:
        config = VirtualClientConfig(
            api_url=args.api_url,
            api_key=args.api_key,
            device_id=f"demo-client-{entry.index:03d}",
        )
        try:
            outcome = replay_video_session(config, Path(entry.source_video))
            return ClientResult(
                device_id=config.device_id,
                session_id=str(outcome["session_id"]),
                status="ok",
                ws_latency_ms=float(outcome["ws_latency_ms"]),
                complete_latency_ms=float(outcome["complete_latency_ms"]),
                state=str(outcome["response"].get("state", "")),
                focus_score=float(outcome["response"].get("focus_score", 0.0)),
            )
        except SystemExit as exc:
            return ClientResult(
                device_id=config.device_id,
                session_id="",
                status="err",
                error=f"SystemExit: {exc}",
            )
        except Exception as exc:
            return ClientResult(
                device_id=config.device_id,
                session_id="",
                status="err",
                error=f"{type(exc).__name__}: {exc}",
            )

    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        for index, result in enumerate(executor.map(worker, manifest.entries), start=1):
            results.append(result)
            tui.progress(
                f"\rprocessed={index}/{len(manifest.entries)} "
                f"ok={sum(1 for r in results if r.status == 'ok')} "
                f"err={sum(1 for r in results if r.status != 'ok')}"
            )

    tui.newline()
    summary = build_summary(
        api_url=args.api_url,
        profile="video-live",
        target_clients=len(manifest.entries),
        results=results,
        wall_seconds=perf_counter() - started_all,
    )
    write_summary_bundle(args.output, summary, results)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
