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
from shared.identifiers import new_google_user_id, new_password_user_id, new_session_id

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
    "new_google_user_id",
    "new_password_user_id",
    "new_session_id",
]
