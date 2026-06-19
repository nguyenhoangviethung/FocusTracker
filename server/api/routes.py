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
    api_key = settings.api_key or ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FocusFlow Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ margin: 0; font-family: 'Inter', sans-serif; background: #F0F4F8; color: #333; display: flex; height: 100vh; overflow: hidden; }}
    .sidebar {{ width: 250px; background: #FFF; padding: 20px; border-right: 1px solid #E5E7EB; display: flex; flex-direction: column; }}
    .logo {{ font-size: 24px; font-weight: 800; margin-bottom: 40px; color: #111; display:flex; align-items:center; gap: 8px;}}
    .nav-item {{ padding: 12px 16px; border-radius: 8px; margin-bottom: 8px; color: #555; font-weight: 600; cursor: pointer; display: flex; align-items:center; gap:12px; }}
    .nav-item.active {{ background: #F0F4F8; color: #1E5EEB; border-right: 4px solid #1E5EEB; }}
    .main {{ flex: 1; padding: 40px; overflow-y: auto; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }}
    .greeting {{ font-size: 28px; font-weight: 700; display:flex; align-items:center; gap: 12px; }}
    .premium-badge {{ background: #333; color: #FFD700; font-size: 12px; padding: 4px 8px; border-radius: 4px; display:flex; align-items:center; gap: 4px;}}
    .search-bar {{ background: #333; color: white; padding: 10px 20px; border-radius: 20px; width: 250px; display:flex; align-items:center; }}
    .search-bar input {{ background: transparent; border: none; color: white; outline: none; width:100%;}}
    .cards-row {{ display: flex; background: linear-gradient(90deg, #2E8CFF, #1E5EEB); border-radius: 16px; color: white; margin-bottom: 40px; overflow: hidden; }}
    .card-col {{ flex: 1; padding: 24px; border-right: 1px solid rgba(255,255,255,0.2); }}
    .card-col:last-child {{ border: none; }}
    .card-label {{ font-size: 14px; opacity: 0.9; margin-bottom: 8px; }}
    .card-value {{ font-size: 42px; font-weight: 700; }}
    .content-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }}
    .section-title {{ font-size: 20px; font-weight: 700; margin-bottom: 20px; display: flex; justify-content: space-between; }}
    .recent-list {{ display: flex; flex-direction: column; gap: 16px; }}
    .recent-item {{ display: flex; align-items: center; justify-content: space-between; padding: 16px; background: white; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }}
    .recent-item-info {{ display: flex; align-items: center; gap: 16px; }}
    .recent-item-icon {{ width: 40px; height: 40px; border-radius: 8px; background: #E0F2FE; display: flex; align-items: center; justify-content: center; color: #0284C7; font-weight: bold; }}
    .chart-container {{ background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); }}
    .system-load {{ margin-top: auto; background: #F8FAFC; padding: 16px; border-radius: 12px; }}
    .progress-bar {{ height: 6px; background: #E2E8F0; border-radius: 3px; overflow: hidden; margin-top: 8px; }}
    .progress-fill {{ height: 100%; background: #1E5EEB; width: 0%; }}
    
    table th {{ padding: 12px 16px; border-bottom: 2px solid #E5E7EB; color: #64748B; font-weight: 600; text-align: left; }}
    table td {{ padding: 16px; border-bottom: 1px solid #F1F5F9; color: #475569; }}
    table tr:hover {{ background: #F8FAFC; }}
  </style>
</head>
<body>
  <div class="sidebar">
    <div class="logo"><span style="font-size: 28px;">▶</span> FocusFlow</div>
    <div class="nav-item active" onclick="switchTab('dashboard')">Dashboard</div>
    <div class="nav-item" onclick="switchTab('sessions')">Sessions <span style="margin-left:auto;background:#1E5EEB;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;font-size:12px;" id="active-badge">0</span></div>
    <div class="nav-item" onclick="switchTab('metrics')">Metrics</div>
    <div class="nav-item" onclick="switchTab('settings')">Settings</div>
    <div class="system-load">
      <div style="font-weight:600; margin-bottom:4px;">System Load</div>
      <div style="font-size:12px; color:#64748B;">P95 Latency <span id="load-val" style="float:right;">0ms</span></div>
      <div class="progress-bar"><div class="progress-fill" id="load-fill"></div></div>
    </div>
  </div>
  <div class="main">
    <div class="header">
      <div class="greeting">Hello Admin <div class="premium-badge">★ PREMIUM</div></div>
      <div class="search-bar"><input type="text" id="search-input" placeholder="Search sessions..." oninput="filterSessions()"></div>
    </div>
    
    <!-- Tab 1: Dashboard -->
    <div id="tab-dashboard" class="tab-content">
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
    
    <!-- Tab 2: Sessions -->
    <div id="tab-sessions" class="tab-content" style="display: none;">
      <div class="section-title">All Sessions List</div>
      
      <!-- Session controls, filters & operations -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; gap: 16px; flex-wrap: wrap;">
        <!-- Filters tab design -->
        <div style="display: flex; gap: 4px; background: #E2E8F0; padding: 4px; border-radius: 8px;">
          <button id="filter-all" onclick="setStatusFilter('all')" style="border: none; background: #FFF; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; color: #1E5EEB; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: all 0.2s;">All</button>
          <button id="filter-active" onclick="setStatusFilter('active')" style="border: none; background: transparent; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; color: #64748B; transition: all 0.2s;">Active</button>
          <button id="filter-completed" onclick="setStatusFilter('completed')" style="border: none; background: transparent; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; color: #64748B; transition: all 0.2s;">Completed</button>
        </div>
        
        <!-- Quick clean up tools & actions -->
        <div style="display: flex; gap: 12px; align-items: center;">
          <button id="batch-delete-btn" onclick="batchDeleteSelected()" style="display: none; background: #EF4444; color: white; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; align-items: center; gap: 6px; box-shadow: 0 2px 5px rgba(239, 68, 68, 0.2);">
            Delete Selected (<span id="selected-count">0</span>)
          </button>
          <button onclick="clearStaleSessions()" style="background: #F59E0B1A; color: #D97706; border: 1px solid #F59E0B33; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.2s;">
            Clear Stale Active (>1h)
          </button>
          <button onclick="clearAllSessions()" style="background: #EF44441A; color: #EF4444; border: 1px solid #EF444433; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; transition: all 0.2s;">
            Clear All
          </button>
        </div>
      </div>

      <div style="background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left;" id="sessions-table">
          <thead>
            <tr style="border-bottom: 2px solid #E5E7EB; color: #64748B; font-weight: 600;">
              <th style="padding: 12px 16px; width: 40px;"><input type="checkbox" id="select-all-checkbox" onchange="toggleSelectAll(this)" style="cursor: pointer; width: 16px; height: 16px;"></th>
              <th style="padding: 12px 16px;">User</th>
              <th style="padding: 12px 16px;">Session ID</th>
              <th style="padding: 12px 16px;">Device ID</th>
              <th style="padding: 12px 16px;">Status</th>
              <th style="padding: 12px 16px;">Live Focus</th>
              <th style="padding: 12px 16px;">Latency</th>
              <th style="padding: 12px 16px;">Duration</th>
              <th style="padding: 12px 16px; text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody id="sessions-table-body">
            <tr>
              <td colspan="9" style="padding: 24px; text-align: center; color: #64748B;">Loading sessions...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>


    <!-- Tab 3: Metrics (Simulation Info) -->
    <div id="tab-metrics" class="tab-content" style="display: none;">
      <div class="section-title">Load Simulation & Metrics</div>
      <div class="content-grid" style="grid-template-columns: 1fr 2fr;">
        <!-- Control panel -->
        <div style="background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); display: flex; flex-direction: column; gap: 16px;">
          <div style="font-size: 16px; font-weight: 600;">100-User Demo Scenario</div>
          <div style="font-size: 14px; color: #64748B; line-height: 1.5;">
            To simulate 100 concurrent clients sending real-time face feature sequences at 1 Hz, run the demo shell script from your workspace terminal:
          </div>
          <div style="background: #F1F5F9; padding: 12px 16px; border-radius: 8px; font-family: monospace; font-size: 13px; color: #1E293B; border: 1px solid #E2E8F0; word-break: break-all;">
            ./scripts/run_demo_100_users.sh
          </div>
          <div style="font-size: 13px; color: #64748B; line-height: 1.5;">
            This script selects focus/distracted video segments, generates user profiles, and replays telemetry packets to verify your GCP or local deployment's concurrency performance.
          </div>
        </div>

        <!-- Metric details -->
        <div style="background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); display: flex; flex-direction: column; gap: 16px;">
          <div style="font-size: 16px; font-weight: 600;">Focus Level Distribution</div>
          <div style="height: 250px; position: relative;">
            <canvas id="focusDistChart" height="250"></canvas>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 4: Settings -->
    <div id="tab-settings" class="tab-content" style="display: none;">
      <div class="section-title">Server Environments & Configurations</div>
      <div style="background: white; padding: 24px; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.02); display: flex; flex-direction: column; gap: 16px;">
        <div class="settings-row" style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #F1F5F9;">
          <span style="font-weight: 600; color: #475569;">Environment Mode</span>
          <span style="text-transform: uppercase; font-family: monospace; font-weight: bold; padding: 2px 8px; border-radius: 4px; background: #E2E8F0;" id="cfg-env">-</span>
        </div>
        <div class="settings-row" style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #F1F5F9;">
          <span style="font-weight: 600; color: #475569;">Session Repository Backend</span>
          <span style="text-transform: uppercase; font-family: monospace; font-weight: bold; padding: 2px 8px; border-radius: 4px; background: #E2E8F0;" id="cfg-repo">-</span>
        </div>
        <div class="settings-row" style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #F1F5F9;">
          <span style="font-weight: 600; color: #475569;">Event Messaging Backend</span>
          <span style="text-transform: uppercase; font-family: monospace; font-weight: bold; padding: 2px 8px; border-radius: 4px; background: #E2E8F0;" id="cfg-event">-</span>
        </div>
        <div class="settings-row" style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #F1F5F9;">
          <span style="font-weight: 600; color: #475569;">X-API-Key Security Guard</span>
          <span style="font-family: monospace; font-weight: bold; color: #22C55E;" id="cfg-key">-</span>
        </div>
        <div class="settings-row" style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #F1F5F9;">
          <span style="font-weight: 600; color: #475569;">4-Class XGBoost Runtime Engine</span>
          <span style="font-family: monospace; color: #64748B;">fixed_triple_xgb_fusion [CPU, XGBoost]</span>
        </div>
      </div>
    </div>
  </div>

<script>
  let chart;
  let distChart;
  const API_KEY = "{api_key}";
  let allSessions = [];
  let currentTab = 'dashboard';

  function initCharts() {{
    const ctx = document.getElementById('metricsChart').getContext('2d');
    chart = new Chart(ctx, {{
      type: 'bar',
      data: {{
        labels: [],
        datasets: [
          {{ label: 'P90 Latency (ms)', data: [], backgroundColor: '#60A5FA', borderRadius: 4 }},
          {{ label: 'P95 Latency (ms)', data: [], backgroundColor: '#1E40AF', borderRadius: 4 }}
        ]
      }},
      options: {{ responsive: true, maintainAspectRatio: false, scales: {{ y: {{ beginAtZero: true }} }} }}
    }});

    const ctxDist = document.getElementById('focusDistChart').getContext('2d');
    distChart = new Chart(ctxDist, {{
      type: 'doughnut',
      data: {{
        labels: ['Focused (>= 54%)', 'Distracted (< 54%)'],
        datasets: [{{
          data: [0, 0],
          backgroundColor: ['#10B981', '#EF4444'],
          borderWidth: 0
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom' }}
        }}
      }}
    }});
  }}

  function switchTab(tabId) {{
    currentTab = tabId;
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => {{
      tab.style.display = 'none';
    }});
    document.getElementById('tab-' + tabId).style.display = 'block';
    
    const navItems = document.querySelectorAll('.sidebar .nav-item');
    navItems.forEach(item => {{
      item.classList.remove('active');
    }});
    
    const clickedItem = Array.from(navItems).find(item => item.textContent.toLowerCase().includes(tabId));
    if (clickedItem) clickedItem.classList.add('active');
  }}

  let selectedSessions = new Set();
  let statusFilter = 'all';

  function setStatusFilter(filter) {{
    statusFilter = filter;
    
    // Update active tab buttons visual style
    const filters = ['all', 'active', 'completed'];
    filters.forEach(f => {{
      const btn = document.getElementById('filter-' + f);
      if (f === filter) {{
        btn.style.background = '#FFF';
        btn.style.color = '#1E5EEB';
        btn.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
      }} else {{
        btn.style.background = 'transparent';
        btn.style.color = '#64748B';
        btn.style.boxShadow = 'none';
      }}
    }});
    
    filterSessions();
  }}

  function updateSessionsTable(sessions) {{
    allSessions = sessions;
    
    // Clean up selectedSessions to remove IDs that are no longer present
    const validIds = new Set(sessions.map(s => s.session_id));
    for (let id of selectedSessions) {{
      if (!validIds.has(id)) {{
        selectedSessions.delete(id);
      }}
    }}
    
    filterSessions();
    updateBatchDeleteButton();
  }}

  function filterSessions() {{
    const query = (document.getElementById('search-input').value || '').toLowerCase().trim();
    const tbody = document.getElementById('sessions-table-body');
    
    const filtered = allSessions.filter(s => {{
      const user = (s.user_display_name || s.user_id || '').toLowerCase();
      const sid = (s.session_id || '').toLowerCase();
      const did = (s.device_id || '').toLowerCase();
      const matchesSearch = user.includes(query) || sid.includes(query) || did.includes(query);
      
      const status = s.ended_at ? 'completed' : 'active';
      const matchesStatus = statusFilter === 'all' || status === statusFilter;
      
      return matchesSearch && matchesStatus;
    }});

    // Update Select All checkbox state based on filtered rows
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    if (selectAllCheckbox) {{
      const allChecked = filtered.length > 0 && filtered.every(s => selectedSessions.has(s.session_id));
      selectAllCheckbox.checked = allChecked;
    }}

    if (filtered.length === 0) {{
      tbody.innerHTML = `<tr><td colspan="9" style="padding: 24px; text-align: center; color: #64748B;">No sessions found.</td></tr>`;
      return;
    }}

    tbody.innerHTML = filtered.map(s => {{
      const focus = s.live_metrics?.average_focus ?? s.summary?.average_focus ?? 0.0;
      const focusPercent = Math.round(focus * 100);
      const latency = s.live_metrics?.latency_ms ?? '-';
      const status = s.ended_at ? 'completed' : 'active';
      const statusColor = status === 'active' ? '#22C55E' : '#3B82F6';
      const isChecked = selectedSessions.has(s.session_id) ? 'checked' : '';
      
      let durationStr = '-';
      if (s.started_at) {{
        const start = new Date(s.started_at);
        const end = s.ended_at ? new Date(s.ended_at) : new Date();
        const diffSecs = Math.max(0, Math.floor((end - start) / 1000));
        const mins = Math.floor(diffSecs / 60);
        const secs = diffSecs % 60;
        durationStr = mins + 'm ' + secs + 's';
      }}

      return `
        <tr style="border-bottom: 1px solid #F1F5F9; color: #475569;">
          <td style="padding: 16px; width: 40px;">
            <input type="checkbox" class="session-checkbox" value="${{s.session_id}}" ${{isChecked}} onchange="onSessionCheckChange(this)" style="cursor: pointer; width: 16px; height: 16px;">
          </td>
          <td style="padding: 16px; font-weight: 600;">${{s.user_display_name || s.user_id || '-'}}</td>
          <td style="padding: 16px; font-family: monospace;">${{s.session_id.split('-')[0]}}</td>
          <td style="padding: 16px; font-family: monospace;">${{(s.device_id || '').substring(0,8)}}</td>
          <td style="padding: 16px;">
            <span style="background: ${{statusColor}}1A; color: ${{statusColor}}; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; text-transform: uppercase;">
              ${{status}}
            </span>
          </td>
          <td style="padding: 16px; font-weight: bold;">${{focusPercent}}%</td>
          <td style="padding: 16px;">${{latency !== '-' ? latency + 'ms' : '-'}}</td>
          <td style="padding: 16px;">${{durationStr}}</td>
          <td style="padding: 16px; text-align: right;">
            <button onclick="deleteSession('${{s.session_id}}')" style="background: #EF44441A; color: #EF4444; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600;">
              Delete
            </button>
          </td>
        </tr>
      `;
    }}).join('');
  }}

  function onSessionCheckChange(checkbox) {{
    if (checkbox.checked) {{
      selectedSessions.add(checkbox.value);
    }} else {{
      selectedSessions.delete(checkbox.value);
    }}
    updateBatchDeleteButton();
    
    // Check/uncheck Select All based on whether all filtered are checked
    const selectAllCheckbox = document.getElementById('select-all-checkbox');
    if (selectAllCheckbox) {{
      const query = (document.getElementById('search-input').value || '').toLowerCase().trim();
      const filtered = allSessions.filter(s => {{
        const user = (s.user_display_name || s.user_id || '').toLowerCase();
        const sid = (s.session_id || '').toLowerCase();
        const did = (s.device_id || '').toLowerCase();
        const matchesSearch = user.includes(query) || sid.includes(query) || did.includes(query);
        const status = s.ended_at ? 'completed' : 'active';
        const matchesStatus = statusFilter === 'all' || status === statusFilter;
        return matchesSearch && matchesStatus;
      }});
      const allChecked = filtered.length > 0 && filtered.every(s => selectedSessions.has(s.session_id));
      selectAllCheckbox.checked = allChecked;
    }}
  }}

  function toggleSelectAll(selectAllCheckbox) {{
    const query = (document.getElementById('search-input').value || '').toLowerCase().trim();
    const filtered = allSessions.filter(s => {{
      const user = (s.user_display_name || s.user_id || '').toLowerCase();
      const sid = (s.session_id || '').toLowerCase();
      const did = (s.device_id || '').toLowerCase();
      const matchesSearch = user.includes(query) || sid.includes(query) || did.includes(query);
      const status = s.ended_at ? 'completed' : 'active';
      const matchesStatus = statusFilter === 'all' || status === statusFilter;
      return matchesSearch && matchesStatus;
    }});

    filtered.forEach(s => {{
      if (selectAllCheckbox.checked) {{
        selectedSessions.add(s.session_id);
      }} else {{
        selectedSessions.delete(s.session_id);
      }}
    }});

    const checkboxes = document.querySelectorAll('.session-checkbox');
    checkboxes.forEach(cb => {{
      cb.checked = selectAllCheckbox.checked;
    }});
    
    updateBatchDeleteButton();
  }}

  function updateBatchDeleteButton() {{
    const btn = document.getElementById('batch-delete-btn');
    const countSpan = document.getElementById('selected-count');
    if (selectedSessions.size > 0) {{
      btn.style.display = 'flex';
      countSpan.textContent = selectedSessions.size;
    }} else {{
      btn.style.display = 'none';
    }}
  }}

  async function batchDeleteSelected() {{
    if (selectedSessions.size === 0) return;
    if (!confirm('Are you sure you want to delete the ' + selectedSessions.size + ' selected session(s)?')) return;
    try {{
      const ids = Array.from(selectedSessions);
      const resp = await fetch('/dashboard/api/sessions/batch-delete', {{
        method: 'POST',
        headers: {{ 'X-API-Key': API_KEY, 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ session_ids: ids }})
      }});
      if (resp.ok) {{
        selectedSessions.clear();
        refreshDashboard();
      }}
    }} catch(err) {{
      console.error(err);
    }}
  }}

  async function clearAllSessions() {{
    if (allSessions.length === 0) return;
    if (!confirm('Are you sure you want to delete ALL sessions currently retrieved (up to 100)? This action is permanent.')) return;
    try {{
      const ids = allSessions.map(s => s.session_id);
      const resp = await fetch('/dashboard/api/sessions/batch-delete', {{
        method: 'POST',
        headers: {{ 'X-API-Key': API_KEY, 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ session_ids: ids }})
      }});
      if (resp.ok) {{
        selectedSessions.clear();
        refreshDashboard();
      }}
    }} catch(err) {{
      console.error(err);
    }}
  }}

  async function clearStaleSessions() {{
    if (!confirm('Are you sure you want to delete all inactive/stale active sessions that started more than 1 hour ago?')) return;
    try {{
      const resp = await fetch('/dashboard/api/sessions/clear-stale', {{
        method: 'POST',
        headers: {{ 'X-API-Key': API_KEY }}
      }});
      if (resp.ok) {{
        const result = await resp.json();
        alert('Cleared ' + result.deleted_ids.length + ' stale active session(s).');
        refreshDashboard();
      }}
    }} catch(err) {{
      console.error(err);
    }}
  }}

  async function deleteSession(sessionId) {{
    if (!confirm('Are you sure you want to delete this session?')) return;
    try {{
      const resp = await fetch('/dashboard/api/sessions/' + sessionId, {{
        method: 'DELETE',
        headers: {{ 'X-API-Key': API_KEY }}
      }});
      if (resp.ok) {{
        selectedSessions.delete(sessionId);
        refreshDashboard();
      }}
    }} catch(err) {{
      console.error(err);
    }}
  }}

  function updateDistChart(sessions) {{
    let focusedCount = 0;
    let distractedCount = 0;
    sessions.forEach(s => {{
      const state = s.live_metrics?.state;
      if (state === 'FOCUSED') {{
        focusedCount++;
      }} else {{
        distractedCount++;
      }}
    }});
    distChart.data.datasets[0].data = [focusedCount, distractedCount];
    distChart.update();
  }}

  async function refreshDashboard() {{
    try {{
      const response = await fetch('/dashboard/api/summary?limit=100', {{ cache: 'no-store' }});
      const data = await response.json();
      
      const active = data.active_sessions || 0;
      const total = data.recent_count || 0;
      document.getElementById('val-active').textContent = active;
      document.getElementById('active-badge').textContent = active;
      document.getElementById('val-total').textContent = total;
      
      const sessions = data.recent_sessions || [];
      
      let focusedSessions = 0;
      let focusCount = 0;
      sessions.forEach(s => {{
        const state = s.live_metrics?.state;
        if (state != null) {{
          focusCount++;
          if (state === 'FOCUSED') {{
            focusedSessions++;
          }}
        }}
      }});
      const map50 = focusCount > 0 ? (focusedSessions / focusCount) : 0.00;
      document.getElementById('val-map50').textContent = map50.toFixed(2);
      
      const latencies = sessions.map(s => s.live_metrics?.latency_ms).filter(v => v != null).sort((a,b)=>a-b);
      let p90 = 0, p95 = 0;
      if(latencies.length > 0) {{
        p90 = latencies[Math.floor(latencies.length * 0.9)] || latencies[latencies.length-1];
        p95 = latencies[Math.floor(latencies.length * 0.95)] || latencies[latencies.length-1];
      }}
      
      document.getElementById('val-p95').textContent = p95.toFixed(1);
      document.getElementById('load-val').textContent = p95.toFixed(1) + 'ms';
      document.getElementById('load-fill').style.width = Math.min(100, (p95/200)*100) + '%';
      
      const now = new Date();
      chart.data.labels.push(now.toLocaleTimeString());
      chart.data.datasets[0].data.push(p90);
      chart.data.datasets[1].data.push(p95);
      if(chart.data.labels.length > 10) {{
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
        chart.data.datasets[1].data.shift();
      }}
      chart.update();
      
      document.getElementById('cfg-env').textContent = data.environment || '-';
      document.getElementById('cfg-repo').textContent = data.repository_backend || '-';
      document.getElementById('cfg-event').textContent = data.event_backend || '-';
      document.getElementById('cfg-key').textContent = data.api_key_configured ? 'ENABLED (SECURED)' : 'DISABLED (DEV)';
      
      updateSessionsTable(sessions);
      updateDistChart(sessions);
      
      const listHtml = sessions.slice(0,5).map(s => `
        <div class="recent-item">
          <div class="recent-item-info">
            <div class="recent-item-icon">${{s.user_display_name ? s.user_display_name.charAt(0).toUpperCase() : 'U'}}</div>
            <div>
              <div style="font-weight:600">${{s.user_display_name || s.user_id || 'Unknown'}}</div>
              <div style="font-size:12px; color:#64748B">${{(s.started_at || '').replace('T',' ').slice(0,19)}}</div>
            </div>
          </div>
          <div style="font-size:14px; font-family:monospace; color:#64748B">${{s.session_id.split('-')[0]}}</div>
        </div>
      `).join('');
      document.getElementById('recent-list').innerHTML = listHtml || '<div style="color:#64748B">No recent sessions</div>';
      
    }} catch(err) {{
      console.error(err);
    }}
  }}

  initCharts();
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
async def dashboard(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return HTMLResponse(_dashboard_html(settings))



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


@router.post("/dashboard/api/sessions/batch-delete")
async def dashboard_batch_delete_sessions(
    request: Request,
    payload: dict[str, list[str]],
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    session_ids = payload.get("session_ids", [])
    deleted_ids = []
    for sid in session_ids:
        deleted = await asyncio.to_thread(repository.delete, sid)
        if deleted:
            deleted_ids.append(sid)
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
    return {"status": "deleted", "deleted_ids": deleted_ids}


@router.post("/dashboard/api/sessions/clear-stale")
async def dashboard_clear_stale_sessions(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings, repository, _, _, _ = _services(request)
    _verify_api_key(settings, x_api_key)
    recent = await asyncio.to_thread(repository.list_recent, 100)
    import datetime
    from shared.contracts import utc_now
    now = utc_now()
    deleted_ids = []
    for s in recent:
        if not s.get("ended_at"):
            started_at_str = s.get("started_at")
            if started_at_str:
                try:
                    # parse started_at with timezone offset
                    started_at = datetime.datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    if (now - started_at).total_seconds() > 3600:
                        deleted = await asyncio.to_thread(repository.delete, s["session_id"])
                        if deleted:
                            deleted_ids.append(s["session_id"])
                except Exception:
                    pass
    cache = getattr(request.app.state, "dashboard_cache", None)
    if cache is not None:
        cache.clear()
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
