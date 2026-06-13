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
    AuthPasswordRegister,
    AuthProfile,
    InferenceResponse,
    SessionCreate,
    SessionRecord,
    SessionSummary,
    TelemetryPacket,
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
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FocusFlow AI Dashboard</title>
  <style>
    :root { color-scheme: dark; --bg:#0f0f0f; --panel:#1a1a1a; --panel2:#141414; --text:#f5f5f5; --muted:#a1a1aa; --accent:#2ecc71; --border:#2b2b2b; --warn:#ef4444; }
    * { box-sizing:border-box; }
    body { margin:0; font-family: Inter, Segoe UI, Arial, sans-serif; background: linear-gradient(180deg,#111 0%, #0b0b0b 100%); color:var(--text); }
    .wrap { max-width: 1400px; margin: 0 auto; padding: 24px; }
    header { display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:20px; }
    h1 { margin:0; font-size: 2rem; }
    .muted { color: var(--muted); }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:16px; margin-bottom:16px; }
    .card { background: var(--panel); border:1px solid var(--border); border-radius:16px; padding:18px; }
    .kpi { font-size: 2rem; font-weight: 800; margin: 8px 0 0; }
    .sub { color: var(--muted); font-size: .92rem; }
    .two { display:grid; grid-template-columns: 1.3fr .7fr; gap:16px; }
    .wall { display:grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap:8px; margin-top:16px; }
    .tile { background:#0f172a; border:1px solid #243041; border-radius:12px; padding:10px; min-height:90px; }
    .tile strong { display:block; font-size:.88rem; margin-bottom:4px; }
    .tile .tiny { color: var(--muted); font-size: .78rem; line-height: 1.4; }
    table { width:100%; border-collapse: collapse; }
    th, td { text-align:left; padding:10px 8px; border-bottom:1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-weight:600; font-size:.85rem; text-transform: uppercase; letter-spacing:.06em; }
    .pill { display:inline-block; padding:4px 10px; border-radius:999px; background: #1f2937; border:1px solid #334155; }
    .pill.ok { background: rgba(46, 204, 113, .14); border-color: rgba(46, 204, 113, .32); color: #7ef0a9; }
    .pill.warn { background: rgba(239, 68, 68, .12); border-color: rgba(239, 68, 68, .28); color: #fca5a5; }
    .row { display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }
    code { background:#0b1220; padding:2px 6px; border-radius:8px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    @media (max-width: 1100px) { .grid, .two { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 760px) { .grid, .two { grid-template-columns: 1fr; } header { flex-direction: column; } }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>FocusFlow AI Server Dashboard</h1>
        <div class="muted">Live view of sessions, inference traffic, and backend status.</div>
      </div>
      <div class="row">
        <span id="ready-pill" class="pill">loading</span>
        <span id="repo-pill" class="pill"></span>
        <span id="event-pill" class="pill"></span>
      </div>
    </header>

    <section class="grid">
      <div class="card"><div class="sub">Recent sessions shown</div><div id="recent-count" class="kpi">0</div></div>
      <div class="card"><div class="sub">Active sessions</div><div id="active-count" class="kpi">0</div></div>
      <div class="card"><div class="sub">Completed</div><div id="completed-count" class="kpi">0</div></div>
      <div class="card"><div class="sub">API key configured</div><div id="api-key" class="kpi">No</div></div>
    </section>

    <section class="two">
      <div class="card">
        <div class="row" style="justify-content:space-between; align-items:flex-end; margin-top:0;">
          <div>
            <h2 style="margin:0;">Session history</h2>
            <div class="sub">Scrollable archive with search, result filters, and local delete controls.</div>
          </div>
          <div id="history-meta" class="pill">Showing 0</div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Device</th>
              <th>User</th>
              <th>Status</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Summary</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="session-rows">
            <tr><td colspan="8" class="muted">Loading...</td></tr>
          </tbody>
        </table>
      </div>
      <div class="card">
        <h2 style="margin-top:0;">Latest session</h2>
        <div id="latest-card" class="muted">No sessions yet.</div>
        <h2>Server notes</h2>
        <div class="muted">
          Open <code>/docs</code> for the API and use the desktop client to create sessions.
          This dashboard refreshes every 3 seconds.
        </div>
      </div>
    </section>

    <section class="card" style="margin-top:16px;">
      <h2 style="margin-top:0;">Camera wall preview</h2>
      <div class="muted">
        The server reads at most 100 recent session documents in one bounded
        query and caches the snapshot for 3 seconds.
      </div>
      <div id="camera-wall" class="wall"></div>
    </section>
  </div>
<script>
async function refreshDashboard() {
  const response = await fetch('/dashboard/api/summary?limit=100', { cache: 'no-store' });
  const data = await response.json();
  document.getElementById('ready-pill').textContent = data.ready ? 'READY' : 'NOT READY';
  document.getElementById('ready-pill').className = 'pill ' + (data.ready ? 'ok' : 'warn');
  document.getElementById('repo-pill').textContent = 'repo: ' + data.repository_backend;
  document.getElementById('event-pill').textContent = 'events: ' + data.event_backend;
  document.getElementById('recent-count').textContent = data.recent_count ?? 0;
  document.getElementById('active-count').textContent = data.active_sessions ?? 0;
  document.getElementById('completed-count').textContent = data.status_counts?.completed ?? 0;
  document.getElementById('api-key').textContent = data.api_key_configured ? 'Yes' : 'No';
  if (data.dashboard_error) {
    document.getElementById('latest-card').textContent = data.dashboard_error;
  }

  const latest = data.latest_session;
  if (latest) {
    const summary = latest.summary || {};
    document.getElementById('latest-card').innerHTML = `
      <div><strong>Session:</strong> <span class="mono">${latest.session_id || ''}</span></div>
      <div><strong>Device:</strong> <span class="mono">${latest.device_id || ''}</span></div>
      <div><strong>Status:</strong> ${latest.status || 'unknown'}</div>
      <div><strong>User:</strong> ${latest.user_display_name || latest.user_id || '-'}</div>
      <div><strong>Email:</strong> ${latest.user_email || '-'}</div>
      <div><strong>User ID:</strong> <span class="mono">${latest.user_id || '-'}</span></div>
      <div><strong>Live state:</strong> ${latest.live_metrics?.state || 'waiting'}</div>
      <div><strong>Live focus:</strong> ${latest.live_metrics?.focus_score != null ? (latest.live_metrics.focus_score * 100).toFixed(1) + '%' : '-'}</div>
      <div><strong>Face:</strong> ${latest.live_metrics?.face_found == null ? '-' : (latest.live_metrics.face_found ? 'found' : 'not found')}</div>
      <div><strong>Inference latency:</strong> ${latest.live_metrics?.latency_ms != null ? latest.live_metrics.latency_ms.toFixed(1) + ' ms' : '-'}</div>
      <div><strong>Average focus:</strong> ${((summary.average_focus || 0) * 100).toFixed(1)}%</div>
      <div><strong>Report:</strong> ${latest.report_status || 'n/a'}</div>
    `;
  } else {
    document.getElementById('latest-card').textContent = data.dashboard_error || 'No sessions yet.';
  }

  const rows = (data.recent_sessions || []).map(record => {
    const summary = record.summary || {};
    return `
      <tr>
        <td class="mono">${record.session_id || ''}</td>
        <td class="mono">${record.device_id || ''}</td>
        <td>${record.user_display_name || record.user_id || '-'}</td>
        <td>${record.status || 'unknown'}</td>
        <td class="mono">${(record.started_at || '').replace('T', ' ').slice(0, 19)}</td>
        <td class="mono">${(record.ended_at || '').replace('T', ' ').slice(0, 19) || '-'}</td>
        <td>${summary.completed ? 'completed' : (summary.average_focus != null ? ((summary.average_focus * 100).toFixed(1) + '% focus') : '-')}</td>
      </tr>
    `;
  }).join('');
  document.getElementById('session-rows').innerHTML = rows || '<tr><td colspan="8" class="muted">No sessions yet.</td></tr>';

  const tiles = (data.recent_sessions || []).slice(0, 24).map((record, index) => {
    const summary = record.summary || {};
    const live = record.live_metrics || {};
    const focusValue = live.focus_score ?? summary.average_focus;
    const focus = focusValue != null ? (focusValue * 100).toFixed(1) + '%' : '-';
    const status = (live.state || record.status || 'unknown').toUpperCase();
    const user = record.user_display_name || record.user_id || '-';
    return `
      <div class="tile">
        <strong>${String(index + 1).padStart(3, '0')} | ${status}</strong>
        <div class="tiny mono">${(record.device_id || '').slice(0, 16)}</div>
        <div class="tiny">focus: ${focus}</div>
        <div class="tiny">face: ${live.face_found == null ? '-' : (live.face_found ? 'found' : 'missing')}</div>
        <div class="tiny">latency: ${live.latency_ms != null ? live.latency_ms.toFixed(1) + ' ms' : '-'}</div>
        <div class="tiny">user: ${String(user).slice(0, 16)}</div>
      </div>
    `;
  }).join('');
  document.getElementById('camera-wall').innerHTML = tiles || '<div class="muted">No sessions yet.</div>';
}
refreshDashboard().catch(err => {
  document.getElementById('session-rows').innerHTML = '<tr><td colspan="8" class="muted">Dashboard load failed.</td></tr>';
  console.error(err);
});
</script>
  <script>
(function enhanceDashboard() {
  const style = document.createElement('style');
  style.textContent = `
    .scroll-box { max-height: 56vh; overflow: auto; border: 1px solid var(--border); border-radius: 12px; }
    .scroll-box table { min-width: 920px; }
    .scroll-box thead th { position: sticky; top: 0; z-index: 1; background: #171717; }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 0; align-items: end; }
    .control { display: flex; flex-direction: column; gap: 6px; min-width: 160px; }
    .control label { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }
    .control input, .control select {
      background: #0b1220; color: var(--text); border: 1px solid #334155; border-radius: 10px;
      padding: 10px 12px; font: inherit; outline: none;
    }
    .control input:focus, .control select:focus { border-color: #4ade80; box-shadow: 0 0 0 2px rgba(74, 222, 128, .12); }
    .history-actions { display:flex; flex-wrap:wrap; gap:8px; }
    .history-action {
      border: 1px solid #334155; border-radius: 10px; background: #0b1220; color: var(--text);
      padding: 10px 12px; font: inherit; cursor: pointer;
    }
    .history-action:hover { border-color: #4ade80; }
    .history-action.danger { border-color: rgba(239, 68, 68, .45); color: #fca5a5; }
    .history-action.danger:hover { border-color: rgba(248, 113, 113, .8); }
    .empty-state {
      display: none; margin-top: 12px; padding: 16px; text-align: center; color: var(--muted);
      border: 1px dashed var(--border); border-radius: 12px;
    }
    .tiles-wrap { max-height: 54vh; overflow: auto; padding-right: 4px; }
    .history-summary { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:12px; }
    .history-summary .pill { font-size: .84rem; }
    .table-muted { color: var(--muted); }
  `;
  document.head.appendChild(style);

  const storageKey = 'focusflow.dashboard.hiddenSessions';
  const state = { data: null, hiddenSessions: new Set() };
  const normalize = value => String(value ?? '').toLowerCase();

  function loadHiddenSessions() {
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter(Boolean).map(value => String(value)) : [];
    } catch {
      return [];
    }
  }

  function persistHiddenSessions() {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify([...state.hiddenSessions]));
    } catch {
      return;
    }
  }

  state.hiddenSessions = new Set(loadHiddenSessions());

  function hideSession(sessionId) {
    if (!sessionId) return;
    state.hiddenSessions.add(String(sessionId));
    persistHiddenSessions();
    if (state.data) render(state.data);
  }

  function resetHiddenSessions() {
    state.hiddenSessions.clear();
    persistHiddenSessions();
    if (state.data) render(state.data);
  }

  function wrapTable() {
    const rows = document.getElementById('session-rows');
    if (!rows) return;
    const table = rows.closest('table');
    if (table && !table.parentElement.classList.contains('scroll-box')) {
      const wrap = document.createElement('div');
      wrap.className = 'scroll-box';
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    }
    const wall = document.getElementById('camera-wall');
    if (wall) wall.classList.add('tiles-wrap');
  }

  function buildControls() {
    if (!document.getElementById('history-controls')) {
      const recentCard = document.getElementById('session-rows')?.closest('.card');
      const titleRow = recentCard?.querySelector('.row');
      if (recentCard && titleRow) {
        const controls = document.createElement('div');
        controls.id = 'history-controls';
        controls.className = 'controls';
        controls.innerHTML = `
          <div class="control" style="min-width:220px;">
            <label for="history-search">Search</label>
            <input id="history-search" type="search" placeholder="User, device, session...">
          </div>
          <div class="control">
            <label for="history-status">Result</label>
            <select id="history-status">
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
              <option value="unknown">Unknown</option>
            </select>
          </div>
          <div class="control">
            <label for="history-sort">Sort</label>
            <select id="history-sort">
              <option value="newest" selected>Newest</option>
              <option value="oldest">Oldest</option>
              <option value="focus">Focus</option>
              <option value="user">User</option>
              <option value="device">Device</option>
            </select>
          </div>
          <div class="control">
            <label for="history-limit">Count</label>
            <select id="history-limit">
              <option value="10">10</option>
              <option value="25" selected>25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
          <div class="history-actions">
            <button id="history-reset-hidden" class="history-action" type="button">Show all</button>
          </div>
        `;
        titleRow.insertAdjacentElement('afterend', controls);
        if (!document.getElementById('history-empty')) {
          const empty = document.createElement('div');
          empty.id = 'history-empty';
          empty.className = 'empty-state';
          empty.textContent = 'No sessions to show.';
          recentCard.appendChild(empty);
        }
      }
    }

    if (!document.getElementById('wall-controls')) {
      const wallCard = document.getElementById('camera-wall')?.closest('.card');
      const heading = wallCard?.querySelector('h2');
      if (wallCard && heading) {
        const controls = document.createElement('div');
        controls.id = 'wall-controls';
        controls.className = 'controls';
        controls.innerHTML = `
          <div class="control" style="min-width:220px;">
            <label for="wall-search">Search</label>
            <input id="wall-search" type="search" placeholder="User, device, session...">
          </div>
          <div class="control">
            <label for="wall-state">Result</label>
            <select id="wall-state">
              <option value="all">All</option>
              <option value="FOCUSED">Focused</option>
              <option value="DISTRACTED">Distracted</option>
              <option value="NO_FACE">No face</option>
              <option value="ACTIVE">Active</option>
            </select>
          </div>
          <div class="control">
            <label for="wall-limit">Count</label>
            <select id="wall-limit">
              <option value="12">12</option>
              <option value="24" selected>24</option>
              <option value="48">48</option>
              <option value="96">96</option>
            </select>
          </div>
        `;
        heading.insertAdjacentElement('afterend', controls);
        if (!document.getElementById('wall-empty')) {
          const empty = document.createElement('div');
          empty.id = 'wall-empty';
          empty.className = 'empty-state';
          empty.textContent = 'No sessions to show.';
          wallCard.appendChild(empty);
        }
      }
    }
  }

  function readHistoryFilters() {
    return {
      search: document.getElementById('history-search')?.value || '',
      status: document.getElementById('history-status')?.value || 'all',
      sort: document.getElementById('history-sort')?.value || 'newest',
      limit: Number(document.getElementById('history-limit')?.value || 25),
    };
  }

  function readWallFilters() {
    return {
      search: document.getElementById('wall-search')?.value || '',
      state: document.getElementById('wall-state')?.value || 'all',
      limit: Number(document.getElementById('wall-limit')?.value || 24),
    };
  }

  function matches(record, filter) {
    const search = normalize(filter.search);
    const recordState = normalize(record.live_metrics?.state || record.status || 'unknown');
    const recordStatus = normalize(record.status || record.live_metrics?.state || 'unknown');
    if (filter.status && filter.status !== 'all' && recordStatus !== normalize(filter.status)) return false;
    if (filter.state && filter.state !== 'all' && recordState !== normalize(filter.state)) return false;
    if (!search) return true;
    const haystack = [
      record.session_id,
      record.device_id,
      record.user_display_name,
      record.user_username,
      record.user_email,
      record.user_id,
      record.status,
      record.live_metrics?.state,
    ].map(normalize).join(' | ');
    return haystack.includes(search);
  }

  function sortRecords(records, sortKey) {
    const focusValue = record => {
      const summary = record.summary || {};
      const live = record.live_metrics || {};
      return Number(live.focus_score ?? summary.average_focus ?? -1);
    };
    const byText = key => [...records].sort((a, b) => normalize(a?.[key]).localeCompare(normalize(b?.[key])));
    const sorted = [...records];
    if (sortKey === 'oldest') {
      return sorted.sort((a, b) => normalize(a.started_at).localeCompare(normalize(b.started_at)));
    }
    if (sortKey === 'focus') {
      return sorted.sort((a, b) => focusValue(b) - focusValue(a));
    }
    if (sortKey === 'user') {
      return byText('user_display_name');
    }
    if (sortKey === 'device') {
      return byText('device_id');
    }
    return sorted.sort((a, b) => normalize(b.started_at).localeCompare(normalize(a.started_at)));
  }

  function render(data) {
    state.data = data;
    wrapTable();
    buildControls();
    const recent = Array.isArray(data.recent_sessions) ? data.recent_sessions : [];
    const visibleRecent = recent.filter(record => !state.hiddenSessions.has(String(record.session_id || '')));
    const latestCard = document.getElementById('latest-card');
    const recentRows = document.getElementById('session-rows');
    const recentEmpty = document.getElementById('history-empty');
    const wall = document.getElementById('camera-wall');
    const wallEmpty = document.getElementById('wall-empty');
    const historyMeta = document.getElementById('history-meta');

    if (latestCard) {
      const latest = visibleRecent[0] || (recent.length ? null : data.latest_session);
      if (!latest) {
        latestCard.textContent = recent.length
          ? 'All visible sessions are hidden in your browser.'
          : (data.dashboard_error || 'No sessions yet.');
      } else {
        const summary = latest.summary || {};
        latestCard.innerHTML = `
          <div><strong>Session:</strong> <span class="mono">${latest.session_id || ''}</span></div>
          <div><strong>Device:</strong> <span class="mono">${latest.device_id || ''}</span></div>
          <div><strong>Status:</strong> ${latest.status || 'unknown'}</div>
          <div><strong>User:</strong> ${latest.user_display_name || latest.user_id || '-'}</div>
          <div><strong>Email:</strong> ${latest.user_email || '-'}</div>
          <div><strong>User ID:</strong> <span class="mono">${latest.user_id || '-'}</span></div>
          <div><strong>Live state:</strong> ${latest.live_metrics?.state || 'waiting'}</div>
          <div><strong>Live focus:</strong> ${latest.live_metrics?.focus_score != null ? (latest.live_metrics.focus_score * 100).toFixed(1) + '%' : '-'}</div>
          <div><strong>Face:</strong> ${latest.live_metrics?.face_found == null ? '-' : (latest.live_metrics.face_found ? 'found' : 'not found')}</div>
          <div><strong>Inference latency:</strong> ${latest.live_metrics?.latency_ms != null ? latest.live_metrics.latency_ms.toFixed(1) + ' ms' : '-'}</div>
          <div><strong>Average focus:</strong> ${((summary.average_focus || 0) * 100).toFixed(1)}%</div>
          <div><strong>Report:</strong> ${latest.report_status || 'n/a'}</div>
        `;
      }
    }

    if (!visibleRecent.length) {
      if (recentRows) recentRows.innerHTML = '';
      if (wall) wall.innerHTML = '';
      if (recentEmpty) {
        recentEmpty.style.display = 'block';
        recentEmpty.textContent = recent.length ? 'All visible sessions are hidden in your browser.' : 'No sessions to show.';
      }
      if (wallEmpty) {
        wallEmpty.style.display = 'block';
        wallEmpty.textContent = recent.length ? 'All visible sessions are hidden in your browser.' : 'No sessions to show.';
      }
      if (historyMeta) {
        historyMeta.textContent = recent.length
          ? `Showing 0 of ${recent.length}`
          : 'Showing 0';
      }
      return;
    }

    const historyFilter = readHistoryFilters();
    const wallFilter = readWallFilters();
    const filteredRecent = sortRecords(
      visibleRecent.filter(record => matches(record, { ...historyFilter, state: historyFilter.status })),
      historyFilter.sort,
    ).slice(0, historyFilter.limit);
    const filteredWall = visibleRecent.filter(record => matches(record, wallFilter)).slice(0, wallFilter.limit);
    if (historyMeta) {
      historyMeta.textContent = `Showing ${filteredRecent.length} of ${visibleRecent.length}`;
    }

    if (recentRows) {
      if (!filteredRecent.length) {
        recentRows.innerHTML = '';
        if (recentEmpty) {
          recentEmpty.style.display = 'block';
          recentEmpty.textContent = visibleRecent.length ? 'No sessions match your filters.' : 'No sessions to show.';
        }
      } else {
        if (recentEmpty) recentEmpty.style.display = 'none';
        recentRows.innerHTML = filteredRecent.map(record => {
          const summary = record.summary || {};
          const live = record.live_metrics || {};
          const stateLabel = (live.state || record.status || 'unknown').toLowerCase();
          return `
            <tr>
              <td class="mono">${record.session_id || ''}</td>
              <td class="mono">${record.device_id || ''}</td>
              <td>${record.user_display_name || record.user_id || '-'}</td>
              <td>${stateLabel}</td>
              <td class="mono">${(record.started_at || '').replace('T', ' ').slice(0, 19)}</td>
              <td class="mono">${(record.ended_at || '').replace('T', ' ').slice(0, 19) || '-'}</td>
              <td>${summary.completed ? 'completed' : (summary.average_focus != null ? ((summary.average_focus * 100).toFixed(1) + '% focus') : '-')}</td>
              <td>
                <button class="history-action danger" type="button" data-history-delete="${record.session_id || ''}">Delete</button>
              </td>
            </tr>
          `;
        }).join('');
      }
    }

    if (wall) {
      if (!filteredWall.length) {
        wall.innerHTML = '';
        if (wallEmpty) {
          wallEmpty.style.display = 'block';
          wallEmpty.textContent = visibleRecent.length ? 'No sessions match your filters.' : 'No sessions to show.';
        }
      } else {
        if (wallEmpty) wallEmpty.style.display = 'none';
        wall.innerHTML = filteredWall.map((record, index) => {
          const summary = record.summary || {};
          const live = record.live_metrics || {};
          const focusValue = live.focus_score ?? summary.average_focus;
          const focus = focusValue != null ? (focusValue * 100).toFixed(1) + '%' : '-';
          const status = (live.state || record.status || 'unknown').toUpperCase();
          const user = record.user_display_name || record.user_id || '-';
          return `
            <div class="tile">
              <strong>${String(index + 1).padStart(3, '0')} | ${status}</strong>
              <div class="tiny mono">${(record.device_id || '').slice(0, 16)}</div>
              <div class="tiny">focus: ${focus}</div>
              <div class="tiny">face: ${live.face_found == null ? '-' : (live.face_found ? 'found' : 'missing')}</div>
              <div class="tiny">latency: ${live.latency_ms != null ? live.latency_ms.toFixed(1) + ' ms' : '-'}</div>
              <div class="tiny">user: ${String(user).slice(0, 16)}</div>
            </div>
          `;
        }).join('');
      }
    }
  }

  function bind() {
    ['history-search', 'history-status', 'history-sort', 'history-limit', 'wall-search', 'wall-state', 'wall-limit'].forEach(id => {
      const el = document.getElementById(id);
      if (!el || el.dataset.bound === '1') return;
      el.dataset.bound = '1';
      el.addEventListener('input', () => state.data && render(state.data));
      el.addEventListener('change', () => state.data && render(state.data));
    });
    const resetHidden = document.getElementById('history-reset-hidden');
    if (resetHidden && resetHidden.dataset.bound !== '1') {
      resetHidden.dataset.bound = '1';
      resetHidden.addEventListener('click', () => resetHiddenSessions());
    }
    const rows = document.getElementById('session-rows');
    if (rows && rows.dataset.bound !== '1') {
      rows.dataset.bound = '1';
      rows.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target.closest('[data-history-delete]') : null;
        if (!target) return;
        const sessionId = target.getAttribute('data-history-delete');
        if (!sessionId) return;
        const apiKey = window.prompt('Enter the FocusFlow API key to delete this session:');
        if (!apiKey) return;
        fetch(`/dashboard/api/sessions/${encodeURIComponent(sessionId)}`, {
          method: 'DELETE',
          headers: { 'X-API-Key': apiKey },
        })
          .then(response => {
            if (!response.ok) {
              throw new Error(`Delete failed with HTTP ${response.status}`);
            }
            return response.json();
          })
          .then(() => {
            hideSession(sessionId);
          })
          .catch(error => {
            window.alert(error.message || 'Delete failed');
          });
      });
    }
  }

  window.refreshDashboard = async function refreshDashboardEnhanced() {
    const response = await fetch('/dashboard/api/summary?limit=100', { cache: 'no-store' });
    const data = await response.json();
    document.getElementById('ready-pill').textContent = data.ready ? 'READY' : 'NOT READY';
    document.getElementById('ready-pill').className = 'pill ' + (data.ready ? 'ok' : 'warn');
    document.getElementById('repo-pill').textContent = 'repo: ' + data.repository_backend;
    document.getElementById('event-pill').textContent = 'events: ' + data.event_backend;
    document.getElementById('recent-count').textContent = data.recent_count ?? 0;
    document.getElementById('active-count').textContent = data.active_sessions ?? 0;
    document.getElementById('completed-count').textContent = data.status_counts?.completed ?? 0;
    document.getElementById('api-key').textContent = data.api_key_configured ? 'Yes' : 'No';
    render(data);
  };

  bind();
  window.refreshDashboard().catch(err => {
    console.error(err);
    const rows = document.getElementById('session-rows');
    const wall = document.getElementById('camera-wall');
    if (rows) rows.innerHTML = '';
    if (wall) wall.innerHTML = '';
  });
  setInterval(() => window.refreshDashboard().catch(console.error), 3000);
})();
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
