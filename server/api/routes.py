from __future__ import annotations

import asyncio
from collections import Counter
from datetime import timedelta
import logging
import secrets
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from server.api.dashboard_ui import render_dashboard_html
from server.api.release_ui import render_release_html
from server.config import ServerSettings
from server.core.inference import CloudInferenceEngine
from server.repositories.sessions import SessionRepository
from server.repositories.users import UserRepository
from server.services.event_publisher import EventPublisher
from server.services.auth_service import extract_google_profile, hash_password, profile_from_record, verify_password
from shared.contracts import (
    AuthGoogleLogin,
    AuthPasswordLogin,
    AuthPasswordChange,
    AuthPasswordRegister,
    AuthProfile,
    InferenceResponse,
    SessionCreate,
    SessionRecord,
    SessionSummary,
    TelemetryPacket,
    UserStats,
    utc_now,
)


router = APIRouter()
logger = logging.getLogger(__name__)
DASHBOARD_CACHE_SECONDS = 3.0


class DashboardSnapshotCache:
    def __init__(self, ttl_seconds: float = DASHBOARD_CACHE_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[int, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get_or_load(
        self,
        limit: int,
        loader,
    ) -> tuple[dict[str, Any], bool]:
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(limit)
            if cached and now - cached[0] < self.ttl_seconds:
                return cached[1], True
            snapshot = loader()
            self._entries[limit] = (time.monotonic(), snapshot)
            return snapshot, False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def _dashboard_snapshot(request: Request, limit: int = 24) -> dict[str, Any]:
    settings, repository, user_repository, engine, _ = _services(request)
    safe_limit = max(1, min(int(limit or 24), 100))
    dashboard_error: str | None = None
    try:
        recent = repository.list_recent(safe_limit)
    except Exception:
        logger.exception("Dashboard failed to load recent sessions")
        recent = []
        dashboard_error = "Session storage is temporarily unavailable"
    user_ids = [
        str(record.get("user_id"))
        for record in recent
        if record.get("user_id")
    ]
    try:
        user_cache = user_repository.get_many(user_ids)
    except Exception:
        logger.warning("Dashboard failed to resolve users", exc_info=True)
        user_cache = {}

    def decorate(record: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(record)
        _normalize_dashboard_session(decorated)
        user = user_cache.get(str(record.get("user_id") or ""))
        if user:
            decorated["user_display_name"] = user.get("display_name") or user.get("email") or user.get("username") or user.get("user_id")
            decorated["user_email"] = user.get("email")
            decorated["user_username"] = user.get("username")
        else:
            decorated["user_display_name"] = record.get("user_id") or "-"
            decorated["user_email"] = None
            decorated["user_username"] = None
        return decorated

    recent = [decorate(record) for record in recent]
    status_counts = Counter(str(record.get("status") or "unknown") for record in recent)
    active_sessions = sum(1 for record in recent if not record.get("ended_at"))
    latest = recent[0] if recent else None
    return {
        "environment": settings.environment,
        "repository_backend": settings.repository_backend,
        "event_backend": settings.event_backend,
        "api_key_configured": bool(settings.api_key),
        "ready": engine is not None and repository is not None,
        "recent_count": len(recent),
        "active_sessions": active_sessions,
        "status_counts": dict(status_counts),
        "latest_session": latest,
        "recent_sessions": recent,
        "dashboard_error": dashboard_error,
        "firestore_query_limit": safe_limit,
    }


def _normalize_dashboard_session(record: dict[str, Any]) -> None:
    live_metrics = record.get("live_metrics")
    if not isinstance(live_metrics, dict):
        return

    if not live_metrics.get("state") and live_metrics.get("ai_state"):
        live_metrics["state"] = str(live_metrics["ai_state"])

    if live_metrics.get("focus_score") is None:
        class_probabilities = live_metrics.get("class_probabilities")
        if isinstance(class_probabilities, list) and len(class_probabilities) >= 4:
            try:
                live_metrics["focus_score"] = float(class_probabilities[3])
            except (TypeError, ValueError):
                pass

    if live_metrics.get("focus_score") is None:
        components = live_metrics.get("components")
        if isinstance(components, dict):
            probabilities: list[float] = []
            for key in (
                "final_xgb",
                "boost_xgb",
                "targeted_xgb",
                "layer1_extra_trees",
                "layer1_random_forest",
                "layer2_cascade",
                # Historical Firestore snapshots predate the Triple XGB
                # product migration and remain readable in the dashboard.
                "gru",
                "tcn",
                "xgboost",
            ):
                value = components.get(key)
                if isinstance(value, dict) and value.get("probability") is not None:
                    try:
                        probabilities.append(float(value["probability"]))
                    except (TypeError, ValueError):
                        continue
            if probabilities:
                live_metrics["focus_score"] = sum(probabilities) / len(probabilities)

    if live_metrics.get("focus_score") is None:
        summary = record.get("summary")
        if isinstance(summary, dict) and summary.get("average_focus") is not None:
            live_metrics["focus_score"] = summary.get("average_focus")


def _live_session_updates(
    response: InferenceResponse,
    packet: TelemetryPacket,
) -> dict[str, Any]:
    return {
        "last_seen_at": response.processed_at.isoformat(),
        "live_metrics": {
            "sequence_number": packet.sequence_number,
            "captured_at": packet.captured_at.isoformat(),
            "processed_at": response.processed_at.isoformat(),
            "state": response.state,
            "ai_state": response.ai_state,
            "focus_score": response.focus_score,
            "label_space": response.label_space,
            "face_found": packet.face_found,
            "latency_ms": response.latency_ms,
            "model_inference_latency_ms": response.inference_latency_ms,
            "components": response.components,
            "class_labels": response.class_labels,
            "class_probabilities": response.class_probabilities,
            "predicted_class": response.predicted_class,
            "predicted_label": response.predicted_label,
        },
    }





def _dashboard_html(settings: ServerSettings) -> str:
    return render_dashboard_html(settings.api_key or "")


def _release_html(settings: ServerSettings) -> str:
    return render_release_html(settings)


def _expire_stale_sessions(settings: ServerSettings, repository: SessionRepository) -> list[str]:
    timeout_seconds = max(60, int(settings.stale_session_timeout_seconds))
    cutoff = utc_now() - timedelta(seconds=timeout_seconds)
    expired_ids = repository.expire_stale(cutoff, limit=500)
    if expired_ids:
        logger.warning(
            "Expired stale sessions count=%d timeout_seconds=%d",
            len(expired_ids),
            timeout_seconds,
        )
    return expired_ids


def _services(
    request: Request,
) -> tuple[
    ServerSettings,
    SessionRepository,
    UserRepository,
    CloudInferenceEngine,
    EventPublisher,
]:
    return (
        request.app.state.settings,
        request.app.state.session_repository,
        request.app.state.user_repository,
        request.app.state.inference_engine,
        request.app.state.event_publisher,
    )


def _verify_api_key(settings: ServerSettings, supplied: str | None) -> None:
    if not settings.api_key:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="Server API key is not configured")
        return
    if not supplied or not secrets.compare_digest(settings.api_key, supplied):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/download", response_class=HTMLResponse, include_in_schema=False)
async def download_portal(request: Request) -> HTMLResponse:
    return HTMLResponse(_release_html(request.app.state.settings))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return HTMLResponse(_dashboard_html(settings))



@router.get("/dashboard/api/summary")
async def dashboard_summary(request: Request, limit: int | None = None) -> dict[str, Any]:
    query_limit = getattr(request.app.state, "query_limit", 100)
    if limit is not None:
        query_limit = limit
    safe_limit = max(1, min(int(query_limit), 100))

    cache: DashboardSnapshotCache = request.app.state.dashboard_cache
    settings, repository, _, _, _ = _services(request)
    expired_ids = _expire_stale_sessions(settings, repository)
    if expired_ids:
        cache.clear()

    def load_snapshot() -> tuple[dict[str, Any], bool]:
        return cache.get_or_load(
            safe_limit,
            lambda: _dashboard_snapshot(request, safe_limit),
        )

    snapshot, cache_hit = load_snapshot()
    return {
        **snapshot,
        "dashboard_cache_hit": cache_hit,
        "dashboard_cache_seconds": cache.ttl_seconds,
        "expired_stale_sessions": expired_ids,
    }


@router.post("/dashboard/api/settings")
async def dashboard_update_settings(
    request: Request,
    payload: dict[str, Any],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, _, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)

    cache_seconds = payload.get("cache_seconds")
    query_limit = payload.get("query_limit")

    if cache_seconds is not None:
        try:
            val = float(cache_seconds)
            if val < 0.5 or val > 60.0:
                raise HTTPException(status_code=422, detail="Cache window must be between 0.5 and 60 seconds")
            request.app.state.dashboard_cache.ttl_seconds = val
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid cache_seconds value") from exc

    if query_limit is not None:
        try:
            val = int(query_limit)
            if val < 1 or val > 100:
                raise HTTPException(status_code=422, detail="Query limit must be between 1 and 100")
            request.app.state.query_limit = val
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Invalid query_limit value") from exc

    request.app.state.dashboard_cache.clear()
    logger.info(
        "Dashboard settings updated cache_seconds=%s query_limit=%s",
        cache_seconds,
        query_limit,
    )
    return {
        "status": "success",
        "cache_seconds": request.app.state.dashboard_cache.ttl_seconds,
        "query_limit": getattr(request.app.state, "query_limit", 100),
    }


@router.post("/dashboard/api/sessions/create")
async def dashboard_create_session(
    request: Request,
    payload: dict[str, Any],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)

    user_id = payload.get("user_id", "admin-demo")
    device_id = payload.get("device_id", "demo-device")
    duration = int(payload.get("duration_seconds", 1800))
    status = payload.get("status", "active")

    create_payload = SessionCreate(
        device_id=device_id,
        user_id=user_id,
        duration_seconds=duration,
    )

    record = repository.create(create_payload)

    updates = {}
    if status in ("completed", "cancelled"):
        completed = (status == "completed")
        import random
        minutes = max(1, duration // 60)
        mock_scores = [round(random.uniform(0.3, 0.98), 2) for _ in range(minutes)]
        avg_focus = sum(mock_scores) / len(mock_scores)

        summary = {
            "duration_seconds": duration,
            "focused_seconds": int(duration * avg_focus),
            "average_focus": avg_focus,
            "distraction_count": random.randint(1, 6),
            "focus_streak_seconds": float(random.randint(120, 600)),
            "completed": completed,
            "minute_focus_scores": mock_scores,
        }

        ended_at = utc_now().isoformat()
        updates = {
            "status": status,
            "ended_at": ended_at,
            "last_seen_at": ended_at,
            "summary": summary,
            "report_status": "completed",
            "report_started_at": ended_at,
            "report_completed_at": ended_at,
        }

    if updates:
        repository.update(record.session_id, updates)

    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()

    return {"status": "created", "session_id": record.session_id}


@router.post("/dashboard/api/sessions/{session_id}/update")
async def dashboard_update_session(
    request: Request,
    session_id: str,
    payload: dict[str, Any],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)

    existing = repository.get(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = {}
    if "user_id" in payload:
        updates["user_id"] = str(payload["user_id"]).strip()
    if "device_id" in payload:
        updates["device_id"] = str(payload["device_id"]).strip()
    if "status" in payload:
        status = payload["status"]
        if status in ("active", "completed", "cancelled"):
            updates["status"] = status
            if status != "active" and not existing.get("ended_at"):
                ended_at = utc_now().isoformat()
                updates["ended_at"] = ended_at
                updates["last_seen_at"] = ended_at

                if not existing.get("summary"):
                    updates["summary"] = {
                        "duration_seconds": existing.get("duration_seconds", 1800),
                        "focused_seconds": 0,
                        "average_focus": 0.0,
                        "distraction_count": 0,
                        "focus_streak_seconds": 0.0,
                        "completed": (status == "completed"),
                        "minute_focus_scores": [0.5, 0.6, 0.7],
                    }
                    updates["report_status"] = "completed"
                    updates["report_started_at"] = ended_at
                    updates["report_completed_at"] = ended_at
            elif status == "active":
                updates["ended_at"] = None
                updates["summary"] = None
                updates["report_status"] = None
                updates["report_started_at"] = None
                updates["report_completed_at"] = None

    if "notes" in payload:
        summary = existing.get("summary") or {}
        summary["notes"] = str(payload["notes"]).strip()
        updates["summary"] = summary

    if updates:
        repository.update(session_id, updates)

    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()

    return {"status": "updated", "session_id": session_id}


@router.post("/dashboard/api/sessions/{session_id}/finalize")
async def dashboard_finalize_session(
    request: Request,
    session_id: str,
    payload: dict[str, Any],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, publisher = _services(request)
    _verify_api_key(settings, x_api_key)

    existing = repository.get(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session not found")

    duration = int(payload.get("duration_seconds") or existing.get("duration_seconds") or 1800)
    completed = bool(payload.get("completed", True))

    import random
    minutes = max(1, duration // 60)
    mock_scores = [round(random.uniform(0.4, 0.98), 2) for _ in range(minutes)]
    avg_focus = sum(mock_scores) / len(mock_scores)

    summary = SessionSummary(
        duration_seconds=duration,
        focused_seconds=int(duration * avg_focus),
        average_focus=avg_focus,
        distraction_count=random.randint(1, 5),
        focus_streak_seconds=float(random.randint(150, 700)),
        completed=completed,
        minute_focus_scores=mock_scores,
    )

    completed_at = utc_now().isoformat()
    updates = {
        "status": "completed" if completed else "cancelled",
        "ended_at": completed_at,
        "last_seen_at": completed_at,
        "summary": summary.model_dump(mode="json"),
        "report_status": "completed",
        "report_started_at": completed_at,
        "report_completed_at": completed_at,
    }

    repository.update(session_id, updates)

    try:
        publisher.publish(
            "session.completed",
            {
                "session_id": session_id,
                "device_id": existing.get("device_id"),
                "summary": summary.model_dump(mode="json"),
            },
        )
    except Exception:
        logger.error(
            "Dashboard manual finalization event publish failed session_id=%s",
            session_id,
            exc_info=True,
        )

    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()

    return {"status": "finalized", "session_id": session_id}


@router.delete("/dashboard/api/sessions/{session_id}")
async def dashboard_delete_session(
    request: Request,
    session_id: str,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    existing = repository.get(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session not found")
    deleted = repository.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
    logger.info("Dashboard deleted session session_id=%s", session_id)
    return {"status": "deleted", "session_id": session_id}


@router.post("/dashboard/api/sessions/batch-delete")
async def dashboard_batch_delete_sessions(
    request: Request,
    payload: dict[str, Any],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    raw_session_ids = payload.get("session_ids")
    if not isinstance(raw_session_ids, list):
        raise HTTPException(status_code=422, detail="session_ids must be a list")
    session_ids = [
        str(session_id).strip()
        for session_id in raw_session_ids
        if str(session_id).strip()
    ]
    deleted_ids = []
    for sid in session_ids:
        deleted = repository.delete(sid)
        if deleted:
            deleted_ids.append(sid)
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
    logger.info(
        "Dashboard batch delete requested=%d deleted=%d",
        len(session_ids),
        len(deleted_ids),
    )
    return {"status": "deleted", "deleted_ids": deleted_ids}


@router.post("/dashboard/api/sessions/clear-stale")
async def dashboard_clear_stale_sessions(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    expired_ids = _expire_stale_sessions(settings, repository)
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
    logger.info("Dashboard expired stale sessions count=%d", len(expired_ids))
    return {"status": "expired", "expired_ids": expired_ids}


@router.post("/dashboard/api/sessions/clear-all")
async def dashboard_clear_all_sessions(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    deleted_ids: list[str] = []
    seen_ids: set[str] = set()
    max_rounds = 20
    for _ in range(max_rounds):
        recent = repository.list_recent(100)
        session_ids = [
            str(session.get("session_id") or "")
            for session in recent
            if session.get("session_id")
        ]
        session_ids = [sid for sid in session_ids if sid and sid not in seen_ids]
        if not session_ids:
            break
        for sid in session_ids:
            seen_ids.add(sid)
            deleted = repository.delete(sid)
            if deleted:
                deleted_ids.append(sid)
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
    logger.info("Dashboard cleared all visible sessions deleted=%d", len(deleted_ids))
    return {"status": "cleared", "deleted_ids": deleted_ids}




@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    engine = getattr(request.app.state, "inference_engine", None)
    repository = getattr(request.app.state, "session_repository", None)
    if engine is None or repository is None:
        raise HTTPException(status_code=503, detail="Application is not ready")
    return {"status": "ready"}


@router.post("/v1/auth/password/register", response_model=AuthProfile, status_code=201)
async def register_password_user(
    payload: AuthPasswordRegister,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthProfile:
    settings, _, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    password_hash, password_salt, iterations = hash_password(payload.password)
    try:
        record = await asyncio.to_thread(
            user_repository.create_password_user,
            payload.username,
            password_hash,
            password_salt,
            payload.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Password registration storage failure")
        raise HTTPException(
            status_code=503,
            detail="Identity storage is temporarily unavailable",
        ) from exc
    record["password_iterations"] = iterations
    return profile_from_record(record)


@router.post("/v1/auth/password/login", response_model=AuthProfile)
async def login_password_user(
    payload: AuthPasswordLogin,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthProfile:
    settings, _, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    try:
        record = await asyncio.to_thread(user_repository.get_by_username, payload.username)
    except Exception as exc:
        logger.exception("Password login storage failure")
        raise HTTPException(
            status_code=503,
            detail="Identity storage is temporarily unavailable",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(
        payload.password,
        str(record.get("password_hash") or ""),
        str(record.get("password_salt") or ""),
        int(record.get("password_iterations") or 390000),
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    try:
        updated = await asyncio.to_thread(user_repository.login_password_user, payload.username)
    except Exception:
        logger.warning("Failed to update password login timestamp", exc_info=True)
        updated = None
    return profile_from_record(updated or record)


@router.put("/v1/auth/password", response_model=AuthProfile)
async def change_password_user(
    payload: AuthPasswordChange,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthProfile:
    settings, _, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    try:
        record = await asyncio.to_thread(user_repository.get_by_username, payload.username)
    except Exception as exc:
        logger.exception("Password change storage failure")
        raise HTTPException(
            status_code=503,
            detail="Identity storage is temporarily unavailable",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")
        
    if not verify_password(
        payload.old_password,
        str(record.get("password_hash") or ""),
        str(record.get("password_salt") or ""),
        int(record.get("password_iterations") or 390000),
    ):
        raise HTTPException(status_code=401, detail="Invalid current password")
        
    new_hash, new_salt, iterations = hash_password(payload.new_password)
    try:
        updated = await asyncio.to_thread(user_repository.update_password, payload.username, new_hash, new_salt)
    except Exception as exc:
        logger.exception("Password change update failure")
        raise HTTPException(status_code=503, detail="Failed to update password") from exc
        
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    updated["password_iterations"] = iterations
    return profile_from_record(updated)


@router.post("/v1/auth/google", response_model=AuthProfile)
async def login_google_user(
    payload: AuthGoogleLogin,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> AuthProfile:
    settings, _, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    if not settings.google_oauth_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth client is not configured")
    try:
        claims = await asyncio.to_thread(extract_google_profile, payload.id_token, settings.google_oauth_client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Google token") from exc

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(status_code=401, detail="Google token missing subject")
    try:
        record = await asyncio.to_thread(
            user_repository.upsert_google_user,
            subject,
            str(claims.get("email") or "") or None,
            str(claims.get("name") or "") or None,
            str(claims.get("jti") or "") or None,
        )
    except Exception as exc:
        logger.exception("Google login storage failure")
        raise HTTPException(
            status_code=503,
            detail="Identity storage is temporarily unavailable",
        ) from exc
    return profile_from_record(record)


@router.get("/v1/users/{username}/stats", response_model=UserStats)
async def get_user_stats(
    username: str,
    request: Request,
    user_id: str | None = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> UserStats:
    from datetime import datetime, timedelta, timezone

    settings, repository, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)

    # Resolve user_id: prefer explicit query param, then lookup by username
    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        user = await asyncio.to_thread(user_repository.get_by_username, username)
        if user:
            resolved_user_id = str(user.get("user_id", ""))

    # Fallback: construct deterministic user_id from username pattern
    if not resolved_user_id:
        resolved_user_id = f"user_password_{username.lower().strip()}"

    sessions = await asyncio.to_thread(repository.list_by_user, resolved_user_id, 100)

    total_focused_seconds = 0
    total_score = 0.0
    scored_sessions = 0
    recent_activity: list[dict[str, str]] = []
    session_dates: list[str] = []

    for sess in sessions:
        summary = sess.get("summary") or {}
        status = sess.get("status", "")
        has_summary = bool(summary.get("duration_seconds") or summary.get("focused_seconds"))

        if has_summary and status in ("completed", "cancelled"):
            scored_sessions += 1
            total_focused_seconds += int(summary.get("focused_seconds", 0))
            total_score += float(summary.get("average_focus", 0.0))

            started_at = sess.get("started_at", "")
            if started_at:
                try:
                    dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    session_dates.append(dt.strftime("%Y-%m-%d"))
                    if len(recent_activity) < 5:
                        label = dt.strftime("%a %d/%m, %I:%M %p")
                        mins = int(summary.get("focused_seconds", 0)) // 60
                        score_pct = int(float(summary.get("average_focus", 0)) * 100)
                        recent_activity.append({
                            "label": label,
                            "description": f"{mins}m focused · {score_pct}%",
                        })
                except Exception:
                    pass

    avg_score = (total_score / scored_sessions) if scored_sessions > 0 else 0.0
    hours = total_focused_seconds / 3600.0

    # Calculate day streak
    streak = 0
    if session_dates:
        unique_days = sorted(set(session_dates), reverse=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        if unique_days[0] in (today, yesterday):
            streak = 1
            for i in range(1, len(unique_days)):
                prev = datetime.strptime(unique_days[i - 1], "%Y-%m-%d")
                curr = datetime.strptime(unique_days[i], "%Y-%m-%d")
                if (prev - curr).days == 1:
                    streak += 1
                else:
                    break

    return UserStats(
        total_focus_hours=f"{hours:.1f}h",
        total_sessions=str(scored_sessions),
        average_score=f"{int(avg_score * 100)}%",
        current_streak=str(streak),
        recent_activity=recent_activity,
    )


@router.get("/v1/users/{username}/sessions")
async def get_user_sessions(
    username: str,
    request: Request,
    user_id: str | None = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    settings, repository, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)

    # Resolve user_id
    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        user = await asyncio.to_thread(user_repository.get_by_username, username)
        if user:
            resolved_user_id = str(user.get("user_id", ""))

    if not resolved_user_id:
        resolved_user_id = f"user_password_{username.lower().strip()}"

    sessions = await asyncio.to_thread(repository.list_by_user, resolved_user_id, 100)
    return sessions



@router.post("/v1/sessions", response_model=SessionRecord, status_code=201)
async def create_session(
    payload: SessionCreate,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> SessionRecord:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    return await asyncio.to_thread(repository.create, payload)


@router.get("/v1/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    record = await asyncio.to_thread(repository.get, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return record


@router.delete("/v1/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    existing = await asyncio.to_thread(repository.get, session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session not found")
    deleted = await asyncio.to_thread(repository.delete, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.post("/v1/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    summary: SessionSummary,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, publisher = _services(request)
    _verify_api_key(settings, x_api_key)
    existing = await asyncio.to_thread(repository.get, session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if existing.get("ended_at"):
        return existing
    record = await asyncio.to_thread(repository.complete, session_id, summary)
    if record is None:  # Defensive guard for concurrent deletion.
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await asyncio.to_thread(
            publisher.publish,
            "session.completed",
            {
                "session_id": session_id,
                "device_id": record.get("device_id"),
                "summary": summary.model_dump(mode="json"),
            },
        )
    except Exception:
        logger.error(
            "Session completed but event publication failed session_id=%s",
            session_id,
            exc_info=True,
        )
    return record


@router.post("/v1/inference", response_model=InferenceResponse)
async def run_inference(
    packet: TelemetryPacket,
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> InferenceResponse:
    settings, repository, _, engine, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    session = await asyncio.to_thread(repository.get, packet.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if str(session.get("device_id")) != packet.device_id:
        raise HTTPException(status_code=403, detail="Device does not own this session")
    response = await asyncio.to_thread(engine.predict, packet)
    try:
        await asyncio.to_thread(
            repository.update,
            packet.session_id,
            _live_session_updates(response, packet),
        )
    except Exception:
        logger.warning(
            "Inference succeeded but live metrics update failed session_id=%s",
            packet.session_id,
            exc_info=True,
        )
    return response


@router.websocket("/v1/ws/sessions/{session_id}")
async def session_telemetry(websocket: WebSocket, session_id: str) -> None:
    settings: ServerSettings = websocket.app.state.settings
    supplied_key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    try:
        _verify_api_key(settings, supplied_key)
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid API key")
        return

    device_id = websocket.query_params.get("device_id", "")
    repository: SessionRepository = websocket.app.state.session_repository
    session = await asyncio.to_thread(repository.get, session_id)
    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return
    if not device_id or str(session.get("device_id")) != device_id:
        await websocket.close(code=4403, reason="Device does not own this session")
        return

    engine: CloudInferenceEngine = websocket.app.state.inference_engine
    await websocket.accept()
    receive_timeout_seconds = max(60, int(settings.stale_session_timeout_seconds))
    try:
        while True:
            try:
                raw_payload = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=receive_timeout_seconds,
                )
            except asyncio.TimeoutError:
                expired_ids = _expire_stale_sessions(settings, repository)
                logger.warning(
                    "WebSocket telemetry timed out session_id=%s expired=%s",
                    session_id,
                    session_id in expired_ids,
                )
                await websocket.close(code=1001, reason="Telemetry timeout")
                return
            try:
                packet = TelemetryPacket.model_validate(raw_payload)
            except ValidationError as exc:
                await websocket.send_json(
                    {
                        "type": "validation_error",
                        "errors": exc.errors(include_url=False),
                    }
                )
                continue
            if packet.session_id != session_id or packet.device_id != device_id:
                await websocket.send_json(
                    {"type": "protocol_error", "message": "Session or device mismatch"}
                )
                continue
            response = await asyncio.to_thread(engine.predict, packet)
            try:
                await asyncio.to_thread(
                    repository.update,
                    session_id,
                    _live_session_updates(response, packet),
                )
            except Exception:
                logger.warning(
                    "WebSocket inference succeeded but live metrics update failed session_id=%s",
                    session_id,
                    exc_info=True,
                )
            await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("WebSocket telemetry failure session_id=%s", session_id)
        try:
            await websocket.send_json(
                {
                    "type": "server_error",
                    "message": "Telemetry processing is temporarily unavailable",
                }
            )
            await websocket.close(code=1011)
        except Exception:
            return
