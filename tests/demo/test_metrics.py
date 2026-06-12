from __future__ import annotations

from demo.metrics import summarize_latencies, build_summary
from demo.schemas import ClientResult


def test_summarize_latencies() -> None:
    stats = summarize_latencies([10.0, 20.0, 30.0, 40.0])
    assert stats["mean"] == 25.0
    assert stats["p50"] == 25.0
    assert stats["p95"] is not None
    assert stats["max"] == 40.0


def test_build_summary_counts_results() -> None:
    results = [
        ClientResult(device_id="a", session_id="1", status="ok", ws_latency_ms=10.0, complete_latency_ms=12.0, state="FOCUSED"),
        ClientResult(device_id="b", session_id="2", status="err", error="boom"),
    ]
    summary = build_summary(
        api_url="https://example.com",
        profile="video-live",
        target_clients=2,
        results=results,
        wall_seconds=1.5,
    )
    assert summary.ok == 1
    assert summary.err == 1
    assert summary.states["FOCUSED"] == 1

