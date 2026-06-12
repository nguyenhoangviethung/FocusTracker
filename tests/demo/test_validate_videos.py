from __future__ import annotations

from pathlib import Path

from demo.validate_videos import collect_videos, natural_key


def test_natural_key_orders_numbers() -> None:
    items = [Path("10.mp4"), Path("2.mp4"), Path("1.mp4")]
    ordered = sorted(items, key=natural_key)
    assert [item.name for item in ordered] == ["1.mp4", "2.mp4", "10.mp4"]


def test_collect_videos_uses_natural_sort_and_limit(monkeypatch, tmp_path) -> None:
    files = [tmp_path / name for name in ["10.mp4", "2.mp4", "1.mp4"]]
    for file in files:
        file.write_bytes(b"fake")

    monkeypatch.setattr(
        "demo.validate_videos.read_video_metadata",
        lambda path: (300, 30.0, 10.0),
    )

    manifest = collect_videos(tmp_path, limit=2)
    assert [Path(entry.source_video).name for entry in manifest.entries] == ["1.mp4", "2.mp4"]
    assert len(manifest.entries) == 2

