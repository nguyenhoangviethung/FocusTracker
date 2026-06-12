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
from shared.identifiers import (
    google_subject_document_id,
    new_google_user_id,
    new_password_user_id,
    new_session_id,
    username_document_id,
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
    "google_subject_document_id",
    "new_google_user_id",
    "new_password_user_id",
    "new_session_id",
    "username_document_id",
]
