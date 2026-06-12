from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROTOCOL_VERSION = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionCreate(ContractModel):
    device_id: str = Field(min_length=1, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)
    duration_seconds: int = Field(ge=1, le=12 * 60 * 60)


class SessionRecord(SessionCreate):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["active", "paused", "completed", "cancelled"] = "active"
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    last_seen_at: datetime = Field(default_factory=utc_now)


class TelemetryPacket(ContractModel):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    captured_at: datetime = Field(default_factory=utc_now)
    sequence_number: int = Field(ge=0)
    raw_feature_sequence: list[list[float]]
    face_found: bool
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("raw_feature_sequence")
    @classmethod
    def validate_model_shape(cls, value: list[list[float]]) -> list[list[float]]:
        if len(value) != 30:
            raise ValueError("raw_feature_sequence must contain exactly 30 frames")
        if any(len(frame) != 30 for frame in value):
            raise ValueError("each raw feature frame must contain exactly 30 values")
        return value


class InferenceResponse(ContractModel):
    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    message_id: str
    session_id: str
    processed_at: datetime = Field(default_factory=utc_now)
    model_name: str
    model_version: str
    state: Literal["FOCUSED", "DISTRACTED", "NO_FACE"]
    ai_state: str
    focus_score: float = Field(ge=0.0, le=1.0)
    components: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = Field(ge=0.0)


class SessionSummary(ContractModel):
    duration_seconds: int = Field(ge=0)
    focused_seconds: int = Field(ge=0)
    average_focus: float = Field(ge=0.0, le=1.0)
    distraction_count: int = Field(ge=0)
    focus_streak_seconds: float = Field(ge=0.0)
    completed: bool
    minute_focus_scores: list[float] = Field(default_factory=list)
