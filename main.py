from __future__ import annotations
import sys

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from ui.app_window import FocusFlowApp
from utils.logger import get_logger, setup_logging


load_dotenv()

logger = get_logger("main")

def main() -> None:
    setup_logging()
    logger.info("Starting FocusFlow AI PyQt6 desktop app")
    
    app = QApplication(sys.argv)
    window = FocusFlowApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
