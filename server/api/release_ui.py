from __future__ import annotations

import json
from pathlib import Path

from server.config import ServerSettings


_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "releases.html"


def render_release_html(settings: ServerSettings) -> str:
    """Render the public release portal without exposing operational settings."""
    releases = [
        {
            "platform": "Windows",
            "detail": "Windows 10/11, 64-bit",
            "format": "Installer-free .exe",
            "url": settings.release_windows_url,
            "filename": "FocusFlowAI-Windows.exe",
        },
        {
            "platform": "macOS",
            "detail": "Apple Silicon and Intel",
            "format": "Signed-ready .dmg bundle",
            "url": settings.release_macos_url,
            "filename": "FocusFlowAI-macOS.dmg",
        },
        {
            "platform": "Linux",
            "detail": "Desktop Linux, 64-bit",
            "format": "Portable .tar.gz package",
            "url": settings.release_linux_url,
            "filename": "FocusFlowAI-Linux.tar.gz",
        },
    ]
    payload = json.dumps(releases, ensure_ascii=False).replace("</", "<\\/")
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("__RELEASES_JSON__", payload)
        .replace("__RELEASE_VERSION__", _html_text(settings.release_version or "Unversioned preview"))
        .replace("__CHECKSUMS_URL__", _html_attribute(settings.release_checksums_url))
    )


def _html_text(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _html_attribute(value: str) -> str:
    return _html_text(value).replace("'", "&#x27;")
