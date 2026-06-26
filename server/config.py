from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class ServerSettings:
    environment: str
    repository_backend: str
    gcp_project_id: str
    api_key: str
    firestore_sessions_collection: str
    event_backend: str
    pubsub_session_events_topic: str
    cors_origins: tuple[str, ...]
    google_oauth_client_id: str
    firestore_users_collection: str
    stale_session_timeout_seconds: int
    stale_session_cleanup_interval_seconds: int
    release_version: str
    release_windows_url: str
    release_macos_url: str
    release_linux_url: str
    release_checksums_url: str

    @classmethod
    def from_env(cls) -> "ServerSettings":
        load_dotenv()
        origins = tuple(
            item.strip()
            for item in os.getenv("FOCUSFLOW_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
        release_base_url = os.getenv("FOCUSFLOW_RELEASE_BASE_URL", "").strip().rstrip("/")
        return cls(
            environment=os.getenv("FOCUSFLOW_ENV", "development").strip().lower(),
            repository_backend=os.getenv("FOCUSFLOW_REPOSITORY", "memory").strip().lower(),
            gcp_project_id=os.getenv("GOOGLE_CLOUD_PROJECT", "").strip(),
            api_key=os.getenv("FOCUSFLOW_API_KEY", "").strip(),
            firestore_sessions_collection=os.getenv(
                "FOCUSFLOW_FIRESTORE_SESSIONS_COLLECTION",
                "focusflow_sessions",
            ).strip(),
            event_backend=os.getenv("FOCUSFLOW_EVENT_BACKEND", "logging").strip().lower(),
            pubsub_session_events_topic=os.getenv(
                "FOCUSFLOW_PUBSUB_SESSION_EVENTS_TOPIC",
                "focusflow-session-events",
            ).strip(),
            cors_origins=origins,
            google_oauth_client_id=os.getenv(
                "FOCUSFLOW_GOOGLE_OAUTH_CLIENT_ID",
                "",
            ).strip(),
            firestore_users_collection=os.getenv(
                "FOCUSFLOW_FIRESTORE_USERS_COLLECTION",
                "focusflow_users",
            ).strip(),
            stale_session_timeout_seconds=int(
                os.getenv("FOCUSFLOW_STALE_SESSION_TIMEOUT_SECONDS", "600")
            ),
            stale_session_cleanup_interval_seconds=int(
                os.getenv("FOCUSFLOW_STALE_SESSION_CLEANUP_INTERVAL_SECONDS", "60")
            ),
            release_version=os.getenv("FOCUSFLOW_RELEASE_VERSION", "preview").strip(),
            release_windows_url=_release_url("FOCUSFLOW_RELEASE_WINDOWS_URL", release_base_url, "FocusFlowAI-Windows.exe"),
            release_macos_url=_release_url("FOCUSFLOW_RELEASE_MACOS_URL", release_base_url, "FocusFlowAI-macOS.dmg"),
            release_linux_url=_release_url("FOCUSFLOW_RELEASE_LINUX_URL", release_base_url, "FocusFlowAI-Linux.tar.gz"),
            release_checksums_url=_release_url("FOCUSFLOW_RELEASE_CHECKSUMS_URL", release_base_url, "SHA256SUMS.txt"),
        )


def _release_url(env_name: str, base_url: str, filename: str) -> str:
    explicit_url = os.getenv(env_name, "").strip()
    if explicit_url:
        return explicit_url
    return f"{base_url}/{filename}" if base_url else ""
