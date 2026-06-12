from __future__ import annotations

from datetime import datetime
import threading
from typing import Any, Protocol

from server.config import ServerSettings
from shared.contracts import SessionCreate, SessionRecord, SessionSummary, utc_now


class SessionRepository(Protocol):
    def create(self, payload: SessionCreate) -> SessionRecord: ...

    def get(self, session_id: str) -> dict[str, Any] | None: ...

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]: ...

    def touch(self, session_id: str) -> None: ...

    def complete(self, session_id: str, summary: SessionSummary) -> dict[str, Any] | None: ...

    def update(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None: ...


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, payload: SessionCreate) -> SessionRecord:
        record = SessionRecord(**payload.model_dump())
        with self._lock:
            self._records[record.session_id] = record.model_dump(mode="json")
        return record

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(session_id)
            return dict(record) if record else None

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda record: str(record.get("started_at", "")),
                reverse=True,
            )
            return [dict(record) for record in records[:limit]]

    def touch(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._records:
                self._records[session_id]["last_seen_at"] = utc_now().isoformat()

    def complete(self, session_id: str, summary: SessionSummary) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            if record.get("ended_at"):
                return dict(record)
            completed_at = utc_now().isoformat()
            record.update(
                {
                    "status": "completed" if summary.completed else "cancelled",
                    "ended_at": completed_at,
                    "last_seen_at": completed_at,
                    "summary": summary.model_dump(mode="json"),
                    "report_status": "completed",
                    "report_started_at": completed_at,
                    "report_completed_at": completed_at,
                }
            )
            return dict(record)

    def update(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            record.update(updates)
            return dict(record)


class FirestoreSessionRepository:
    def __init__(self, project_id: str, collection_name: str) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-firestore is required for FOCUSFLOW_REPOSITORY=firestore"
            ) from exc

        self._client = firestore.Client(project=project_id or None)
        self._firestore = firestore
        self._collection = self._client.collection(collection_name)

    def create(self, payload: SessionCreate) -> SessionRecord:
        record = SessionRecord(**payload.model_dump())
        self._collection.document(record.session_id).set(record.model_dump(mode="json"))
        return record

    def get(self, session_id: str) -> dict[str, Any] | None:
        snapshot = self._collection.document(session_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        query = self._collection.order_by(
            "started_at",
            direction=self._firestore.Query.DESCENDING,
        ).limit(limit)
        return [doc.to_dict() for doc in query.stream() if doc.exists and doc.to_dict()]

    def touch(self, session_id: str) -> None:
        self._collection.document(session_id).update(
            {"last_seen_at": utc_now().isoformat()}
        )

    def complete(self, session_id: str, summary: SessionSummary) -> dict[str, Any] | None:
        reference = self._collection.document(session_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return None
        existing = snapshot.to_dict() or {}
        if existing.get("ended_at"):
            return existing
        completed_at = utc_now().isoformat()
        updates = {
            "status": "completed" if summary.completed else "cancelled",
            "ended_at": completed_at,
            "last_seen_at": completed_at,
            "summary": summary.model_dump(mode="json"),
            "report_status": "completed",
            "report_started_at": completed_at,
            "report_completed_at": completed_at,
        }
        reference.update(updates)
        record = existing
        record.update(updates)
        return record

    def update(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        reference = self._collection.document(session_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return None
        reference.update(updates)
        record = snapshot.to_dict() or {}
        record.update(updates)
        return record


def create_session_repository(settings: ServerSettings) -> SessionRepository:
    if settings.repository_backend == "firestore":
        return FirestoreSessionRepository(
            project_id=settings.gcp_project_id,
            collection_name=settings.firestore_sessions_collection,
        )
    return InMemorySessionRepository()
