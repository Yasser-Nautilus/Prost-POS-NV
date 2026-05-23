"""
Login view — avatar tiles → PIN numpad → session.

Two-phase UI:
  1. Avatar grid: shows all active users as circular tiles
  2. PIN entry: on-screen numpad with masked input

Emits ``login_success(User)`` on valid authentication.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QPoint,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import get_restaurant_info
from broast_pos.core.models.user import User
from broast_pos.core.services.auth_service import AuthService
from broast_pos.ui.styles.theme import get_color, get_font_family

logger = logging.getLogger(__name__)

# Pastel-ish colours for initials avatars (rotating)
_AVATAR_COLORS = [
    "#3498db", "#e74c3c", "#2ecc71", "#9b59b6",
    "#f39c12", "#1abc9c", "#e67e22", "#34495e",
]


# ============================================================================
# Login View (two-phase: tiles → PIN)
# ============================================================================


class LoginView(QWidget):
    """Full login screen: avatar tile grid + PIN numpad."""

    login_success = pyqtSignal(object)  # emits User

    def __init__(
        self,
        auth_service: AuthService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._auth = auth_service
        self._selected_user: Optional[User] = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0: avatar tiles
        self._tiles_page = _AvatarTilesPage(self._auth)
        self._tiles_page.user_selected.connect(self._on_user_selected)
        self._stack.addWidget(self._tiles_page)

        # Page 1: PIN entry
        self._pin_page = _PinEntryPage()
        self._pin_page.pin_submitted.connect(self._on_pin_submitted)
        self._pin_page.back_requested.connect(self._show_tiles)
        self._stack.addWidget(self._pin_page)

        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_user_selected(self, user: User) -> None:
        self._selected_user = user
        self._pin_page.set_user(user)
        self._stack.setCurrentIndex(1)

    def _on_pin_submitted(self, pin: str) -> None:
        if self._selected_user is None:
            return

        try:
            user = self._auth.login(self._selected_user.id, pin)
            logger.info("Login success: %s (%s)", user.display_name, user.role.value)
            self.login_success.emit(user)
        except ValueError as exc:
            logger.warning("Login failed for user %s: %s", self._selected_user.display_name, exc)
            self._pin_page.show_error(str(exc))

    def _show_tiles(self) -> None:
        self._selected_user = None
        self._tiles_page.refresh()
        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload user tiles (call on logout / return)."""
        self._tiles_page.refresh()
        self._pin_page.clear()
        self._stack.setCurrentIndex(0)


# ============================================================================
# Page 1: Avatar Tiles Grid
# ============================================================================


class _AvatarTilesPage(QWidget):
    """Grid of user avatar tiles."""

    user_selected = pyqtSignal(object)  # emits User

    def __init__(self, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self._auth = auth_service
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(20)

        # Header: restaurant branding
        header = QVBoxLayout()
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info = get_restaurant_info()
        name = info.get("name_ar", "Prost POS")
        slogan = info.get("slogan_ar", "")

        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(f"""
            font-size: 32px;
            font-weight: bold;
            color: {get_color('text_primary')};
            margin-bottom: 4px;
        """)
        header.addWidget(name_lbl)

        if slogan:
            slogan_lbl = QLabel(slogan)
            slogan_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            slogan_lbl.setStyleSheet(f"""
                font-size: 16px;
                color: {get_color('text_secondary')};
            """)
            header.addWidget(slogan_lbl)

        prompt_lbl = QLabel("اختر المستخدم")
        prompt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt_lbl.setStyleSheet(f"""
            font-size: 20px;
            color: {get_color('text_secondary')};
            margin-top: 20px;
        """)
        header.addWidget(prompt_lbl)

        outer.addLayout(header)

        # Tile grid container
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(20)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._grid_container, 1)

        outer.addStretch()

    def refresh(self) -> None:
        """Reload tiles from auth service."""
        # Clear existing tiles
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        users = self._auth.get_all_users()
        cols = min(4, max(1, len(users)))  # 1–4 columns

        for i, user in enumerate(users):
            tile = _AvatarTile(user, i)
            tile.clicked_user.connect(self.user_selected.emit)
            row, col = divmod(i, cols)
            self._grid_layout.addWidget(tile, row, col, Qt.AlignmentFlag.AlignCenter)


class _AvatarTile(QFrame):
    """Single user tile: coloured circle with initials + name below."""

    clicked_user = pyqtSignal(object)  # emits User

    TILE_SIZE = 140  # overall tile width
    AVATAR_SIZE = 90  # circle diameter

    def __init__(self, user: User, index: int, parent=None):
        super().__init__(parent)
        self._user = user
        self._color = QColor(_AVATAR_COLORS[index % len(_AVATAR_COLORS)])
        self._hovered = False

        self.setFixedSize(self.TILE_SIZE, self.TILE_SIZE + 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Avatar circle (custom painted)
        self._avatar_widget = _InitialsCircle(
            self._get_initials(),
            self._color,
            self.AVATAR_SIZE,
        )
        layout.addWidget(self._avatar_widget, 0, Qt.AlignmentFlag.AlignCenter)

        # Name label
        name_lbl = QLabel(user.display_name or user.username)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

    def _get_initials(self) -> str:
        name = self._user.display_name or self._user.username
        if not name:
            return "?"
        parts = name.split()
        if len(parts) >= 2:
            return parts[0][0] + parts[-1][0]
        return name[0]

    def enterEvent(self, event):
        self._hovered = True
        self._avatar_widget.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._avatar_widget.set_hovered(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked_user.emit(self._user)
        super().mousePressEvent(event)


class _InitialsCircle(QWidget):
    """Draws a coloured circle with text initials."""

    def __init__(self, initials: str, color: QColor, size: int, parent=None):
        super().__init__(parent)
        self._initials = initials
        self._color = color
        self._size = size
        self._hovered = False
        self.setFixedSize(size, size)

    def set_hovered(self, hovered: bool) -> None:
        self._hovered = hovered
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circle
        color = self._color.lighter(120) if self._hovered else self._color
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        margin = 2 if self._hovered else 0
        painter.drawEllipse(
            margin, margin,
            self._size - 2 * margin,
            self._size - 2 * margin,
        )

        # Ring on hover
        if self._hovered:
            from PyQt6.QtGui import QPen
            pen = QPen(QColor("#ffffff"), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(1, 1, self._size - 2, self._size - 2)

        # Initials text
        painter.setPen(QColor("#ffffff"))
        font = QFont(get_font_family(), self._size // 3)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._initials)

        painter.end()


# ============================================================================
# Page 2: PIN Entry
# ============================================================================


class _PinEntryPage(QWidget):
    """PIN numpad with masked display."""

    pin_submitted = pyqtSignal(str)
    back_requested = pyqtSignal()

    MAX_PIN_LENGTH = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pin = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setSpacing(16)

        # --- Back button ---
        back_row = QHBoxLayout()
        self._back_btn = QPushButton("→ رجوع")
        self._back_btn.setObjectName("backBtn")
        self._back_btn.setFixedHeight(44)
        self._back_btn.setStyleSheet(f"""
            QPushButton#backBtn {{
                background: transparent;
                color: {get_color('text_secondary')};
                border: none;
                font-size: 16px;
                padding: 4px 12px;
            }}
            QPushButton#backBtn:hover {{
                color: {get_color('text_primary')};
            }}
        """)
        self._back_btn.clicked.connect(self._on_back)
        back_row.addWidget(self._back_btn)
        back_row.addStretch()
        outer.addLayout(back_row)

        outer.addStretch(1)

        # --- Centre content ---
        centre = QVBoxLayout()
        centre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centre.setSpacing(16)

        # User name
        self._user_label = QLabel("")
        self._user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._user_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {get_color('text_primary')};
        """)
        centre.addWidget(self._user_label)

        # Prompt
        prompt = QLabel("أدخل رمز الدخول")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt.setStyleSheet(f"""
            font-size: 16px;
            color: {get_color('text_secondary')};
        """)
        centre.addWidget(prompt)

        # PIN dots display
        self._pin_display = QLabel("")
        self._pin_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pin_display.setFixedHeight(60)
        self._pin_display.setStyleSheet(f"""
            font-size: 36px;
            letter-spacing: 12px;
            color: {get_color('text_primary')};
            background-color: {get_color('input_bg')};
            border: 2px solid {get_color('border_color')};
            border-radius: 10px;
            padding: 8px 20px;
            min-width: 200px;
        """)
        centre.addWidget(self._pin_display, 0, Qt.AlignmentFlag.AlignCenter)

        # Error label
        self._error_label = QLabel("")
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('accent_red')};
            min-height: 24px;
        """)
        centre.addWidget(self._error_label)

        # Numpad grid
        numpad_widget = QWidget()
        numpad_widget.setFixedWidth(300)
        numpad = QGridLayout(numpad_widget)
        numpad.setSpacing(10)

        btn_style = f"""
            QPushButton {{
                background-color: {get_color('secondary_bg')};
                color: {get_color('text_primary')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
                min-width: 70px;
                min-height: 70px;
            }}
            QPushButton:hover {{
                background-color: {get_color('border_color')};
            }}
            QPushButton:pressed {{
                background-color: {get_color('accent_blue')};
            }}
        """

        # Number buttons 1-9
        for i in range(1, 10):
            btn = QPushButton(str(i))
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, d=str(i): self._on_digit(d))
            row, col = divmod(i - 1, 3)
            numpad.addWidget(btn, row, col)

        # Bottom row: Clear, 0, Backspace
        clear_btn = QPushButton("مسح")
        clear_btn.setStyleSheet(btn_style.replace(
            get_color('secondary_bg'), get_color('button_cancel')
        ))
        clear_btn.clicked.connect(self._on_clear)
        numpad.addWidget(clear_btn, 3, 0)

        zero_btn = QPushButton("0")
        zero_btn.setStyleSheet(btn_style)
        zero_btn.clicked.connect(lambda: self._on_digit("0"))
        numpad.addWidget(zero_btn, 3, 1)

        back_btn = QPushButton("⌫")
        back_btn.setStyleSheet(btn_style)
        back_btn.clicked.connect(self._on_backspace)
        numpad.addWidget(back_btn, 3, 2)

        # Enter button (full width)
        enter_btn = QPushButton("دخول")
        enter_btn.setObjectName("enterBtn")
        enter_btn.setStyleSheet(f"""
            QPushButton#enterBtn {{
                background-color: {get_color('button_confirm')};
                color: {get_color('text_primary')};
                border: none;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
                min-height: 60px;
            }}
            QPushButton#enterBtn:hover {{
                background-color: {get_color('accent_green')};
            }}
            QPushButton#enterBtn:pressed {{
                background-color: #1a9a3a;
            }}
        """)
        enter_btn.clicked.connect(self._on_enter)
        numpad.addWidget(enter_btn, 4, 0, 1, 3)

        centre.addWidget(numpad_widget, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addLayout(centre)
        outer.addStretch(1)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_user(self, user: User) -> None:
        self._user_label.setText(user.display_name or user.username)
        self.clear()

    def clear(self) -> None:
        self._pin = ""
        self._update_display()
        self._error_label.setText("")

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._pin = ""
        self._update_display()
        self._shake()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_digit(self, digit: str) -> None:
        if len(self._pin) < self.MAX_PIN_LENGTH:
            self._pin += digit
            self._update_display()
            self._error_label.setText("")

    def _on_backspace(self) -> None:
        if self._pin:
            self._pin = self._pin[:-1]
            self._update_display()

    def _on_clear(self) -> None:
        self.clear()

    def _on_enter(self) -> None:
        if self._pin:
            self.pin_submitted.emit(self._pin)

    def _on_back(self) -> None:
        self.clear()
        self.back_requested.emit()

    def _update_display(self) -> None:
        self._pin_display.setText("●" * len(self._pin))

    def _shake(self) -> None:
        """Shake the PIN display on invalid input."""
        anim = QPropertyAnimation(self._pin_display, b"pos")
        anim.setDuration(300)
        origin = self._pin_display.pos()
        anim.setKeyValueAt(0.0, origin)
        anim.setKeyValueAt(0.15, origin + QPoint(12, 0))
        anim.setKeyValueAt(0.30, origin + QPoint(-10, 0))
        anim.setKeyValueAt(0.45, origin + QPoint(8, 0))
        anim.setKeyValueAt(0.60, origin + QPoint(-6, 0))
        anim.setKeyValueAt(0.75, origin + QPoint(4, 0))
        anim.setKeyValueAt(0.90, origin + QPoint(-2, 0))
        anim.setKeyValueAt(1.0, origin)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        # Must keep a reference so it doesn't get GC'd
        self._shake_anim = anim
        anim.start()
