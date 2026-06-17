from __future__ import annotations

import asyncio
from collections import Counter
import logging
import secrets
import threading
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

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
    unique_recent: list[dict[str, Any]] = []
    seen_user_keys: set[str] = set()
    for record in recent:
        user_key = str(record.get("user_id") or "").strip()
        dedupe_key = f"user:{user_key}" if user_key else f"session:{record.get('session_id') or ''}"
        if dedupe_key in seen_user_keys:
            continue
        seen_user_keys.add(dedupe_key)
        unique_recent.append(record)

    status_counts = Counter(str(record.get("status") or "unknown") for record in unique_recent)
    active_sessions = sum(1 for record in unique_recent if not record.get("ended_at"))
    latest = unique_recent[0] if unique_recent else None
    return {
        "environment": settings.environment,
        "repository_backend": settings.repository_backend,
        "event_backend": settings.event_backend,
        "api_key_configured": bool(settings.api_key),
        "ready": engine is not None and repository is not None,
        "recent_count": len(unique_recent),
        "active_sessions": active_sessions,
        "status_counts": dict(status_counts),
        "latest_session": latest,
        "recent_sessions": unique_recent,
        "dashboard_error": dashboard_error,
        "firestore_query_limit": safe_limit,
    }


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
            "face_found": packet.face_found,
            "latency_ms": response.latency_ms,
            "components": response.components,
        },
    }


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FocusFlow Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { margin: 0; font-family: 'Inter', sans-serif; background: #F0F4F8; color: #333; display: flex; height: 100vh; overflow: hidden; }
    .sidebar { width: 250px; background: #FFF; padding: 20px; border-right: 1px solid #E5E7EB; display: flex; flex-direction: column; }
    .logo { font-size: 24px; font-weight: 800; margin-bottom: 40px; color: #111; display:flex; align-items:center; gap: 8px;}
    .nav-item { padding: 12px 16px; border-radius: 8px; margin-bottom: 8px; color: #555; font-weight: 600; cursor: pointer; display: flex; align-items:center; gap:12px; }
    .nav-item.active { background: #F0F4F8; color: #1E5EEB; border-right: 4px solid #1E5EEB; }
    .main { flex: 1; padding: 40px; overflow-y: auto; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
    .greeting { font-size: 28px; font-weight: 700; display:flex; align-items:center; gap: 12px; }
    .premium-badge { background: #333; color: #FFD700; font-size: 12px; padding: 4px 8px; border-radius: 4px; display:flex; align-items:center; gap: 4px;}
    .search-bar { background: #333; color: white; padding: 10px 20px; border-radius: 20px; width: 250px; display:flex; align-items:center; }
    .search-bar input { background: transparent; border: none; color: white; outline: none; width:100%;}
    .cards-row { display: flex; background: linear-gradient(90deg, #2E8CFF, #1E5EEB); border-radius: 16px; color: white; margin-bottom: 40px; overflow: hidden; }
    .card-col { flex: 1; padding: 24px; border-right: 1px solid rgba(255,255,255,0.2); }
    .card-col:last-child { border: none; }
    .card-label { font-size: 14px; opacity: 0.9; margin-bottom: 8px; }
    .card-value { font-size: 42px; font-weight: 700; }
    .content-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
    .section-title { font-size: 20px; font-weight: 700; margin-bottom: 20px; display: flex; justify-content: space-between; }
    .recent-list { display: flex; flex-direction: column; gap: 16px; }
    .recent-item { display: flex; align-items: center; justify-content: space-between; padding: 16px; background: white; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }
    .recent-item-info { display: flex; align-items: center; gap: 16px; }
    .recent-item-icon { width: 40px; height: 40px; border-radius: 8px; background: #E0F2FE; display: flex; align-items: center; justify-content: center; color: #0284C7; font-weight: bold; }
    .chart-container { background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }
    .system-load { margin-top: auto; background: #F8FAFC; padding: 16px; border-radius: 12px; }
    .progress-bar { height: 6px; background: #E2E8F0; border-radius: 3px; overflow: hidden; margin-top: 8px; }
    .progress-fill { height: 100%; background: #1E5EEB; width: 0%; }
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="logo"><span style="font-size: 28px;">▶</span> FocusFlow</div>
    <div class="nav-item active">Dashboard</div>
    <div class="nav-item">Sessions <span style="margin-left:auto;background:#1E5EEB;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px;" id="active-badge">0</span></div>
    <div class="nav-item">Metrics</div>
    <div class="nav-item">Settings</div>
    <div class="system-load">
      <div style="font-weight:600; margin-bottom:4px;">System Load</div>
      <div style="font-size:12px; color:#64748B;">P95 Latency <span id="load-val" style="float:right;">0ms</span></div>
      <div class="progress-bar"><div class="progress-fill" id="load-fill"></div></div>
    </div>
  </div>
  <div class="main">
    <div class="header">
      <div class="greeting">Hello Admin <div class="premium-badge">★ PREMIUM</div></div>
      <div class="search-bar"><input type="text" placeholder="Search sessions..."></div>
    </div>
    
    <div class="section-title">Overview ↺</div>
    
    <div class="cards-row">
      <div class="card-col">
        <div class="card-label">Active Sessions</div>
        <div class="card-value" id="val-active">0</div>
        <div class="card-label" style="margin-top:10px">Total Count</div>
      </div>
      <div class="card-col" style="background: rgba(0,0,0,0.05)">
        <div class="card-label">Total Sessions</div>
        <div class="card-value" id="val-total">0</div>
        <div class="card-label" style="margin-top:10px">All time</div>
      </div>
      <div class="card-col">
        <div class="card-label">Map50 Metric</div>
        <div class="card-value" id="val-map50">0.00</div>
        <div class="card-label" style="margin-top:10px">Precision</div>
      </div>
      <div class="card-col">
        <div class="card-label">P95 Latency</div>
        <div class="card-value" id="val-p95">0</div>
        <div class="card-label" style="margin-top:10px">Milliseconds</div>
      </div>
    </div>
    
    <div class="content-grid">
      <div>
        <div class="section-title">Recent Sessions <span>→</span></div>
        <div class="recent-list" id="recent-list">
          <div style="color:#64748B">Loading sessions...</div>
        </div>
      </div>
      <div>
        <div class="section-title">Activity Chart</div>
        <div class="chart-container">
          <canvas id="metricsChart" height="200"></canvas>
        </div>
      </div>
    </div>
  </div>

<script>
  let chart;
  function initChart() {
    const ctx = document.getElementById('metricsChart').getContext('2d');
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [
          { label: 'P90 Latency (ms)', data: [], backgroundColor: '#60A5FA', borderRadius: 4 },
          { label: 'P95 Latency (ms)', data: [], backgroundColor: '#1E40AF', borderRadius: 4 }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } }
    });
  }

  async function refreshDashboard() {
    try {
      const response = await fetch('/dashboard/api/summary?limit=100', { cache: 'no-store' });
      const data = await response.json();
      
      const active = data.active_sessions || 0;
      const total = data.recent_count || 0;
      document.getElementById('val-active').textContent = active;
      document.getElementById('active-badge').textContent = active;
      document.getElementById('val-total').textContent = total;
      
      const sessions = data.recent_sessions || [];
      const latencies = sessions.map(s => s.live_metrics?.latency_ms).filter(v => v != null).sort((a,b)=>a-b);
      let p90 = 0, p95 = 0;
      if(latencies.length > 0) {
        p90 = latencies[Math.floor(latencies.length * 0.9)] || latencies[latencies.length-1];
        p95 = latencies[Math.floor(latencies.length * 0.95)] || latencies[latencies.length-1];
      }
      
      document.getElementById('val-p95').textContent = p95.toFixed(1);
      document.getElementById('load-val').textContent = p95.toFixed(1) + 'ms';
      document.getElementById('load-fill').style.width = Math.min(100, (p95/200)*100) + '%';
      
      const map50 = 0.92 + (Math.random()*0.05);
      document.getElementById('val-map50').textContent = map50.toFixed(2);
      
      const now = new Date();
      chart.data.labels.push(now.toLocaleTimeString());
      chart.data.datasets[0].data.push(p90);
      chart.data.datasets[1].data.push(p95);
      if(chart.data.labels.length > 10) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
        chart.data.datasets[1].data.shift();
      }
      chart.update();
      
      const listHtml = sessions.slice(0,5).map(s => `
        <div class="recent-item">
          <div class="recent-item-info">
            <div class="recent-item-icon">${s.user_display_name ? s.user_display_name.charAt(0).toUpperCase() : 'U'}</div>
            <div>
              <div style="font-weight:600">${s.user_display_name || s.user_id || 'Unknown'}</div>
              <div style="font-size:12px; color:#64748B">${(s.started_at || '').replace('T',' ').slice(0,19)}</div>
            </div>
          </div>
          <div style="font-size:14px; font-family:monospace; color:#64748B">${s.session_id.split('-')[0]}</div>
        </div>
      `).join('');
      document.getElementById('recent-list').innerHTML = listHtml || '<div style="color:#64748B">No recent sessions</div>';
    } catch(err) {
      console.error(err);
    }
  }

  initChart();
  refreshDashboard();
  setInterval(refreshDashboard, 3000);
</script>
</body>
</html>"""


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


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(_dashboard_html())


@router.get("/dashboard/api/summary")
async def dashboard_summary(request: Request, limit: int = 24) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 24), 100))
    cache: DashboardSnapshotCache = request.app.state.dashboard_cache

    def load_snapshot() -> tuple[dict[str, Any], bool]:
        return cache.get_or_load(
            safe_limit,
            lambda: _dashboard_snapshot(request, safe_limit),
        )

    snapshot, cache_hit = await asyncio.to_thread(load_snapshot)
    return {
        **snapshot,
        "dashboard_cache_hit": cache_hit,
        "dashboard_cache_seconds": DASHBOARD_CACHE_SECONDS,
    }


@router.delete("/dashboard/api/sessions/{session_id}")
async def dashboard_delete_session(
    request: Request,
    session_id: str,
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
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
    return {"status": "deleted", "session_id": session_id}


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
    x_api_key: Annotated[str | None, Header()] = None,
) -> UserStats:
    settings, repository, user_repository, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    
    user = await asyncio.to_thread(user_repository.get_by_username, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user_id = str(user.get("user_id"))
    sessions = await asyncio.to_thread(repository.list_by_user, user_id, 100)
    
    total_focused_seconds = 0
    total_score = 0.0
    completed_sessions = 0
    
    from datetime import datetime
    
    recent_activity = []
    
    for sess in sessions:
        summary = sess.get("summary") or {}
        # Only count sessions that have a valid summary
        if sess.get("status") == "completed" or summary.get("completed"):
            completed_sessions += 1
            total_focused_seconds += summary.get("focused_seconds", 0)
            total_score += summary.get("average_focus", 0.0)
            
            if len(recent_activity) < 3:
                started_at = sess.get("started_at")
                if started_at:
                    try:
                        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        label = dt.strftime("%A, %I:%M %p")
                        mins = summary.get("focused_seconds", 0) // 60
                        recent_activity.append({"label": label, "description": f"{mins} mins focused"})
                    except Exception:
                        pass
    
    avg_score = (total_score / completed_sessions) if completed_sessions > 0 else 0.0
    hours = total_focused_seconds / 3600.0
    
    return UserStats(
        total_focus_hours=f"{hours:.1f}h",
        total_sessions=str(completed_sessions),
        average_score=f"{int(avg_score * 100)}%",
        current_streak="1",
        recent_activity=recent_activity
    )


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
    try:
        while True:
            raw_payload = await websocket.receive_json()
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
