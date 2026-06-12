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

    @classmethod
    def from_env(cls) -> "ServerSettings":
        load_dotenv()
        origins = tuple(
            item.strip()
            for item in os.getenv("FOCUSFLOW_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
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
        )
