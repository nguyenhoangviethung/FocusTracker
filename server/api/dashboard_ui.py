from __future__ import annotations

import json
from pathlib import Path


_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard.html"


def render_dashboard_html(api_key: str) -> str:
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("__API_KEY_JSON__", json.dumps(api_key or ""))
