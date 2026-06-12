"""Versioned contracts shared by the edge client and cloud services."""

from shared.contracts import (
    AuthGoogleLogin,
    AuthPasswordLogin,
    AuthPasswordRegister,
    AuthProfile,
    PROTOCOL_VERSION,
    InferenceResponse,
    SessionCreate,
    SessionRecord,
    SessionSummary,
    TelemetryPacket,
)

__all__ = [
    "AuthGoogleLogin",
    "AuthPasswordLogin",
    "AuthPasswordRegister",
    "AuthProfile",
    "PROTOCOL_VERSION",
    "InferenceResponse",
    "SessionCreate",
    "SessionRecord",
    "SessionSummary",
    "TelemetryPacket",
]
