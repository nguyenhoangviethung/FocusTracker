from __future__ import annotations

from types import SimpleNamespace

from server.api.release_ui import render_release_html


def test_release_portal_renders_gcs_download_links() -> None:
    settings = SimpleNamespace(
        release_version="abc1234",
        release_windows_url="https://storage.googleapis.com/focusflow/releases/latest/FocusFlowAI-Windows.exe",
        release_macos_url="https://storage.googleapis.com/focusflow/releases/latest/FocusFlowAI-macOS.dmg",
        release_linux_url="https://storage.googleapis.com/focusflow/releases/latest/FocusFlowAI-Linux.tar.gz",
        release_checksums_url="https://storage.googleapis.com/focusflow/releases/latest/SHA256SUMS.txt",
    )

    html = render_release_html(settings)

    assert "Release abc1234" in html
    assert "FocusFlowAI-Windows.exe" in html
    assert "FocusFlowAI-macOS.dmg" in html
    assert "FocusFlowAI-Linux.tar.gz" in html
    assert "SHA256SUMS.txt" in html
    assert "__RELEASES_JSON__" not in html


def test_release_portal_marks_missing_links_as_pending() -> None:
    settings = SimpleNamespace(
        release_version="preview",
        release_windows_url="",
        release_macos_url="",
        release_linux_url="",
        release_checksums_url="",
    )

    html = render_release_html(settings)

    assert "Release pending" in html
    assert 'id="checksums"' in html
    assert 'href=""' in html
