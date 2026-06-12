from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from demo.schemas import BenchmarkSummary, ClientResult, utc_now_iso


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_latencies(values: Iterable[float]) -> dict[str, float | None]:
    latencies = list(values)
    if not latencies:
        return {"mean": None, "p50": None, "p95": None, "max": None}
    return {
        "mean": round(mean(latencies), 2),
        "p50": round(median(latencies), 2),
        "p95": round(_percentile(latencies, 0.95) or 0.0, 2),
        "max": round(max(latencies), 2),
    }


def build_summary(
    *,
    api_url: str,
    profile: str,
    target_clients: int,
    results: list[ClientResult],
    wall_seconds: float,
) -> BenchmarkSummary:
    ok = sum(1 for result in results if result.status == "ok")
    err = sum(1 for result in results if result.status != "ok")
    states: dict[str, int] = {}
    errors: dict[str, int] = {}
    ws_latencies = []
    completion_latencies = []
    for result in results:
        if result.status == "ok":
            if result.state:
                states[result.state] = states.get(result.state, 0) + 1
            if result.ws_latency_ms is not None:
                ws_latencies.append(float(result.ws_latency_ms))
            if result.complete_latency_ms is not None:
                completion_latencies.append(float(result.complete_latency_ms))
        elif result.error:
            errors[result.error] = errors.get(result.error, 0) + 1

    return BenchmarkSummary(
        generated_at=utc_now_iso(),
        api_url=api_url,
        profile=profile,
        target_clients=target_clients,
        ok=ok,
        err=err,
        wall_seconds=round(wall_seconds, 3),
        websocket_latency_ms=summarize_latencies(ws_latencies),
        completion_latency_ms=summarize_latencies(completion_latencies),
        states=states,
        errors=sorted(errors.items(), key=lambda item: (-item[1], item[0]))[:10],
    )


def write_summary_bundle(output_dir: Path, summary: BenchmarkSummary, results: list[ClientResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = summary.generated_at.replace(":", "").replace("-", "").replace(".", "")
    json_path = output_dir / f"run-{stamp}.json"
    csv_path = output_dir / f"run-{stamp}.csv"
    txt_path = output_dir / f"run-{stamp}-summary.txt"

    json_path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(results[0].to_dict().keys()) if results else ["status"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result.to_dict())

    txt_path.write_text(
        "\n".join(
            [
                "FocusFlow Scale Benchmark",
                "-------------------------",
                f"Generated at UTC:      {summary.generated_at}",
                f"API URL:               {summary.api_url}",
                f"Profile:               {summary.profile}",
                f"Target clients:        {summary.target_clients}",
                f"Ok / Err:              {summary.ok} / {summary.err}",
                f"Wall seconds:          {summary.wall_seconds}",
                f"WebSocket latency:     {summary.websocket_latency_ms}",
                f"Completion latency:    {summary.completion_latency_ms}",
                f"States:                {summary.states}",
                f"Top errors:            {summary.errors}",
                f"JSON report:           {json_path}",
                f"CSV report:            {csv_path}",
            ]
        ),
        encoding="utf-8",
    )


def render_live_status(
    *,
    stage_name: str,
    elapsed_seconds: float,
    stage_duration: int,
    connected: int,
    success: int,
    failed: int,
    p95_ms: float | None,
    active_clients: int,
) -> str:
    width = 50
    pct = int((connected / active_clients) * width) if active_clients else 0
    bar = "#" * max(0, min(width, pct))
    p95_text = f"{p95_ms:.2f} ms" if p95_ms is not None else "n/a"
    return (
        f"\r[{stage_name}] {elapsed_seconds:6.1f}/{stage_duration:3d}s "
        f"clients {connected}/{active_clients} "
        f"ok={success} err={failed} p95={p95_text} [{bar:<50}]"
    )

