from __future__ import annotations

from pathlib import Path
import sys

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from ui.app_window import FocusFlowApp
from ui.auth_dialog import AuthDialog
from ui.theme import ThemeManager
from utils.logger import get_logger, setup_logging
from utils.settings_store import load_settings, save_settings


load_dotenv(Path(__file__).resolve().with_name(".env"), override=True)

logger = get_logger("main")


def _apply_auth_profile(settings: dict, profile: dict | None) -> dict:
    if not profile:
        return settings
    merged = dict(settings)
    merged.update(
        {
            "auth_user_id": str(profile.get("user_id") or ""),
            "auth_provider": str(profile.get("auth_provider") or ""),
            "auth_username": str(profile.get("username") or ""),
            "auth_email": str(profile.get("email") or ""),
            "auth_display_name": str(profile.get("display_name") or ""),
            "auth_last_login_at": str(profile.get("last_login_at") or ""),
        }
    )
    return save_settings(merged)


def main() -> None:
    setup_logging()
    logger.info("Starting FocusFlow AI PyQt6 desktop app")

    app = QApplication(sys.argv)
    settings = load_settings()
    theme = ThemeManager(str(settings.get("theme_mode", "Dark")))
    auth_dialog = AuthDialog(theme, settings)
    if auth_dialog.exec() == auth_dialog.DialogCode.Accepted:
        settings = _apply_auth_profile(settings, auth_dialog.profile())
        logger.info(
            "Authenticated user saved: provider=%s user_id=%s",
            settings.get("auth_provider") or "unknown",
            settings.get("auth_user_id") or "unknown",
        )
    window = FocusFlowApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
