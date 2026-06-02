"""
Main window — navigation shell with role-based sidebar.

Layout (RTL):
    ┌──────────────────────────────┐
    │  Header (user + shift)       │
    ├──────────┬───────────────────┤
    │ Content  │  Sidebar (nav)    │
    │ (stacked │  🛒 نقطة البيع    │
    │  widget) │  📋 تتبع الطلبات  │
    │          │  🚚 التوصيل       │
    │          │  📊 التقارير      │
    │          │  📦 المنتجات      │
    │          │  👥 المستخدمين    │
    │          │  💰 المالية       │
    │          │  ──────────       │
    │          │  🚪 تسجيل خروج   │
    └──────────┴───────────────────┘

Role-based visibility:
    CASHIER  → POS, Tracking, Delivery (3 items)
    MANAGER  → all except Users (6 items)
    ADMIN    → all (7 items)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import get_app_name
from broast_pos.core.models.user import User, UserRole
from broast_pos.ui.styles.theme import get_color, get_font_family

logger = logging.getLogger(__name__)


# ============================================================================
# Navigation definition
# ============================================================================


class NavPage(Enum):
    """Identifiers for each navigable page."""
    POS = auto()
    TRACKING = auto()
    DELIVERY = auto()
    REPORTS = auto()
    PRODUCTS = auto()
    USERS = auto()
    FINANCIAL = auto()


@dataclass(frozen=True)
class NavItem:
    """Sidebar navigation button metadata."""
    page: NavPage
    icon: str          # emoji
    label: str         # Arabic text
    min_role: UserRole  # minimum role required


# Navigation items in display order
_NAV_ITEMS: List[NavItem] = [
    NavItem(NavPage.POS,       "🛒", "نقطة البيع",   UserRole.CASHIER),
    NavItem(NavPage.TRACKING,  "📋", "تتبع الطلبات", UserRole.CASHIER),
    NavItem(NavPage.DELIVERY,  "🚚", "التوصيل",      UserRole.CASHIER),
    NavItem(NavPage.REPORTS,   "📊", "التقارير",      UserRole.MANAGER),
    NavItem(NavPage.PRODUCTS,  "📦", "المنتجات",      UserRole.MANAGER),
    NavItem(NavPage.USERS,     "👥", "المستخدمين",    UserRole.ADMIN),
    NavItem(NavPage.FINANCIAL, "💰", "المالية",        UserRole.MANAGER),
]

# Role hierarchy for permission checks
_ROLE_LEVEL: Dict[UserRole, int] = {
    UserRole.CASHIER: 0,
    UserRole.MANAGER: 1,
    UserRole.ADMIN: 2,
}


def _has_access(user_role: UserRole, min_role: UserRole) -> bool:
    """Check if *user_role* meets the *min_role* requirement."""
    return _ROLE_LEVEL.get(user_role, 0) >= _ROLE_LEVEL.get(min_role, 0)


# ============================================================================
# Main Window
# ============================================================================


class MainWindow(QWidget):
    """Application shell: header + sidebar + stacked content area.

    Signals:
        logout_requested: emitted when the user clicks logout.
    """

    logout_requested = pyqtSignal()
    shift_clicked = pyqtSignal()

    # Sidebar dimensions (min/max for flexible layout)
    SIDEBAR_MIN_WIDTH = 180
    SIDEBAR_MAX_WIDTH = 240
    HEADER_MIN_HEIGHT = 48
    HEADER_MAX_HEIGHT = 64

    def __init__(self, user: User, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user = user
        self._nav_buttons: Dict[NavPage, QPushButton] = {}
        self._page_widgets: Dict[NavPage, QWidget] = {}
        self._active_page: Optional[NavPage] = None

        self._setup_window()
        self._setup_ui()
        self._apply_role_visibility()
        self._navigate_to(NavPage.POS)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(get_app_name())
        self.setMinimumSize(1024, 600)
        self.showMaximized()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Header ---
        root.addWidget(self._build_header())

        # --- Body: sidebar + content ---
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar (toggleable) — added FIRST (appears on right in RTL)
        self._sidebar = self._build_sidebar()
        self._sidebar.setVisible(False)  # hidden by default
        body.addWidget(self._sidebar)

        # Content area (fills remaining space) — added SECOND for RTL
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._register_placeholder_views()
        body.addWidget(self._stack, 1)

        root.addLayout(body, 1)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setMinimumHeight(self.HEADER_MIN_HEIGHT)
        header.setMaximumHeight(self.HEADER_MAX_HEIGHT)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-bottom: 1px solid {get_color('border_color')};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)

        # Left side: app name
        app_label = QLabel(get_app_name())
        app_label.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        layout.addWidget(app_label)

        # Sidebar toggle button (hamburger)
        self._sidebar_toggle = QPushButton("☰")
        self._sidebar_toggle.setObjectName("sidebarToggle")
        self._sidebar_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sidebar_toggle.setStyleSheet(f"""
            QPushButton#sidebarToggle {{
                background: transparent;
                color: {get_color('text_secondary')};
                border: none;
                border-radius: 6px;
                font-size: 20px;
                padding: 4px 10px;
                min-height: 32px;
            }}
            QPushButton#sidebarToggle:hover {{
                background-color: rgba(255, 255, 255, 0.08);
                color: {get_color('text_primary')};
            }}
        """)
        self._sidebar_toggle.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._sidebar_toggle)

        layout.addStretch()

        # Right side: user info + role badge
        role_colors = {
            UserRole.CASHIER: get_color('accent_blue'),
            UserRole.MANAGER: get_color('accent_orange'),
            UserRole.ADMIN: get_color('accent_red'),
        }
        role_labels = {
            UserRole.CASHIER: "كاشير",
            UserRole.MANAGER: "مدير",
            UserRole.ADMIN: "مسؤول",
        }

        role_color = role_colors.get(self._user.role, get_color('accent_blue'))
        role_text = role_labels.get(self._user.role, "")

        role_badge = QLabel(role_text)
        role_badge.setStyleSheet(f"""
            background-color: {role_color};
            color: #ffffff;
            border-radius: 10px;
            padding: 3px 12px;
            font-size: 12px;
            font-weight: bold;
        """)
        layout.addWidget(role_badge)

        user_label = QLabel(self._user.display_name or self._user.username)
        user_label.setStyleSheet(f"""
            font-size: 15px;
            color: {get_color('text_primary')};
            background: transparent;
            margin-right: 8px;
        """)
        layout.addWidget(user_label)

        # Shift button/badge
        self._shift_btn = QPushButton("🔴  الوردية: مغلقة")
        self._shift_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shift_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(220, 53, 69, 0.15);
                border: 1px solid {get_color('accent_red')};
                color: {get_color('accent_red')};
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(220, 53, 69, 0.25);
            }}
        """)
        self._shift_btn.clicked.connect(self.shift_clicked.emit)
        layout.addWidget(self._shift_btn)

        # Printer status indicator
        self._printer_badge = QLabel("🖨")
        self._printer_badge.setToolTip("حالة الطابعة")
        self._printer_badge.setStyleSheet(f"""
            font-size: 18px;
            background: transparent;
            margin-right: 12px;
        """)
        layout.addWidget(self._printer_badge)

        return header

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setMinimumWidth(self.SIDEBAR_MIN_WIDTH)
        sidebar.setMaximumWidth(self.SIDEBAR_MAX_WIDTH)
        sidebar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-left: 1px solid {get_color('border_color')};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(4)

        # Navigation buttons
        for item in _NAV_ITEMS:
            btn = self._create_nav_button(item)
            self._nav_buttons[item.page] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Separator
        sep = QFrame()
        sep.setMinimumHeight(1)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f"background-color: {get_color('border_color')};")
        layout.addWidget(sep)

        # Logout button
        logout_btn = QPushButton("🚪  تسجيل خروج")
        logout_btn.setObjectName("logoutBtn")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(f"""
            QPushButton#logoutBtn {{
                background: transparent;
                color: {get_color('accent_red')};
                border: none;
                border-radius: 8px;
                padding: 12px 8px;
                font-size: 15px;
                text-align: right;
                min-height: 44px;
            }}
            QPushButton#logoutBtn:hover {{
                background-color: rgba(220, 53, 69, 0.15);
            }}
        """)
        logout_btn.clicked.connect(self._on_logout)
        layout.addWidget(logout_btn)

        return sidebar

    def _create_nav_button(self, item: NavItem) -> QPushButton:
        btn = QPushButton(f"{item.icon}  {item.label}")
        btn.setObjectName(f"nav_{item.page.name}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._nav_button_style(active=False))
        btn.clicked.connect(lambda _, p=item.page: self._navigate_to(p))
        return btn

    def _nav_button_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background-color: {get_color('accent_blue')};
                    color: {get_color('text_primary')};
                    border: none;
                    border-radius: 8px;
                    padding: 12px 8px;
                    font-size: 15px;
                    font-weight: bold;
                    text-align: right;
                    min-height: 44px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                color: {get_color('text_secondary')};
                border: none;
                border-radius: 8px;
                padding: 12px 8px;
                font-size: 15px;
                text-align: right;
                min-height: 44px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {get_color('text_primary')};
            }}
        """

    # ------------------------------------------------------------------
    # Content area — placeholder views
    # ------------------------------------------------------------------

    def _register_placeholder_views(self) -> None:
        """Create placeholder widgets for each page.

        Real views will be injected later via ``set_view()``.
        """
        for item in _NAV_ITEMS:
            placeholder = self._make_placeholder(item)
            index = self._stack.addWidget(placeholder)
            self._page_widgets[item.page] = placeholder

    def _make_placeholder(self, item: NavItem) -> QWidget:
        """Temporary placeholder showing the page name."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(item.icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(item.label)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {get_color('text_secondary')};
            background: transparent;
        """)
        layout.addWidget(name_lbl)

        hint_lbl = QLabel("قريباً …")
        hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_lbl.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('text_muted')};
            background: transparent;
            margin-top: 8px;
        """)
        layout.addWidget(hint_lbl)

        return widget

    # ------------------------------------------------------------------
    # Public API — inject real views
    # ------------------------------------------------------------------

    def set_view(self, page: NavPage, widget: QWidget) -> None:
        """Replace the placeholder for *page* with a real view widget.

        Call this from ``main.py`` to inject fully wired views.
        """
        old = self._page_widgets.get(page)
        if old is not None:
            index = self._stack.indexOf(old)
            self._stack.removeWidget(old)
            old.deleteLater()
            self._stack.insertWidget(index, widget)
        else:
            self._stack.addWidget(widget)

        self._page_widgets[page] = widget

        # If we're currently viewing this page, switch to the new widget
        if self._active_page == page:
            self._stack.setCurrentWidget(widget)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_to(self, page: NavPage) -> None:
        widget = self._page_widgets.get(page)
        if widget is None:
            return

        # Update button styles
        for p, btn in self._nav_buttons.items():
            btn.setStyleSheet(self._nav_button_style(active=(p == page)))

        self._stack.setCurrentWidget(widget)
        self._active_page = page
        logger.debug("Navigated to %s", page.name)

    def _apply_role_visibility(self) -> None:
        """Show/hide nav buttons based on current user's role."""
        for item in _NAV_ITEMS:
            btn = self._nav_buttons.get(item.page)
            if btn is not None:
                btn.setVisible(_has_access(self._user.role, item.min_role))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_logout(self) -> None:
        logger.info("Logout requested by %s", self._user.display_name)
        self.logout_requested.emit()

    def _toggle_sidebar(self) -> None:
        """Show/hide the navigation sidebar."""
        visible = self._sidebar.isVisible()
        self._sidebar.setVisible(not visible)
        self._sidebar_toggle.setText("✕" if not visible else "☰")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_user(self) -> User:
        """Return the currently logged-in user."""
        return self._user

    def update_printer_status(self, healthy: bool) -> None:
        """Update the header printer badge."""
        if healthy:
            self._printer_badge.setText("🖨")
            self._printer_badge.setToolTip("الطابعة متصلة")
        else:
            self._printer_badge.setText("🖨⚠")
            self._printer_badge.setToolTip("الطابعة غير متصلة")

    def update_shift_status(self, active: bool, shift_id: Optional[int] = None) -> None:
        """Update the header shift badge."""
        if active and shift_id is not None:
            self._shift_btn.setText(f"🟢  الوردية: #{shift_id}")
            self._shift_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(40, 167, 69, 0.15);
                    border: 1px solid {get_color('accent_green')};
                    color: {get_color('accent_green')};
                    border-radius: 8px;
                    padding: 4px 12px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: rgba(40, 167, 69, 0.25);
                }}
            """)
        else:
            self._shift_btn.setText("🔴  الوردية: مغلقة")
            self._shift_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(220, 53, 69, 0.15);
                    border: 1px solid {get_color('accent_red')};
                    color: {get_color('accent_red')};
                    border-radius: 8px;
                    padding: 4px 12px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: rgba(220, 53, 69, 0.25);
                }}
            """)

