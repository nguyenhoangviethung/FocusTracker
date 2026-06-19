from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Protocol

from server.config import ServerSettings
from shared.contracts import SessionCreate, SessionRecord, SessionSummary, utc_now


class SessionRepository(Protocol):
    def create(self, payload: SessionCreate) -> SessionRecord: ...

    def get(self, session_id: str) -> dict[str, Any] | None: ...

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]: ...

    def list_by_user(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]: ...

    def delete(self, session_id: str) -> bool: ...

    def touch(self, session_id: str) -> None: ...

    def complete(self, session_id: str, summary: SessionSummary) -> dict[str, Any] | None: ...

    def update(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None: ...

    def expire_stale(self, cutoff: datetime, limit: int = 500) -> list[str]: ...


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _stale_summary(record: dict[str, Any], ended_at: datetime) -> dict[str, Any]:
    started_at = _parse_datetime(record.get("started_at")) or ended_at
    duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
    planned_seconds = int(record.get("duration_seconds") or duration_seconds or 0)
    if planned_seconds > 0:
        duration_seconds = min(duration_seconds, planned_seconds)
    return {
        "duration_seconds": duration_seconds,
        "focused_seconds": 0,
        "average_focus": 0.0,
        "distraction_count": 0,
        "focus_streak_seconds": 0.0,
        "completed": False,
        "minute_focus_scores": [],
    }


def _expire_record_if_stale(record: dict[str, Any], cutoff: datetime, now: datetime) -> bool:
    if record.get("ended_at"):
        return False
    last_seen_at = _parse_datetime(record.get("last_seen_at")) or _parse_datetime(record.get("started_at"))
    if last_seen_at is None or last_seen_at > cutoff:
        return False
    ended_at = min(last_seen_at, now)
    ended_at_iso = ended_at.isoformat()
    record.update(
        {
            "status": "cancelled",
            "ended_at": ended_at_iso,
            "last_seen_at": ended_at_iso,
            "summary": _stale_summary(record, ended_at),
            "report_status": "stale_timeout",
            "report_started_at": ended_at_iso,
            "report_completed_at": ended_at_iso,
            "cancellation_reason": "stale_timeout",
        }
    )
    return True


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

    def list_by_user(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            records = sorted(
                [r for r in self._records.values() if r.get("user_id") == user_id],
                key=lambda record: str(record.get("started_at", "")),
                reverse=True,
            )
            return [dict(record) for record in records[:limit]]

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._records.pop(session_id, None) is not None

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

    def expire_stale(self, cutoff: datetime, limit: int = 500) -> list[str]:
        now = utc_now()
        expired: list[str] = []
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda record: str(record.get("last_seen_at") or record.get("started_at") or ""),
            )
            for record in records:
                if len(expired) >= limit:
                    break
                if _expire_record_if_stale(record, cutoff, now):
                    expired.append(str(record.get("session_id")))
        return expired


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

    def list_by_user(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        query = self._collection.where("user_id", "==", user_id)
        results = [doc.to_dict() for doc in query.stream() if doc.exists and doc.to_dict()]
        results.sort(key=lambda x: str(x.get("started_at", "")), reverse=True)
        return results[:limit]

    def delete(self, session_id: str) -> bool:
        reference = self._collection.document(session_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return False
        reference.delete()
        return True

    def touch(self, session_id: str) -> None:
        self._collection.document(session_id).update(
            {"last_seen_at": utc_now().isoformat()}
        )

    def complete(self, session_id: str, summary: SessionSummary) -> dict[str, Any] | None:
        reference = self._collection.document(session_id)

        @self._firestore.transactional
        def _complete(transaction):
            snapshot = reference.get(transaction=transaction)
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
            transaction.update(reference, updates)
            existing.update(updates)
            return existing

        return _complete(self._client.transaction())

    def update(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        reference = self._collection.document(session_id)
        reference.update(updates)
        return dict(updates)

    def expire_stale(self, cutoff: datetime, limit: int = 500) -> list[str]:
        query = self._collection.where("last_seen_at", "<=", cutoff.isoformat()).limit(limit)
        now = utc_now()
        expired: list[str] = []
        for snapshot in query.stream():
            if not snapshot.exists:
                continue
            record = snapshot.to_dict() or {}
            if not _expire_record_if_stale(record, cutoff, now):
                continue
            snapshot.reference.update(
                {
                    "status": record["status"],
                    "ended_at": record["ended_at"],
                    "last_seen_at": record["last_seen_at"],
                    "summary": record["summary"],
                    "report_status": record["report_status"],
                    "report_started_at": record["report_started_at"],
                    "report_completed_at": record["report_completed_at"],
                    "cancellation_reason": record["cancellation_reason"],
                }
            )
            expired.append(str(record.get("session_id") or snapshot.id))
        return expired


def create_session_repository(settings: ServerSettings) -> SessionRepository:
    if settings.repository_backend == "firestore":
        return FirestoreSessionRepository(
            project_id=settings.gcp_project_id,
            collection_name=settings.firestore_sessions_collection,
        )
    return InMemorySessionRepository()
