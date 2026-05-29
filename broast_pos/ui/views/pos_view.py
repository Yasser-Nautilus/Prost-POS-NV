"""
POS view — main cashier screen (3-column layout).

Layout (RTL):
    ┌─────────────────────────────────────────────────┐
    │  Parked orders bar (tabs: +, order1, order2 …)  │
    ├──────────┬──────────────────────┬────────────────┤
    │ Order    │   Product grid       │  Categories    │
    │ panel    │   (centre)           │  (right col)   │
    │ (left)   │                      │                │
    │          │                      │                │
    ├──────────┴──────────────────────┴────────────────┤
    │ Action bar: order type + confirm/cancel/discount │
    └─────────────────────────────────────────────────┘

Note: In RTL, "left" visually appears on the right and vice versa.
The code uses logical layout ordering; Qt handles the RTL flip.

This view owns in-memory Order objects (parked orders) and calls
``ProductService`` for categories/products.  No DB writes happen
here — saving is handled by ``OrderService`` when the user confirms.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import (
    SERVICE_CHARGE_PCT,
    TABLE_COUNT,
    get_category_colors,
)
from broast_pos.core.models.order import Order, OrderItem, OrderType
from broast_pos.core.models.product import Category, Product
from broast_pos.core.services.product_service import ProductService
from broast_pos.ui.components.order_panel import OrderPanel
from broast_pos.ui.components.product_grid import ProductGrid
from broast_pos.ui.components.table_grid import TableGrid
from broast_pos.ui.dialogs.pin_dialog import PinDialog
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

# Arabic labels for order types
_ORDER_TYPE_LABELS: Dict[OrderType, str] = {
    OrderType.DINE_IN:  "صالة",
    OrderType.TAKEAWAY: "تيك اواي",
    OrderType.DELIVERY: "دليفري",
    OrderType.PICKUP:   "استلام محل",
}

_ORDER_TYPE_ICONS: Dict[OrderType, str] = {
    OrderType.DINE_IN:  "🍽",
    OrderType.TAKEAWAY: "🥡",
    OrderType.DELIVERY: "🚚",
    OrderType.PICKUP:   "🏪",
}


class PosView(QWidget):
    """Main POS cashier screen.

    Manages:
        • In-memory parked orders (tabs at the top)
        • Category selection → product grid population
        • Order item manipulation via the order panel
        • Order type switching
    """

    # Emitted when user clicks تأكيد (Confirm) — main.py handles save flow
    order_confirmed = pyqtSignal(object)  # Order

    def __init__(
        self,
        product_service: ProductService,
        user_id: int,
        user_name: str,
        cashier_slot: int = 1,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._product_svc = product_service
        self._user_id = user_id
        self._user_name = user_name
        self._cashier_slot = cashier_slot

        # Data caches
        self._categories: List[Category] = []
        self._products_cache: Dict[int, List[Product]] = {}  # cat_id → products
        self._category_colors = get_category_colors()
        self._active_category_id: Optional[int] = None

        # Parked orders
        self._orders: List[Order] = []
        self._active_order_idx: int = -1

        # Build UI
        self._setup_ui()

        # Load categories + products
        self._load_data()

        # Start with a fresh order
        self._new_order()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Parked orders bar
        root.addWidget(self._build_parked_bar())

        # 2. Main body (3 columns)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # RTL: widgets added left→right in code become right→left visually.
        # We want: Categories (right) | Products (centre) | Order (left)
        # In code (LTR order): Order panel | Products | Categories

        # Order panel (will appear on the visual LEFT in RTL = right side of screen)
        self._order_panel = OrderPanel()
        self._order_panel.setFixedWidth(340)
        self._order_panel.quantity_changed.connect(self._on_qty_changed)
        self._order_panel.item_removed.connect(self._on_item_removed)
        self._order_panel.note_changed.connect(self._on_note_changed)
        body.addWidget(self._order_panel)

        # Product grid (centre — stretch)
        self._product_grid = ProductGrid()
        self._product_grid.product_clicked.connect(self._on_product_clicked)
        body.addWidget(self._product_grid, 1)

        # Category sidebar (will appear on visual RIGHT in RTL = left side)
        body.addWidget(self._build_category_sidebar())

        root.addLayout(body, 1)

        # 3. Action bar (bottom)
        root.addWidget(self._build_action_bar())

    # ------------------------------------------------------------------
    # Parked orders bar
    # ------------------------------------------------------------------

    def _build_parked_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-bottom: 1px solid {get_color('border_color')};
            }}
        """)

        self._parked_layout = QHBoxLayout(bar)
        self._parked_layout.setContentsMargins(8, 4, 8, 4)
        self._parked_layout.setSpacing(6)

        # "+" new order button
        new_btn = QPushButton("+")
        new_btn.setObjectName("newOrderBtn")
        new_btn.setFixedSize(40, 36)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton#newOrderBtn {{
                background-color: {get_color('accent_green')};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 20px;
                font-weight: bold;
                min-width: 40px;
                max-width: 40px;
                min-height: 36px;
                max-height: 36px;
                padding: 0px;
            }}
            QPushButton#newOrderBtn:hover {{
                background-color: {get_color('button_confirm')};
            }}
        """)
        new_btn.clicked.connect(self._new_order)
        self._parked_layout.addWidget(new_btn)

        # Spacer to push tabs left (visually right in RTL)
        self._parked_layout.addStretch()

        return bar

    # ------------------------------------------------------------------
    # Category sidebar
    # ------------------------------------------------------------------

    def _build_category_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-right: 1px solid {get_color('border_color')};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)

        # Header
        hdr = QLabel("الأقسام")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setStyleSheet(f"""
            font-size: 15px;
            font-weight: bold;
            color: {get_color('text_secondary')};
            padding-bottom: 6px;
        """)
        layout.addWidget(hdr)

        # Scrollable category buttons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._cat_container = QWidget()
        self._cat_layout = QVBoxLayout(self._cat_container)
        self._cat_layout.setContentsMargins(0, 0, 0, 0)
        self._cat_layout.setSpacing(4)
        self._cat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._cat_container)
        layout.addWidget(scroll, 1)

        return sidebar

    # ------------------------------------------------------------------
    # Action bar (bottom)
    # ------------------------------------------------------------------

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(64)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-top: 1px solid {get_color('border_color')};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Order type selector buttons
        self._type_buttons: Dict[OrderType, QPushButton] = {}
        for otype in OrderType:
            icon = _ORDER_TYPE_ICONS[otype]
            label = _ORDER_TYPE_LABELS[otype]
            btn = QPushButton(f"{icon}  {label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _, t=otype: self._set_order_type(t))
            self._type_buttons[otype] = btn
            layout.addWidget(btn)

        layout.addStretch()

        # Discount button
        self._discount_btn = QPushButton("💰  خصم")
        self._discount_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._discount_btn.setMinimumHeight(44)
        self._discount_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_orange')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #e8700f; }}
        """)
        self._discount_btn.clicked.connect(self._on_discount)
        layout.addWidget(self._discount_btn)

        # Cancel button
        cancel_btn = QPushButton("✕  إلغاء")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setMinimumHeight(44)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_red')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #c82333; }}
        """)
        cancel_btn.clicked.connect(self._on_cancel_order)
        layout.addWidget(cancel_btn)

        # Confirm button
        confirm_btn = QPushButton("✓  تأكيد")
        confirm_btn.setObjectName("confirmBtn")
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setMinimumHeight(44)
        confirm_btn.setMinimumWidth(120)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_green')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 0 20px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #218838; }}
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(confirm_btn)

        return bar

    # ==================================================================
    # Data loading
    # ==================================================================

    def _load_data(self) -> None:
        """Load categories and pre-cache products."""
        try:
            self._categories = self._product_svc.get_categories()
        except Exception as e:
            logger.error("Failed to load categories: %s", e)
            self._categories = []

        self._products_cache.clear()
        for cat in self._categories:
            try:
                prods = self._product_svc.get_products_by_category(cat.id)
                self._products_cache[cat.id] = prods
            except Exception as e:
                logger.error("Failed to load products for cat %s: %s", cat.id, e)
                self._products_cache[cat.id] = []

        self._rebuild_category_buttons()

        # Auto-select the first category
        if self._categories:
            self._select_category(self._categories[0].id)

    def _rebuild_category_buttons(self) -> None:
        """Rebuild the category sidebar buttons."""
        # Clear existing
        while self._cat_layout.count():
            item = self._cat_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self._cat_buttons: Dict[int, QPushButton] = {}
        colors = self._category_colors

        for idx, cat in enumerate(self._categories):
            color = colors[idx % len(colors)] if colors else get_color("accent_blue")
            btn = QPushButton(cat.name)
            btn.setObjectName(f"cat_{cat.id}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(48)
            btn.clicked.connect(lambda _, cid=cat.id: self._select_category(cid))
            self._cat_buttons[cat.id] = btn
            self._cat_layout.addWidget(btn)

        self._cat_layout.addStretch()

    def _select_category(self, category_id: int) -> None:
        """Switch the product grid to show products from *category_id*."""
        self._active_category_id = category_id
        products = self._products_cache.get(category_id, [])
        colors = self._category_colors

        # Find category index for colour
        cat_idx = 0
        for i, c in enumerate(self._categories):
            if c.id == category_id:
                cat_idx = i
                break

        color = colors[cat_idx % len(colors)] if colors else get_color("accent_blue")
        self._product_grid.set_products(products, category_color=color)

        # Update button styles
        for cid, btn in self._cat_buttons.items():
            cidx = next(
                (i for i, c in enumerate(self._categories) if c.id == cid), 0
            )
            c_color = colors[cidx % len(colors)] if colors else get_color("accent_blue")
            if cid == category_id:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {c_color};
                        color: #ffffff;
                        border: none;
                        border-radius: 8px;
                        padding: 8px;
                        font-size: 15px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        color: {get_color('text_secondary')};
                        border: 2px solid {c_color};
                        border-radius: 8px;
                        padding: 8px;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: rgba(255,255,255,0.05);
                        color: {get_color('text_primary')};
                    }}
                """)

    # ==================================================================
    # Order type management
    # ==================================================================

    def _set_order_type(self, otype: OrderType) -> None:
        """Switch the current order's type."""
        order = self._current_order()
        if order is None:
            return

        order.order_type = otype
        self._refresh_type_buttons()
        self._refresh_order_panel()
        logger.debug("Order type set to %s", otype.value)

    def _refresh_type_buttons(self) -> None:
        """Highlight the active order-type button."""
        order = self._current_order()
        active = order.order_type if order else OrderType.DINE_IN

        for otype, btn in self._type_buttons.items():
            if otype == active:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('accent_blue')};
                        color: #ffffff;
                        border: none;
                        border-radius: 8px;
                        padding: 0 14px;
                        font-size: 14px;
                        font-weight: bold;
                        min-height: 44px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('button_neutral')};
                        color: {get_color('text_secondary')};
                        border: none;
                        border-radius: 8px;
                        padding: 0 14px;
                        font-size: 14px;
                        min-height: 44px;
                    }}
                    QPushButton:hover {{
                        color: {get_color('text_primary')};
                        background-color: rgba(255,255,255,0.08);
                    }}
                """)

    # ==================================================================
    # Parked orders management
    # ==================================================================

    def _current_order(self) -> Optional[Order]:
        if 0 <= self._active_order_idx < len(self._orders):
            return self._orders[self._active_order_idx]
        return None

    def _new_order(self) -> None:
        """Create a fresh in-memory order and switch to it."""
        order = Order(
            order_type=OrderType.DINE_IN,
            created_by_id=self._user_id,
            created_by_name=self._user_name,
            cashier_slot=self._cashier_slot,
        )
        self._orders.append(order)
        self._active_order_idx = len(self._orders) - 1
        self._refresh_parked_tabs()
        self._refresh_order_panel()
        self._refresh_type_buttons()
        logger.debug("New order created (parked #%d)", self._active_order_idx)

    def _switch_to_order(self, idx: int) -> None:
        """Switch the active parked order by index."""
        if 0 <= idx < len(self._orders):
            self._active_order_idx = idx
            self._refresh_parked_tabs()
            self._refresh_order_panel()
            self._refresh_type_buttons()

    def _close_order(self, idx: int) -> None:
        """Remove a parked order tab. If it was the active one, switch."""
        if idx < 0 or idx >= len(self._orders):
            return

        # Don't allow closing the last order — always keep one
        if len(self._orders) <= 1:
            self._orders[0] = Order(
                order_type=OrderType.DINE_IN,
                created_by_id=self._user_id,
                created_by_name=self._user_name,
                cashier_slot=self._cashier_slot,
            )
            self._active_order_idx = 0
        else:
            self._orders.pop(idx)
            if self._active_order_idx >= len(self._orders):
                self._active_order_idx = len(self._orders) - 1
            elif self._active_order_idx > idx:
                self._active_order_idx -= 1

        self._refresh_parked_tabs()
        self._refresh_order_panel()
        self._refresh_type_buttons()

    def _refresh_parked_tabs(self) -> None:
        """Rebuild parked order tab buttons."""
        # Remove old tab buttons (keep the + button which is at index 0)
        while self._parked_layout.count() > 2:  # + button and stretch
            item = self._parked_layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()

        # Insert tabs after the + button
        insert_pos = 1
        for idx, order in enumerate(self._orders):
            icon = _ORDER_TYPE_ICONS.get(order.order_type, "🛒")
            item_count = len(order.items)
            label = f"{icon} #{idx + 1}"
            if item_count > 0:
                label += f" ({item_count})"

            tab = QPushButton(label)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setFixedHeight(36)
            tab.setProperty("class", "compact")

            is_active = idx == self._active_order_idx
            if is_active:
                tab.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('accent_blue')};
                        color: #ffffff;
                        border: none;
                        border-radius: 6px;
                        padding: 4px 14px;
                        font-size: 13px;
                        font-weight: bold;
                        min-width: 0px;
                        min-height: 0px;
                        max-height: 36px;
                    }}
                """)
            else:
                tab.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('button_neutral')};
                        color: {get_color('text_secondary')};
                        border: none;
                        border-radius: 6px;
                        padding: 4px 14px;
                        font-size: 13px;
                        min-width: 0px;
                        min-height: 0px;
                        max-height: 36px;
                    }}
                    QPushButton:hover {{
                        background-color: rgba(255,255,255,0.08);
                        color: {get_color('text_primary')};
                    }}
                """)

            tab.clicked.connect(lambda _, i=idx: self._switch_to_order(i))
            self._parked_layout.insertWidget(insert_pos, tab)
            insert_pos += 1

    # ==================================================================
    # Product → Order item flow
    # ==================================================================

    def _on_product_clicked(self, product: Product) -> None:
        """Add a product to the current order (or increment quantity)."""
        order = self._current_order()
        if order is None:
            self._new_order()
            order = self._current_order()

        # Check if item already exists — increment qty
        for item in order.items:
            if item.product_id == product.id:
                item.quantity += 1
                order.recalculate()
                self._refresh_order_panel()
                self._refresh_parked_tabs()
                return

        # New item
        new_item = OrderItem(
            product_id=product.id,
            product_name=product.name,
            quantity=1,
            unit_price=product.price,
        )
        order.items.append(new_item)
        order.recalculate()
        self._refresh_order_panel()
        self._refresh_parked_tabs()

    def _on_qty_changed(self, product_id: int, new_qty: int) -> None:
        """Handle quantity change from order panel."""
        order = self._current_order()
        if order is None:
            return

        for item in order.items:
            if item.product_id == product_id:
                item.quantity = max(1, new_qty)
                break

        order.recalculate()
        self._refresh_order_panel()
        self._refresh_parked_tabs()

    def _on_item_removed(self, product_id: int) -> None:
        """Handle item removal from order panel."""
        order = self._current_order()
        if order is None:
            return

        order.items = [i for i in order.items if i.product_id != product_id]
        order.recalculate()
        self._refresh_order_panel()
        self._refresh_parked_tabs()

    def _on_note_changed(self, product_id: int, note: str) -> None:
        """Handle per-item note change."""
        order = self._current_order()
        if order is None:
            return

        for item in order.items:
            if item.product_id == product_id:
                item.notes = note
                break

    # ==================================================================
    # Order panel sync
    # ==================================================================

    def _refresh_order_panel(self) -> None:
        """Sync the order panel with the current in-memory order."""
        order = self._current_order()
        if order is None:
            self._order_panel.clear()
            return

        self._order_panel.set_items(list(order.items))

        # Compute service charge
        service = round(order.subtotal * (SERVICE_CHARGE_PCT / 100), 2)
        order.service_amount = service

        order.recalculate()

        self._order_panel.set_totals(
            subtotal=order.subtotal,
            service=order.service_amount,
            discount=order.discount_amount,
            delivery_fee=order.delivery_fee,
            total=order.total,
        )

    # ==================================================================
    # Action bar handlers
    # ==================================================================

    def _on_confirm(self) -> None:
        """User clicked تأكيد — validate and emit for saving."""
        order = self._current_order()
        if order is None or not order.items:
            logger.warning("Cannot confirm: no items in order")
            return

        # Dine-in: show table selection grid
        if order.order_type == OrderType.DINE_IN and order.table_no is None:
            self._show_table_grid()
            return

        logger.info(
            "Order confirmed: type=%s, items=%d, total=%.2f",
            order.order_type.value,
            len(order.items),
            order.total,
        )
        self.order_confirmed.emit(order)

        # Remove the confirmed order from parked list and create a fresh one
        self._close_order(self._active_order_idx)

    def _show_table_grid(self) -> None:
        """Show table selection dialog for dine-in orders."""
        dialog = TableGrid(parent=self)

        def on_table_selected(table_no: int) -> None:
            order = self._current_order()
            if order is None:
                return
            order.table_no = table_no
            logger.info("Table %d selected for dine-in order", table_no)
            # Now that we have a table, proceed with confirm
            self.order_confirmed.emit(order)
            self._close_order(self._active_order_idx)

        dialog.table_selected.connect(on_table_selected)
        dialog.exec()

    def _on_cancel_order(self) -> None:
        """Cancel/discard the current in-memory order."""
        order = self._current_order()
        if order is None:
            return

        # If the order has no items, just reset it
        if not order.items:
            return

        # Clear the order
        self._close_order(self._active_order_idx)
        logger.info("In-memory order discarded")

    def _on_discount(self) -> None:
        """Discount button pressed — show PIN dialog for manager override."""
        order = self._current_order()
        if order is None or not order.items:
            return

        dialog = PinDialog(
            title="ادخل PIN المدير لتطبيق الخصم",
            parent=self,
        )

        def on_pin_verified(raw_pin: str) -> None:
            logger.info("Manager PIN verified for discount")
            # TODO: show discount entry dialog
            # For now, just log — discount dialog is Phase 6+

        dialog.pin_verified.connect(on_pin_verified)
        dialog.exec()

    # ==================================================================
    # Public API (for MainWindow / main.py)
    # ==================================================================

    def refresh_products(self) -> None:
        """Reload products from the service (e.g. after manager edits)."""
        self._load_data()
