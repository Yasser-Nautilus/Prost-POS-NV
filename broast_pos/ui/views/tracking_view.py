"""
Tracking view — live order monitoring with filters and timers.

Layout (RTL):
    ┌───────────────────────────────────────────────┐
    │  🔍 Search (invoice #)          Filter tabs   │
    ├───────────────────────────────────────────────┤
    │                                               │
    │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐     │
    │  │ Card │  │ Card │  │ Card │  │ Card │     │
    │  │  #1  │  │  #2  │  │  #3  │  │  #4  │     │
    │  └──────┘  └──────┘  └──────┘  └──────┘     │
    │                                               │
    │  ┌──────┐  ┌──────┐  ...                      │
    │  │ Card │  │ Card │                           │
    │  │  #5  │  │  #6  │                           │
    │  └──────┘  └──────┘                           │
    └───────────────────────────────────────────────┘

Features:
    • Tab filters: الكل / صالة / تيك اواي / دليفري / استلام محل
    • Order cards with live elapsed timer (MM:SS)
    • Takeaway auto-highlight after TAKEAWAY_AUTO_COMPLETE_MINUTES
    • Auto-refresh every TRACKING_REFRESH_SECONDS
    • Search by invoice number
    • Click card → expand with items detail
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import (
    TAKEAWAY_AUTO_COMPLETE_MINUTES,
    TRACKING_REFRESH_SECONDS,
)
from broast_pos.core.models.order import Order, OrderStatus, OrderType
from broast_pos.core.services.order_service import OrderService
from broast_pos.ui.styles.theme import get_color, get_font_family

logger = logging.getLogger(__name__)


# ============================================================================
# Arabic labels
# ============================================================================

_TYPE_LABELS: Dict[OrderType, str] = {
    OrderType.DINE_IN: "صالة",
    OrderType.TAKEAWAY: "تيك اواي",
    OrderType.DELIVERY: "دليفري",
    OrderType.PICKUP: "استلام محل",
}

_TYPE_ICONS: Dict[OrderType, str] = {
    OrderType.DINE_IN: "🍽",
    OrderType.TAKEAWAY: "🥡",
    OrderType.DELIVERY: "🚚",
    OrderType.PICKUP: "🏪",
}

_STATUS_LABELS: Dict[OrderStatus, str] = {
    OrderStatus.NEW: "جديد",
    OrderStatus.PREPARING: "قيد التحضير",
    OrderStatus.READY: "جاهز",

    OrderStatus.OUT_FOR_DELIVERY: "خارج للتوصيل",
    OrderStatus.DELIVERED: "تم التوصيل",
    OrderStatus.COMPLETED: "مكتمل",
    OrderStatus.CANCELLED: "ملغي",
}

_STATUS_COLORS: Dict[OrderStatus, str] = {}


def _init_status_colors() -> None:
    """Lazily initialise status → colour map (theme must be loaded first)."""
    global _STATUS_COLORS
    if _STATUS_COLORS:
        return
    _STATUS_COLORS.update({
        OrderStatus.NEW: get_color("accent_blue"),
        OrderStatus.PREPARING: get_color("accent_orange"),
        OrderStatus.READY: get_color("accent_green"),
        OrderStatus.OUT_FOR_DELIVERY: get_color("accent_yellow"),
        OrderStatus.DELIVERED: get_color("accent_green"),
        OrderStatus.COMPLETED: get_color("accent_green"),
        OrderStatus.CANCELLED: get_color("accent_red"),
    })



# ============================================================================
# Filter definition
# ============================================================================

_FILTER_ALL = "الكل"

_FILTER_TABS = [
    (_FILTER_ALL, None),
    ("صالة", OrderType.DINE_IN),
    ("تيك اواي", OrderType.TAKEAWAY),
    ("دليفري", OrderType.DELIVERY),
    ("استلام محل", OrderType.PICKUP),
]


# ============================================================================
# OrderCard widget
# ============================================================================


class OrderCard(QFrame):
    """Visual card for a single active order.

    Shows:  invoice # │ type │ status badge │ total │ elapsed timer
    Click to expand and show items.
    """

    clicked = pyqtSignal(int)  # order_id

    def __init__(
        self,
        order: Order,
        highlighted: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._order = order
        self._highlighted = highlighted
        self._expanded = False
        self._elapsed_label: Optional[QLabel] = None
        self._items_container: Optional[QWidget] = None

        self.setObjectName("orderCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(140)
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        _init_status_colors()

        order = self._order
        bg = get_color("secondary_bg")
        border = get_color("border_color")

        # Highlight takeaway orders past threshold
        highlight_border = ""
        if self._highlighted:
            highlight_border = f"border: 2px solid {get_color('accent_green')};"
            bg = "#1a2f1a"  # subtle green tint

        self.setStyleSheet(f"""
            QFrame#orderCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
                {highlight_border}
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # --- Row 1: invoice + type icon + status badge ---
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        # Invoice number (large)
        invoice_lbl = QLabel(f"#{order.invoice_no or '—'}")
        invoice_lbl.setStyleSheet(f"""
            font-size: 22px;
            font-weight: bold;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        row1.addWidget(invoice_lbl)

        # Type badge
        type_icon = _TYPE_ICONS.get(order.order_type, "📋")
        type_text = _TYPE_LABELS.get(order.order_type, "—")
        type_lbl = QLabel(f"{type_icon} {type_text}")
        type_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_secondary')};
            background: transparent;
        """)
        row1.addWidget(type_lbl)

        row1.addStretch()

        # Status badge
        status_color = _STATUS_COLORS.get(order.status, get_color("accent_blue"))
        status_text = _STATUS_LABELS.get(order.status, order.status.value)
        status_badge = QLabel(status_text)
        status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_badge.setStyleSheet(f"""
            background-color: {status_color};
            color: #ffffff;
            border-radius: 8px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: bold;
            min-width: 60px;
        """)
        row1.addWidget(status_badge)

        layout.addLayout(row1)

        # --- Row 2: details (table/customer + total + timer) ---
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        # Context info (table or customer)
        context_text = ""
        if order.order_type == OrderType.DINE_IN and order.table_no:
            context_text = f"طاولة {order.table_no}"
        elif order.customer_name:
            context_text = order.customer_name
        elif order.customer_phone:
            context_text = order.customer_phone

        if context_text:
            ctx_lbl = QLabel(context_text)
            ctx_lbl.setStyleSheet(f"""
                font-size: 13px;
                color: {get_color('text_secondary')};
                background: transparent;
            """)
            row2.addWidget(ctx_lbl)

        # Cashier name
        if order.created_by_name:
            cashier_lbl = QLabel(f"👤 {order.created_by_name}")
            cashier_lbl.setStyleSheet(f"""
                font-size: 11px;
                color: {get_color('text_muted')};
                background: transparent;
            """)
            row2.addWidget(cashier_lbl)

        row2.addStretch()

        # Total
        total_lbl = QLabel(f"{order.total:.2f} ج.م")
        total_lbl.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {get_color('accent_green')};
            background: transparent;
        """)
        row2.addWidget(total_lbl)

        layout.addLayout(row2)

        # --- Row 3: elapsed timer + item count ---
        row3 = QHBoxLayout()
        row3.setSpacing(10)

        # Items count
        item_count = sum(i.quantity for i in order.items) if order.items else 0
        items_lbl = QLabel(f"📦 {item_count} عنصر")
        items_lbl.setStyleSheet(f"""
            font-size: 12px;
            color: {get_color('text_muted')};
            background: transparent;
        """)
        row3.addWidget(items_lbl)

        # Highlighted indicator
        if self._highlighted:
            ready_lbl = QLabel("✅ يجب أن يكون جاهز")
            ready_lbl.setStyleSheet(f"""
                font-size: 11px;
                color: {get_color('accent_green')};
                font-weight: bold;
                background: transparent;
            """)
            row3.addWidget(ready_lbl)

        row3.addStretch()

        # Elapsed timer
        self._elapsed_label = QLabel()
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._elapsed_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {get_color('text_secondary')};
            background: transparent;
        """)
        self.update_timer()
        row3.addWidget(self._elapsed_label)

        layout.addLayout(row3)

    # ------------------------------------------------------------------
    # Timer update
    # ------------------------------------------------------------------

    def update_timer(self) -> None:
        """Refresh the elapsed time display."""
        if self._elapsed_label is None:
            return
        elapsed = self._compute_elapsed()
        if elapsed is not None:
            minutes = int(elapsed.total_seconds()) // 60
            seconds = int(elapsed.total_seconds()) % 60
            self._elapsed_label.setText(f"⏱ {minutes:02d}:{seconds:02d}")

            # Change colour if past threshold
            threshold_min = TAKEAWAY_AUTO_COMPLETE_MINUTES
            if minutes >= threshold_min:
                self._elapsed_label.setStyleSheet(f"""
                    font-size: 14px;
                    font-weight: bold;
                    color: {get_color('accent_red')};
                    background: transparent;
                """)
        else:
            self._elapsed_label.setText("⏱ —:—")

    def _compute_elapsed(self) -> Optional[timedelta]:
        """Calculate time since order creation."""
        if not self._order.created_at:
            return None
        try:
            created = datetime.fromisoformat(self._order.created_at)
            return datetime.now() - created
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if self._order.id is not None:
            self.clicked.emit(self._order.id)
        super().mousePressEvent(event)

    @property
    def order(self) -> Order:
        return self._order


# ============================================================================
# TrackingView
# ============================================================================


class TrackingView(QWidget):
    """Live order tracking screen with filters, timers, and auto-refresh.

    Signals:
        order_selected(int): emitted when a card is clicked (order_id).
    """

    order_selected = pyqtSignal(int)

    def __init__(
        self,
        order_service: OrderService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._order_svc = order_service
        self._active_filter: Optional[OrderType] = None  # None = all
        self._search_query: str = ""
        self._cards: List[OrderCard] = []
        self._dismissed_highlights: set = set()  # order_ids where highlight was dismissed

        self._setup_ui()
        self._start_auto_refresh()
        self._refresh_orders()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # --- Header: search + filter tabs ---
        header = QHBoxLayout()
        header.setSpacing(12)

        # Search field
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 بحث برقم الفاتورة ...")
        self._search_input.setFixedWidth(250)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('input_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
                color: {get_color('text_primary')};
            }}
            QLineEdit:focus {{
                border-color: {get_color('accent_blue')};
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        header.addWidget(self._search_input)

        header.addStretch()

        # Filter tabs
        self._filter_buttons: Dict[Optional[OrderType], QPushButton] = {}
        for label, order_type in _FILTER_TABS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.clicked.connect(
                lambda _, t=order_type: self._on_filter_changed(t)
            )
            self._filter_buttons[order_type] = btn
            header.addWidget(btn)

        self._update_filter_styles()

        root.addLayout(header)

        # --- Separator ---
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {get_color('border_color')};")
        root.addWidget(sep)

        # --- Stats bar ---
        self._stats_label = QLabel()
        self._stats_label.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_muted')};
            background: transparent;
        """)
        root.addWidget(self._stats_label)

        # --- Order cards grid (scrollable) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._grid_container)
        root.addWidget(scroll, 1)

    # ------------------------------------------------------------------
    # Filter handling
    # ------------------------------------------------------------------

    def _on_filter_changed(self, order_type: Optional[OrderType]) -> None:
        self._active_filter = order_type
        self._update_filter_styles()
        self._refresh_orders()

    def _update_filter_styles(self) -> None:
        for otype, btn in self._filter_buttons.items():
            active = otype == self._active_filter
            if active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('accent_blue')};
                        color: {get_color('text_primary')};
                        border: none;
                        border-radius: 8px;
                        padding: 6px 16px;
                        font-size: 14px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('secondary_bg')};
                        color: {get_color('text_secondary')};
                        border: 1px solid {get_color('border_color')};
                        border-radius: 8px;
                        padding: 6px 16px;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: rgba(255, 255, 255, 0.05);
                        color: {get_color('text_primary')};
                    }}
                """)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        self._search_query = text.strip()
        self._refresh_orders()

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _start_auto_refresh(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(TRACKING_REFRESH_SECONDS * 1000)
        self._refresh_timer.timeout.connect(self._on_auto_refresh)
        self._refresh_timer.start()

        # Separate timer for updating elapsed displays (every second)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick_timers)
        self._tick_timer.start()

    def _on_auto_refresh(self) -> None:
        """Reload orders from the database."""
        self._refresh_orders()

    def _tick_timers(self) -> None:
        """Update all card timers every second."""
        for card in self._cards:
            card.update_timer()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _refresh_orders(self) -> None:
        """Fetch active orders and rebuild the grid."""
        try:
            if self._active_filter is not None:
                orders = self._order_svc.get_active_by_type(self._active_filter)
            else:
                orders = self._order_svc.get_active_orders()
        except Exception as exc:
            logger.error("Failed to load orders: %s", exc)
            orders = []

        # Apply search filter
        if self._search_query:
            try:
                search_num = int(self._search_query)
                orders = [o for o in orders if o.invoice_no == search_num]
            except ValueError:
                # If not a number, filter by customer name/phone
                q = self._search_query.lower()
                orders = [
                    o for o in orders
                    if (o.customer_name and q in o.customer_name.lower())
                    or (o.customer_phone and q in o.customer_phone)
                ]

        self._rebuild_grid(orders)
        self._update_stats(orders)

    def _rebuild_grid(self, orders: List[Order]) -> None:
        """Clear and rebuild the order card grid."""
        # Clear existing cards
        self._cards.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not orders:
            empty_lbl = QLabel("لا توجد طلبات نشطة")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"""
                font-size: 18px;
                color: {get_color('text_muted')};
                background: transparent;
                padding: 40px;
            """)
            self._grid_layout.addWidget(empty_lbl, 0, 0)
            return

        # Calculate columns based on available width
        cols = max(1, (self.width() - 32) // 340)  # ~340px per card
        if cols < 1:
            cols = 3  # default fallback

        for idx, order in enumerate(orders):
            highlighted = self._should_highlight(order)
            card = OrderCard(order, highlighted=highlighted)
            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)

            row = idx // cols
            col = idx % cols
            self._grid_layout.addWidget(card, row, col)

    def _should_highlight(self, order: Order) -> bool:
        """Determine if a takeaway order should be visually highlighted."""
        if order.id in self._dismissed_highlights:
            return False
        if order.order_type != OrderType.TAKEAWAY:
            return False
        if not order.created_at:
            return False
        try:
            created = datetime.fromisoformat(order.created_at)
            elapsed_min = (datetime.now() - created).total_seconds() / 60
            return elapsed_min >= TAKEAWAY_AUTO_COMPLETE_MINUTES
        except (ValueError, TypeError):
            return False

    def _update_stats(self, orders: List[Order]) -> None:
        """Update the stats bar."""
        total = len(orders)
        type_counts = {}
        for o in orders:
            key = _TYPE_LABELS.get(o.order_type, "—")
            type_counts[key] = type_counts.get(key, 0) + 1

        parts = [f"الإجمالي: {total}"]
        for t, c in type_counts.items():
            parts.append(f"{t}: {c}")

        self._stats_label.setText("  •  ".join(parts))

    # ------------------------------------------------------------------
    # Card interaction
    # ------------------------------------------------------------------

    def _on_card_clicked(self, order_id: int) -> None:
        """Handle card click — emit signal for parent to handle."""
        self.order_selected.emit(order_id)
        logger.debug("Order card clicked: %d", order_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dismiss_highlight(self, order_id: int) -> None:
        """Manually dismiss the auto-complete highlight for an order."""
        self._dismissed_highlights.add(order_id)
        self._refresh_orders()

    def force_refresh(self) -> None:
        """Force an immediate data refresh."""
        self._refresh_orders()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        """Re-layout cards on window resize."""
        super().resizeEvent(event)
        # Trigger re-layout on next refresh
        QTimer.singleShot(100, self._refresh_orders)

    def showEvent(self, event) -> None:
        """Refresh data when the view becomes visible."""
        super().showEvent(event)
        self._refresh_orders()
