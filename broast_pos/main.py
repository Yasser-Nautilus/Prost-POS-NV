"""
Prost POS — Application entry point.

Startup sequence:
    1. Configure logging
    2. Load config (restaurant.json)
    3. Initialise database + run migrations + seed if empty
    4. Create service instances
    5. Create QApplication, apply theme
    6. Show login window → on login → show main window
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from PyQt6.QtWidgets import QApplication

from broast_pos.config.config import get_app_name
from broast_pos.core.models.user import User
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.ui.styles.theme import apply_theme
from broast_pos.ui.windows.login_window import LoginWindow
from broast_pos.ui.windows.main_window import MainWindow

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger with a simple console format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


class AppController:
    """Manages window lifecycle: login ↔ main window transitions.

    Owns both windows and handles the swap on login/logout.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._auth = auth_service
        self._login_window = LoginWindow(auth_service)
        self._main_window: Optional[MainWindow] = None

        # Wire login → show main
        self._login_window.login_complete.connect(self._on_login)

    # ------------------------------------------------------------------
    # Window transitions
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Show the login window — entry point."""
        self._login_window.show()

    def _on_login(self, user: User) -> None:
        """Login succeeded → hide login, create and show main window."""
        logger.info(
            "→ Logged in: %s (%s)", user.display_name, user.role.value
        )
        self._login_window.hide()

        # Create a fresh main window for this session
        self._main_window = MainWindow(user)
        self._main_window.logout_requested.connect(self._on_logout)
        self._main_window.show()

    def _on_logout(self) -> None:
        """Logout requested → destroy main window, show login."""
        logger.info("← Logout — returning to login screen")
        self._auth.logout()

        if self._main_window is not None:
            self._main_window.close()
            self._main_window.deleteLater()
            self._main_window = None

        self._login_window.reset()
        self._login_window.show()


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
    # 4. Window lifecycle controller
    # ------------------------------------------------------------------
    controller = AppController(auth_service)
    controller.start()

    logger.info("Application ready — showing login window")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
