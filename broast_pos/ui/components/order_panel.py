"""
Order panel — live order summary sidebar.

Displays the current order's items with:
    • Product name + quantity + line total
    • Large +/- buttons for quantity (NOT QSpinBox)
    • Per-item notes field
    • Remove (×) button
    • Footer: subtotal, service, discount, delivery_fee, grand total

The panel emits signals for every change; the POS view decides what
to do with them (update the in-memory Order, recalculate totals, etc.).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import get_fonts
from broast_pos.core.models.order import OrderItem
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)


class OrderPanel(QWidget):
    """Sidebar showing the current order items and totals.

    Signals:
        quantity_changed(int product_id, int new_qty):
            Emitted when +/- is pressed.  ``new_qty`` is already clamped ≥ 1.
        item_removed(int product_id):
            Emitted when × is pressed.
        note_changed(int product_id, str note):
            Emitted when the per-item note field loses focus or Enter is pressed.
    """

    quantity_changed = pyqtSignal(int, int)   # product_id, new_qty
    item_removed = pyqtSignal(int)            # product_id
    note_changed = pyqtSignal(int, str)       # product_id, note_text

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: List[OrderItem] = []
        self._subtotal: float = 0.0
        self._service: float = 0.0
        self._discount: float = 0.0
        self._delivery_fee: float = 0.0
        self._total: float = 0.0
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Header ---
        header = QFrame()
        header.setMinimumHeight(40)
        header.setMaximumHeight(56)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-bottom: 1px solid {get_color('border_color')};
                border-radius: 0;
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 12, 0)
        title = QLabel("🛒  الطلب الحالي")
        title.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {get_color('text_primary')};
        """)
        h_layout.addWidget(title)
        h_layout.addStretch()
        self._count_lbl = QLabel("0 عنصر")
        self._count_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_muted')};
        """)
        h_layout.addWidget(self._count_lbl)
        root.addWidget(header)

        # --- Scrollable items area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._items_container = QWidget()
        self._items_container.setStyleSheet(
            "background: transparent; border: none;"
        )
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(8, 8, 8, 8)
        self._items_layout.setSpacing(6)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Empty state
        self._empty_lbl = QLabel("🛒\nاضغط على منتج لإضافته")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setWordWrap(True)
        self._empty_lbl.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('text_muted')};
            padding: 48px 16px;
            background: transparent;
            border: none;
        """)
        self._items_layout.addWidget(self._empty_lbl)

        scroll.setWidget(self._items_container)
        root.addWidget(scroll, 1)

        # --- Totals footer ---
        self._footer = self._build_footer()
        root.addWidget(self._footer)

    def _build_footer(self) -> QFrame:
        """Build the totals breakdown footer."""
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border-top: 1px solid {get_color('border_color')};
                border-radius: 0;
            }}
        """)
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Row builder
        def _row(label_text: str, value_name: str, bold: bool = False) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            style = f"font-size: 14px; color: {get_color('text_secondary')};"
            if bold:
                style = f"font-size: 17px; font-weight: bold; color: {get_color('text_primary')};"
            lbl.setStyleSheet(style)
            row.addWidget(lbl)
            row.addStretch()
            val = QLabel("0")
            val.setObjectName(value_name)
            val.setStyleSheet(style)
            row.addWidget(val)
            layout.addLayout(row)
            return row

        _row("المجموع الفرعي", "lbl_subtotal")
        self._service_row_widget = self._make_optional_row("الخدمة", "lbl_service", layout)
        self._discount_row_widget = self._make_optional_row("الخصم", "lbl_discount", layout)
        self._delivery_row_widget = self._make_optional_row("رسوم التوصيل", "lbl_delivery", layout)

        # Separator
        sep = QFrame()
        sep.setMinimumHeight(1)
        sep.setMaximumHeight(1)
        sep.setStyleSheet(f"background-color: {get_color('border_color')};")
        layout.addWidget(sep)

        _row("الإجمالي", "lbl_total", bold=True)

        return footer

    def _make_optional_row(
        self, label_text: str, obj_name: str, parent_layout: QVBoxLayout
    ) -> QWidget:
        """Create a total row that can be shown/hidden."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"font-size: 14px; color: {get_color('text_secondary')};")
        row_layout.addWidget(lbl)
        row_layout.addStretch()
        val = QLabel("0")
        val.setObjectName(obj_name)
        val.setStyleSheet(f"font-size: 14px; color: {get_color('text_secondary')};")
        row_layout.addWidget(val)
        row_widget.hide()
        parent_layout.addWidget(row_widget)
        return row_widget

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_items(self, items: List[OrderItem]) -> None:
        """Replace the panel contents with the given order items."""
        self._items = items
        self._rebuild_items()

    def set_totals(
        self,
        subtotal: float = 0.0,
        service: float = 0.0,
        discount: float = 0.0,
        delivery_fee: float = 0.0,
        total: float = 0.0,
    ) -> None:
        """Update the footer totals."""
        self._subtotal = subtotal
        self._service = service
        self._discount = discount
        self._delivery_fee = delivery_fee
        self._total = total
        self._update_footer()

    def clear(self) -> None:
        """Reset the panel to empty state."""
        self._items = []
        self._subtotal = self._service = self._discount = 0.0
        self._delivery_fee = self._total = 0.0
        self._rebuild_items()
        self._update_footer()

    # ------------------------------------------------------------------
    # Item list rendering
    # ------------------------------------------------------------------

    def _rebuild_items(self) -> None:
        """Tear down and recreate all item rows."""
        # Clear existing item widgets (skip the empty label)
        while self._items_layout.count() > 1:
            item = self._items_layout.takeAt(0)
            w = item.widget()
            if w and w is not self._empty_lbl:
                w.deleteLater()

        # Also remove the empty label and re-add at end
        self._items_layout.removeWidget(self._empty_lbl)

        if not self._items:
            self._empty_lbl.show()
            self._items_layout.addWidget(self._empty_lbl)
            self._count_lbl.setText("0 عنصر")
            return

        self._empty_lbl.hide()

        for item in self._items:
            row = self._create_item_row(item)
            self._items_layout.addWidget(row)

        # Add empty label back (hidden) at the end
        self._items_layout.addWidget(self._empty_lbl)

        total_qty = sum(i.quantity for i in self._items)
        self._count_lbl.setText(f"{total_qty} عنصر" if total_qty != 1 else "1 عنصر")

    def _create_item_row(self, item: OrderItem) -> QFrame:
        """Build a single item card: name, qty controls, price, notes, remove."""
        card = QFrame()
        card.setObjectName(f"item_{item.product_id}")
        card.setStyleSheet(f"""
            QFrame#item_{item.product_id} {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 8px;
                padding: 6px;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # --- Row 1: Name + line total ---
        top_row = QHBoxLayout()
        name_lbl = QLabel(item.product_name)
        name_lbl.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {get_color('text_primary')};
        """)
        name_lbl.setWordWrap(True)
        top_row.addWidget(name_lbl, 1)

        line_total = QLabel(f"{item.total_price:.0f} ج.م")
        line_total.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {get_color('accent_green')};
        """)
        top_row.addWidget(line_total)
        card_layout.addLayout(top_row)

        # --- Row 2: Qty controls + unit price + remove ---
        ctrl_row = QHBoxLayout()

        # Minus button
        minus_btn = QPushButton("−")
        minus_btn.setMinimumSize(32, 32)
        minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        minus_btn.setProperty("class", "compact")
        minus_btn.setStyleSheet(self._qty_btn_style())
        minus_btn.clicked.connect(
            lambda _, pid=item.product_id, qty=item.quantity:
                self.quantity_changed.emit(pid, max(1, qty - 1))
        )
        ctrl_row.addWidget(minus_btn)

        # Quantity label
        qty_lbl = QLabel(str(item.quantity))
        qty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty_lbl.setMinimumWidth(28)
        qty_lbl.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {get_color('text_primary')};
        """)
        ctrl_row.addWidget(qty_lbl)

        # Plus button
        plus_btn = QPushButton("+")
        plus_btn.setMinimumSize(32, 32)
        plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        plus_btn.setProperty("class", "compact")
        plus_btn.setStyleSheet(self._qty_btn_style())
        plus_btn.clicked.connect(
            lambda _, pid=item.product_id, qty=item.quantity:
                self.quantity_changed.emit(pid, qty + 1)
        )
        ctrl_row.addWidget(plus_btn)

        # Unit price hint
        unit_lbl = QLabel(f"× {item.unit_price:.0f}")
        unit_lbl.setStyleSheet(f"""
            font-size: 12px;
            color: {get_color('text_muted')};
            margin-right: 8px;
        """)
        ctrl_row.addWidget(unit_lbl)

        ctrl_row.addStretch()

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setMinimumSize(24, 24)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setProperty("class", "compact")
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {get_color('accent_red')};
                border: 1px solid {get_color('accent_red')};
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                min-width: 24px;
                max-width: 36px;
                min-height: 24px;
                max-height: 36px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: rgba(220, 53, 69, 0.2);
            }}
        """)
        remove_btn.clicked.connect(
            lambda _, pid=item.product_id: self.item_removed.emit(pid)
        )
        ctrl_row.addWidget(remove_btn)

        card_layout.addLayout(ctrl_row)

        # --- Row 3: Notes field ---
        notes_input = QLineEdit()
        notes_input.setPlaceholderText("ملاحظة …")
        notes_input.setText(item.notes or "")
        notes_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('input_bg')};
                color: {get_color('text_primary')};
                border: 1px solid {get_color('border_color')};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 28px;
            }}
            QLineEdit:focus {{
                border-color: {get_color('accent_blue')};
            }}
        """)
        notes_input.editingFinished.connect(
            lambda pid=item.product_id, inp=notes_input:
                self.note_changed.emit(pid, inp.text().strip())
        )
        card_layout.addWidget(notes_input)

        return card

    # ------------------------------------------------------------------
    # Footer updates
    # ------------------------------------------------------------------

    def _update_footer(self) -> None:
        """Sync footer labels with current totals."""
        self._find_label("lbl_subtotal").setText(f"{self._subtotal:.0f} ج.م")
        self._find_label("lbl_total").setText(f"{self._total:.0f} ج.م")

        # Show/hide optional rows
        svc = self._find_label("lbl_service")
        if self._service > 0:
            svc.setText(f"+{self._service:.0f} ج.م")
            self._service_row_widget.show()
        else:
            self._service_row_widget.hide()

        disc = self._find_label("lbl_discount")
        if self._discount > 0:
            disc.setText(f"−{self._discount:.0f} ج.م")
            self._discount_row_widget.show()
        else:
            self._discount_row_widget.hide()

        dlv = self._find_label("lbl_delivery")
        if self._delivery_fee > 0:
            dlv.setText(f"+{self._delivery_fee:.0f} ج.م")
            self._delivery_row_widget.show()
        else:
            self._delivery_row_widget.hide()

    def _find_label(self, name: str) -> QLabel:
        """Find a QLabel in the footer by objectName."""
        lbl = self._footer.findChild(QLabel, name)
        if lbl is None:
            # Fallback — return a dummy so we don't crash
            lbl = QLabel()
        return lbl

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    @staticmethod
    def _qty_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: {get_color('button_neutral')};
                color: {get_color('text_primary')};
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
                min-width: 32px;
                max-width: 44px;
                min-height: 32px;
                max-height: 44px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {get_color('accent_blue')};
            }}
            QPushButton:pressed {{
                background-color: {get_color('border_color')};
            }}
        """
