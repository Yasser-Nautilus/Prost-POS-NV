"""
Login window — container for the login view.

This is the first window shown on app start.  It hosts ``LoginView``
and emits ``login_complete(User)`` when authentication succeeds.

Zero business logic — everything is delegated to ``LoginView`` and
``AuthService``.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QMainWindow, QWidget

from broast_pos.config.config import get_app_name
from broast_pos.core.models.user import User
from broast_pos.core.services.auth_service import AuthService
from broast_pos.ui.views.login_view import LoginView

logger = logging.getLogger(__name__)


class LoginWindow(QMainWindow):
    """Window that hosts the avatar-tile login flow.

    Signals:
        login_complete(User): emitted after valid PIN entry.
    """

    login_complete = pyqtSignal(object)  # emits User

    def __init__(
        self,
        auth_service: AuthService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._auth = auth_service

        self._setup_window()
        self._setup_content()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(get_app_name())
        self.setMinimumSize(1024, 600)

        # Start maximised but not fullscreen
        self.setWindowState(
            self.windowState() | Qt.WindowState.WindowMaximized
        )

    def _setup_content(self) -> None:
        self._login_view = LoginView(self._auth)
        self._login_view.login_success.connect(self._on_login_success)
        self.setCentralWidget(self._login_view)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_login_success(self, user: User) -> None:
        logger.info(
            "Login window: user '%s' logged in (role=%s)",
            user.display_name,
            user.role.value,
        )
        self.login_complete.emit(user)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Return to the tile grid (call on logout from main window)."""
        self._login_view.refresh()
