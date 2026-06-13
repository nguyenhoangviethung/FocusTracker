from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class VideoManifestEntry:
    index: int
    source_video: str
    duration_seconds: float
    frame_count: int
    fps: float
    selected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VideoManifest:
    created_at: str
    input_dir: str
    limit: int
    entries: list[VideoManifestEntry] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "input_dir": self.input_dir,
            "limit": self.limit,
            "entries": [entry.to_dict() for entry in self.entries],
            "skipped": list(self.skipped),
        }


@dataclass(slots=True)
class FeatureFixture:
    source_video: str
    client_id: str
    sequence_number: int
    captured_at: str
    face_found: bool
    raw_feature_sequence: list[list[float]]
    frame_count: int
    fps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UserManifestEntry:
    index: int
    user_id: str
    email: str
    display_name: str
    auth_provider: str
    google_subject: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UserManifest:
    created_at: str
    collection: str
    limit: int
    entries: list[UserManifestEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "collection": self.collection,
            "limit": self.limit,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(slots=True)
class ClientResult:
    device_id: str
    session_id: str
    status: str
    ws_latency_ms: float | None = None
    complete_latency_ms: float | None = None
    state: str | None = None
    focus_score: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BenchmarkStage:
    clients: int
    duration_seconds: int
    name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BenchmarkSummary:
    generated_at: str
    api_url: str
    profile: str
    target_clients: int
    ok: int
    err: int
    wall_seconds: float
    websocket_latency_ms: dict[str, float | None]
    completion_latency_ms: dict[str, float | None]
    states: dict[str, int]
    errors: list[tuple[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
