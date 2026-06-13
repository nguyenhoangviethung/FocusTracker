from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import traceback
from pathlib import Path
from time import perf_counter

from demo.metrics import build_summary, write_summary_bundle
from demo.schemas import BenchmarkStage, ClientResult
from demo.tui import ConsoleTUI
from demo.virtual_client import VirtualClientConfig, load_fixture, replay_session


DEFAULT_STAGES = [
    BenchmarkStage(clients=1, duration_seconds=30, name="warm-up"),
    BenchmarkStage(clients=5, duration_seconds=30, name="baseline"),
    BenchmarkStage(clients=10, duration_seconds=45, name="small"),
    BenchmarkStage(clients=25, duration_seconds=60, name="medium"),
    BenchmarkStage(clients=50, duration_seconds=60, name="high"),
    BenchmarkStage(clients=100, duration_seconds=90, name="peak"),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the FocusFlow scale demo replay.")
    parser.add_argument("--api-url", default=os.getenv("FOCUSFLOW_CLOUD_API_URL", ""))
    parser.add_argument("--api-key", default=os.getenv("FOCUSFLOW_CLOUD_API_KEY", ""))
    parser.add_argument("--features", type=Path, default=Path("demo/features"))
    parser.add_argument("--manifest", type=Path, default=Path("demo/results/video-manifest.json"))
    parser.add_argument("--users-manifest", type=Path, default=Path("demo/results/user-manifest.json"))
    parser.add_argument("--stages", default="")
    parser.add_argument("--stream-interval-seconds", type=float, default=0.0)
    parser.add_argument("--playback-speed", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("demo/results"))
    return parser


def parse_stages(raw: str) -> list[BenchmarkStage]:
    if not raw.strip():
        return list(DEFAULT_STAGES)
    stages: list[BenchmarkStage] = []
    for chunk in raw.split(","):
        clients_str, duration_str = chunk.split(":", 1)
        stages.append(
            BenchmarkStage(
                clients=int(clients_str),
                duration_seconds=int(duration_str),
                name=f"{clients_str}x{duration_str}",
            )
        )
    return stages


def load_fixtures(features_dir: Path) -> list[dict]:
    fixtures = []
    for path in sorted(features_dir.glob("*.jsonl")):
        fixtures.append(load_fixture(path))
    return fixtures


def load_manifest_entries(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]


def load_user_entries(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]


def main() -> None:
    args = build_parser().parse_args()
    if not args.api_url or not args.api_key:
        raise SystemExit("Missing --api-url / --api-key or environment values")

    stages = parse_stages(args.stages)
    tui = ConsoleTUI(prefix="scale-runner")
    results: list[ClientResult] = []
    started_all = perf_counter()
    manifest_entries = load_manifest_entries(args.manifest)
    user_entries = load_user_entries(args.users_manifest)
    stream_interval_seconds = max(0.0, float(args.stream_interval_seconds))
    playback_speed = max(0.01, float(args.playback_speed))
    verbose = os.getenv("DEMO_VERBOSE", "").strip().lower() in {"1", "true", "yes", "on"}
    fixtures = load_fixtures(args.features) if stream_interval_seconds <= 0 else []
    if not manifest_entries and not fixtures:
        raise SystemExit(
            f"No video manifest entries found in {args.manifest} and no feature fixtures found in {args.features}"
        )

    for stage in stages:
        stage_start = perf_counter()
        stage_results: list[ClientResult] = []

        def worker(index: int) -> ClientResult:
            manifest_entry = manifest_entries[index % len(manifest_entries)] if manifest_entries else None
            fixture = fixtures[index % len(fixtures)] if fixtures else None
            user_entry = user_entries[index % len(user_entries)] if user_entries else None
            source_video = ""
            if fixture is None and manifest_entry is not None:
                source_video = str(manifest_entry.get("source_video") or "")
            elif fixture is not None:
                source_video = str(fixture.get("source_video") or "")
            config = VirtualClientConfig(
                api_url=args.api_url,
                api_key=args.api_key,
                device_id=f"demo-client-{index + 1:03d}",
            )
            def log_step(message: str) -> None:
                if verbose:
                    tui.write(f"[{config.device_id}] {message}")

            try:
                if stream_interval_seconds > 0 and source_video:
                    from demo.virtual_client import replay_video_session

                    outcome = replay_video_session(
                        config,
                        Path(source_video),
                        user_id=str(user_entry.get("user_id") or "") if user_entry else None,
                        packet_interval_seconds=stream_interval_seconds,
                        playback_speed=playback_speed,
                        log=log_step,
                    )
                elif fixture is not None:
                    outcome = replay_session(
                        config,
                        raw_feature_sequence=fixture["raw_feature_sequence"],
                        face_found=bool(fixture.get("face_found", True)),
                        session_duration_seconds=stage.duration_seconds,
                        user_id=str(user_entry.get("user_id") or "") if user_entry else None,
                        log=log_step,
                    )
                elif source_video:
                    from demo.virtual_client import replay_video_session

                    outcome = replay_video_session(
                        config,
                        Path(source_video),
                        user_id=str(user_entry.get("user_id") or "") if user_entry else None,
                        packet_interval_seconds=stream_interval_seconds or 1.0,
                        playback_speed=playback_speed,
                        log=log_step,
                    )
                else:
                    raise RuntimeError("No fixture or source video available for replay")
                return ClientResult(
                    device_id=config.device_id,
                    session_id=str(outcome["session_id"]),
                    status="ok",
                    ws_latency_ms=float(outcome["ws_latency_ms"]),
                    complete_latency_ms=float(outcome["complete_latency_ms"]),
                    state=str(outcome["response"].get("state", "")),
                    focus_score=float(outcome["response"].get("focus_score", 0.0)),
                )
            except Exception as exc:
                tb = traceback.format_exc()
                if verbose:
                    tui.write(f"[{config.device_id}] error_stage={getattr(exc, 'stage', 'unknown')} error={exc}")
                    tui.write(tb.rstrip())
                return ClientResult(
                    device_id=config.device_id,
                    session_id=str(getattr(exc, "session_id", "") or ""),
                    status="err",
                    error_stage=str(getattr(exc, "stage", "unknown")),
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=tb,
                )
            except SystemExit as exc:
                tb = traceback.format_exc()
                if verbose:
                    tui.write(f"[{config.device_id}] error_stage=system_exit error={exc}")
                    tui.write(tb.rstrip())
                return ClientResult(
                    device_id=config.device_id,
                    session_id="",
                    status="err",
                    error_stage="system_exit",
                    error=f"SystemExit: {exc}",
                    traceback=tb,
                )

        with cf.ThreadPoolExecutor(max_workers=stage.clients) as executor:
            for result in executor.map(worker, range(stage.clients)):
                stage_results.append(result)
                results.append(result)
                tui.progress(
                    f"\rstage={stage.name} clients={len(stage_results)}/{stage.clients} "
                    f"ok={sum(1 for r in stage_results if r.status == 'ok')} "
                    f"err={sum(1 for r in stage_results if r.status != 'ok')}"
                )

        tui.newline()
        elapsed = perf_counter() - stage_start
        tui.write(
            f"stage={stage.name} finished in {elapsed:.1f}s "
            f"ok={sum(1 for r in stage_results if r.status == 'ok')} "
            f"err={sum(1 for r in stage_results if r.status != 'ok')}"
        )

    summary = build_summary(
        api_url=args.api_url,
        profile="scale-replay",
        target_clients=sum(stage.clients for stage in stages),
        results=results,
        wall_seconds=perf_counter() - started_all,
    )
    write_summary_bundle(args.output, summary, results)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
