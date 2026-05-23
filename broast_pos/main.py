"""
Prost POS — Application entry point.

Startup sequence:
    1. Configure logging
    2. Load config (restaurant.json)
    3. Initialise database + run migrations + seed if empty
    4. Create service instances
    5. Create QApplication, apply theme
    6. Show login window
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from broast_pos.config.config import get_app_name
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.ui.styles.theme import apply_theme
from broast_pos.ui.windows.login_window import LoginWindow

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger with a simple console format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    """Application entry point — returns exit code."""
    _setup_logging()
    logger.info("Starting %s …", get_app_name())

    # ------------------------------------------------------------------
    # 1. Database
    # ------------------------------------------------------------------
    try:
        db = DatabaseConnection.get_instance()
        initialise_database(db)
        seed_database(db)
        logger.info("Database ready (WAL mode)")
    except Exception as exc:
        logger.critical("Database init failed: %s", exc)
        return 1

    # ------------------------------------------------------------------
    # 2. Services
    # ------------------------------------------------------------------
    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo)

    # ------------------------------------------------------------------
    # 3. Qt Application
    # ------------------------------------------------------------------
    app = QApplication(sys.argv)
    app.setApplicationName(get_app_name())

    # Apply dark theme + Arabic font + RTL
    apply_theme(app)

    # ------------------------------------------------------------------
    # 4. Login Window
    # ------------------------------------------------------------------
    login_window = LoginWindow(auth_service)

    def on_login_complete(user):
        logger.info("→ Logged in as: %s (%s)", user.display_name, user.role.value)
        # TODO: Phase 2 — hide login, show MainWindow
        #       For now, just log and keep the login window open

    login_window.login_complete.connect(on_login_complete)
    login_window.show()

    logger.info("Application ready — showing login window")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
