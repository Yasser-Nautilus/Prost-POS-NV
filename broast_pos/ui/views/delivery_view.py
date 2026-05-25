"""
Delivery view — 3-panel driver lifecycle, trip dispatch, and settlement.

Layout (RTL):
    ┌────────────┬──────────────────────┬─────────────────┐
    │  Drivers   │  Orders & Trips      │  Settlement     │
    │  (left)    │  (center)            │  (right)        │
    │            │                      │                 │
    │ ✅ Ahmad   │ Tab: Unassigned      │  Trip #12       │
    │ 🚗 Khaled  │ Tab: Active          │  Orders: 3      │
    │ ⬜ Salem   │ Tab: Unsettled       │  Cash: 450      │
    │            │                      │  Fees: 60       │
    │ [Check In] │ [Create Trip]        │  [Settle]       │
    │ [Check Out]│ [Dispatch] [Return]  │  [Print]        │
    ├────────────┴──────────────────────┴─────────────────┤
    │  End-of-Day Summary (bottom)                        │
    └─────────────────────────────────────────────────────┘

Features:
    • Driver check-in/out with status indicators
    • Unassigned delivery orders list
    • Trip creation, dispatch, return lifecycle
    • Per-trip settlement with cash/online breakdown
    • End-of-day driver summary with print
    • Auto-refresh every 10 seconds
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import TRACKING_REFRESH_SECONDS
from broast_pos.features.delivery_system.delivery_controller import (
    DeliveryController,
)
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

# Status icons
_DRIVER_ICONS = {
    "available": "✅",
    "out": "🚗",
    "checked_out": "⬜",
}


# ============================================================================
# DeliveryView
# ============================================================================


class DeliveryView(QWidget):
    """3-panel delivery management screen.

    Signals:
        navigate_to_users: emitted when "Add Driver" is clicked (manager).
    """

    navigate_to_users = pyqtSignal()

    def __init__(
        self,
        delivery_controller: DeliveryController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctrl = delivery_controller
        self._selected_orders: List[int] = []
        self._selected_driver_id: Optional[int] = None
        self._selected_trip_id: Optional[int] = None

        self._setup_ui()
        self._start_auto_refresh()
        self._refresh_all()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        # Main 3-panel area
        panels = QHBoxLayout()
        panels.setSpacing(8)

        panels.addWidget(self._build_driver_panel(), 1)
        panels.addWidget(self._build_center_panel(), 2)
        panels.addWidget(self._build_settlement_panel(), 2)

        root.addLayout(panels, 1)

        # Bottom: end-of-day summary
        root.addWidget(self._build_summary_bar())

    # ------------------------------------------------------------------
    # Panel 1: Drivers (Left)
    # ------------------------------------------------------------------

    def _build_driver_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("🚚  السائقين")
        title.setStyleSheet(f"""
            font-size: 16px; font-weight: bold;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        layout.addWidget(title)

        # Driver list
        self._driver_list = QListWidget()
        self._driver_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {get_color('primary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 6px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 10px 8px;
                border-radius: 6px;
                margin: 2px 0;
                color: {get_color('text_primary')};
            }}
            QListWidget::item:selected {{
                background-color: {get_color('accent_blue')};
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba(255,255,255,0.05);
            }}
        """)
        self._driver_list.currentRowChanged.connect(self._on_driver_selected)
        layout.addWidget(self._driver_list, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._checkin_btn = QPushButton("تسجيل حضور")
        self._checkin_btn.setProperty("class", "confirm")
        self._checkin_btn.clicked.connect(self._on_check_in)
        btn_row.addWidget(self._checkin_btn)

        self._checkout_btn = QPushButton("تسجيل انصراف")
        self._checkout_btn.setProperty("class", "danger")
        self._checkout_btn.clicked.connect(self._on_check_out)
        btn_row.addWidget(self._checkout_btn)

        layout.addLayout(btn_row)

        return panel

    # ------------------------------------------------------------------
    # Panel 2: Orders & Trips (Center)
    # ------------------------------------------------------------------

    def _build_center_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Tab widget
        self._center_tabs = QTabWidget()
        self._center_tabs.setStyleSheet(f"""
            QTabBar::tab {{
                padding: 8px 16px;
                font-size: 13px;
            }}
        """)

        # Tab 1: Unassigned orders
        self._unassigned_list = QListWidget()
        self._unassigned_list.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection
        )
        self._style_list_widget(self._unassigned_list)
        self._center_tabs.addTab(self._unassigned_list, "📦 طلبات غير مسندة")

        # Tab 2: Active trips
        self._active_trips_list = QListWidget()
        self._style_list_widget(self._active_trips_list)
        self._active_trips_list.currentRowChanged.connect(
            self._on_active_trip_selected
        )
        self._center_tabs.addTab(self._active_trips_list, "🚗 رحلات نشطة")

        # Tab 3: Unsettled trips
        self._unsettled_list = QListWidget()
        self._style_list_widget(self._unsettled_list)
        self._unsettled_list.currentRowChanged.connect(
            self._on_unsettled_trip_selected
        )
        self._center_tabs.addTab(self._unsettled_list, "💰 غير محسوبة")

        layout.addWidget(self._center_tabs, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._create_trip_btn = QPushButton("إنشاء رحلة")
        self._create_trip_btn.setProperty("class", "confirm")
        self._create_trip_btn.clicked.connect(self._on_create_trip)
        btn_row.addWidget(self._create_trip_btn)

        self._dispatch_btn = QPushButton("إرسال")
        self._dispatch_btn.setProperty("class", "accent")
        self._dispatch_btn.clicked.connect(self._on_dispatch)
        btn_row.addWidget(self._dispatch_btn)

        self._return_btn = QPushButton("تسجيل عودة")
        self._return_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_orange')};
                color: #fff; border: none; border-radius: 8px;
                padding: 10px 16px; font-size: 14px;
                min-height: 44px;
            }}
            QPushButton:hover {{ background-color: #e8710a; }}
        """)
        self._return_btn.clicked.connect(self._on_mark_returned)
        btn_row.addWidget(self._return_btn)

        layout.addLayout(btn_row)

        return panel

    # ------------------------------------------------------------------
    # Panel 3: Settlement (Right)
    # ------------------------------------------------------------------

    def _build_settlement_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("💰  التسوية")
        title.setStyleSheet(f"""
            font-size: 16px; font-weight: bold;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        layout.addWidget(title)

        # Settlement details area (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._settlement_content = QWidget()
        self._settlement_layout = QVBoxLayout(self._settlement_content)
        self._settlement_layout.setContentsMargins(0, 0, 0, 0)
        self._settlement_layout.setSpacing(6)
        self._settlement_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Placeholder
        self._settlement_placeholder = QLabel("اختر رحلة غير محسوبة للتسوية")
        self._settlement_placeholder.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._settlement_placeholder.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('text_muted')};
            background: transparent;
            padding: 40px;
        """)
        self._settlement_layout.addWidget(self._settlement_placeholder)

        scroll.setWidget(self._settlement_content)
        layout.addWidget(scroll, 1)

        # Settlement action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._settle_btn = QPushButton("تأكيد التسوية")
        self._settle_btn.setProperty("class", "confirm")
        self._settle_btn.setEnabled(False)
        self._settle_btn.clicked.connect(self._on_settle)
        btn_row.addWidget(self._settle_btn)

        self._print_settle_btn = QPushButton("🖨 طباعة إيصال")
        self._print_settle_btn.setEnabled(False)
        self._print_settle_btn.clicked.connect(self._on_settle_print)
        btn_row.addWidget(self._print_settle_btn)

        layout.addLayout(btn_row)

        return panel

    # ------------------------------------------------------------------
    # Bottom: End-of-day summary bar
    # ------------------------------------------------------------------

    def _build_summary_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)

        title = QLabel("📊  ملخص اليوم")
        title.setStyleSheet(f"""
            font-size: 14px; font-weight: bold;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        layout.addWidget(title)

        self._summary_label = QLabel("—")
        self._summary_label.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_secondary')};
            background: transparent;
        """)
        layout.addWidget(self._summary_label, 1)

        print_btn = QPushButton("🖨 طباعة ملخص")
        print_btn.setFixedHeight(36)
        print_btn.clicked.connect(self._on_print_summary)
        layout.addWidget(print_btn)

        return bar

    # ------------------------------------------------------------------
    # List widget helper
    # ------------------------------------------------------------------

    def _style_list_widget(self, lw: QListWidget) -> None:
        lw.setStyleSheet(f"""
            QListWidget {{
                background-color: {get_color('primary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 6px; padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px; border-radius: 6px;
                margin: 2px 0;
                color: {get_color('text_primary')};
            }}
            QListWidget::item:selected {{
                background-color: {get_color('accent_blue')};
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba(255,255,255,0.05);
            }}
        """)

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _start_auto_refresh(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(TRACKING_REFRESH_SECONDS * 1000)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start()

    def _refresh_all(self) -> None:
        self._refresh_drivers()
        self._refresh_unassigned()
        self._refresh_active_trips()
        self._refresh_unsettled()
        self._refresh_summary()

    # ------------------------------------------------------------------
    # Data: Drivers
    # ------------------------------------------------------------------

    _driver_data: List[Dict[str, Any]] = []

    def _refresh_drivers(self) -> None:
        from broast_pos.data.repositories.user_repository import UserRepository
        from broast_pos.data.database.connection import DatabaseConnection

        self._driver_list.blockSignals(True)
        prev_row = self._driver_list.currentRow()
        self._driver_list.clear()

        # Get all drivers (users with no cashier_slot)
        try:
            db = DatabaseConnection.get_instance()
            user_repo = UserRepository(db)
            all_drivers = user_repo.get_drivers()
        except Exception:
            all_drivers = []

        # Get active (checked-in) driver IDs
        active = self._ctrl.get_active_drivers()
        active_ids = {d["id"] for d in active}
        active_status = {d["id"]: d["status"] for d in active}

        self._driver_data = []
        for driver in all_drivers:
            if driver.id in active_ids:
                status = active_status.get(driver.id, "available")
            else:
                status = "checked_out"

            icon = _DRIVER_ICONS.get(status, "⬜")
            name = driver.display_name or driver.username
            item = QListWidgetItem(f"{icon}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, driver.id)
            self._driver_list.addItem(item)
            self._driver_data.append(
                {"id": driver.id, "name": name, "status": status}
            )

        if 0 <= prev_row < self._driver_list.count():
            self._driver_list.setCurrentRow(prev_row)
        self._driver_list.blockSignals(False)

    def _on_driver_selected(self, row: int) -> None:
        if 0 <= row < len(self._driver_data):
            self._selected_driver_id = self._driver_data[row]["id"]
        else:
            self._selected_driver_id = None

    def _on_check_in(self) -> None:
        if self._selected_driver_id is None:
            return
        ok, msg = self._ctrl.check_in_driver(self._selected_driver_id)
        if not ok:
            self._show_error(msg)
        self._refresh_drivers()

    def _on_check_out(self) -> None:
        if self._selected_driver_id is None:
            return
        ok, msg = self._ctrl.check_out_driver(self._selected_driver_id)
        if not ok:
            self._show_error(msg)
        self._refresh_drivers()

    # ------------------------------------------------------------------
    # Data: Unassigned orders
    # ------------------------------------------------------------------

    _unassigned_data: List[Dict[str, Any]] = []

    def _refresh_unassigned(self) -> None:
        self._unassigned_list.blockSignals(True)
        self._unassigned_list.clear()
        self._unassigned_data = self._ctrl.get_unassigned_deliveries()

        for o in self._unassigned_data:
            pay = "كاش" if o["payment_method"] == "cash" else "اونلاين"
            text = (
                f"#{o['invoice_no']}  •  {o.get('customer_name', '')}  "
                f"•  {o['total']:.0f} ج.م  ({pay})"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, o["id"])
            self._unassigned_list.addItem(item)

        self._unassigned_list.blockSignals(False)

    # ------------------------------------------------------------------
    # Data: Active trips
    # ------------------------------------------------------------------

    _active_trip_data: List[Dict[str, Any]] = []

    def _refresh_active_trips(self) -> None:
        self._active_trips_list.blockSignals(True)
        prev = self._active_trips_list.currentRow()
        self._active_trips_list.clear()
        self._active_trip_data = self._ctrl.get_active_trips()

        status_labels = {
            "pending": "⏳ بانتظار الإرسال",
            "dispatched": "🚗 خارج للتوصيل",
            "returned": "✅ عاد",
        }

        for t in self._active_trip_data:
            st = status_labels.get(t["status"], t["status"])
            text = (
                f"رحلة #{t['id']}  •  {t['driver_name']}  "
                f"•  {t['order_count']} طلب  •  {st}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self._active_trips_list.addItem(item)

        if 0 <= prev < self._active_trips_list.count():
            self._active_trips_list.setCurrentRow(prev)
        self._active_trips_list.blockSignals(False)

    def _on_active_trip_selected(self, row: int) -> None:
        if 0 <= row < len(self._active_trip_data):
            self._selected_trip_id = self._active_trip_data[row]["id"]

    # ------------------------------------------------------------------
    # Data: Unsettled trips
    # ------------------------------------------------------------------

    _unsettled_data: List[Dict[str, Any]] = []

    def _refresh_unsettled(self) -> None:
        self._unsettled_list.blockSignals(True)
        prev = self._unsettled_list.currentRow()
        self._unsettled_list.clear()
        self._unsettled_data = self._ctrl.get_unsettled_trips()

        for t in self._unsettled_data:
            text = (
                f"رحلة #{t['id']}  •  {t['driver_name']}  "
                f"•  {t['order_count']} طلب"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self._unsettled_list.addItem(item)

        if 0 <= prev < self._unsettled_list.count():
            self._unsettled_list.setCurrentRow(prev)
        self._unsettled_list.blockSignals(False)

    def _on_unsettled_trip_selected(self, row: int) -> None:
        if 0 <= row < len(self._unsettled_data):
            trip_id = self._unsettled_data[row]["id"]
            self._selected_trip_id = trip_id
            self._load_settlement_details(trip_id)
        else:
            self._selected_trip_id = None
            self._clear_settlement()

    # ------------------------------------------------------------------
    # Trip actions
    # ------------------------------------------------------------------

    def _on_create_trip(self) -> None:
        if self._selected_driver_id is None:
            self._show_error("اختر سائق أولاً")
            return

        selected_items = self._unassigned_list.selectedItems()
        if not selected_items:
            self._show_error("اختر طلب واحد على الأقل")
            return

        order_ids = [
            item.data(Qt.ItemDataRole.UserRole) for item in selected_items
        ]
        ok, msg = self._ctrl.create_trip(self._selected_driver_id, order_ids)
        if ok:
            self._refresh_all()
        else:
            self._show_error(msg)

    def _on_dispatch(self) -> None:
        if self._selected_trip_id is None:
            self._show_error("اختر رحلة أولاً")
            return
        ok, msg = self._ctrl.dispatch_trip(self._selected_trip_id)
        if ok:
            self._refresh_all()
        else:
            self._show_error(msg)

    def _on_mark_returned(self) -> None:
        if self._selected_trip_id is None:
            self._show_error("اختر رحلة أولاً")
            return
        ok, msg = self._ctrl.mark_returned(self._selected_trip_id)
        if ok:
            self._refresh_all()
        else:
            self._show_error(msg)

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------

    def _load_settlement_details(self, trip_id: int) -> None:
        details = self._ctrl.get_settlement_details(trip_id)
        if details is None:
            self._clear_settlement()
            return

        # Clear old content
        self._clear_settlement_layout()

        # Trip header
        header = QLabel(
            f"رحلة #{details['trip_id']}  —  {details['driver_name']}"
        )
        header.setStyleSheet(f"""
            font-size: 15px; font-weight: bold;
            color: {get_color('text_primary')};
            background: transparent;
        """)
        self._settlement_layout.addWidget(header)

        # Orders breakdown
        for o in details.get("orders", []):
            pay_label = (
                "كاش" if o["payment_method"] == "cash" else "مدفوع اونلاين"
            )
            collected = f"{o['collected']:.0f}" if o["collected"] else "—"
            card = QLabel(
                f"  #{o['invoice_no']}  •  {o['total']:.0f} ج.م  "
                f"•  {pay_label}  •  محصّل: {collected}"
            )
            card.setStyleSheet(f"""
                font-size: 13px;
                color: {get_color('text_secondary')};
                background-color: {get_color('primary_bg')};
                border-radius: 6px;
                padding: 8px;
            """)
            card.setWordWrap(True)
            self._settlement_layout.addWidget(card)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(
            f"background-color: {get_color('border_color')};"
        )
        self._settlement_layout.addWidget(sep)

        # Summary
        summary_items = [
            ("نقدي محصّل", f"{details['cash_collected']:.0f} ج.م"),
            ("رسوم توصيل", f"{details['total_delivery_fees']:.0f} ج.م"),
            ("المبلغ المسلّم", f"{details['amount_to_hand_over']:.0f} ج.م"),
        ]
        for label_text, value_text in summary_items:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"""
                font-size: 14px;
                color: {get_color('text_secondary')};
                background: transparent;
            """)
            val = QLabel(value_text)
            val.setStyleSheet(f"""
                font-size: 14px; font-weight: bold;
                color: {get_color('accent_green')};
                background: transparent;
            """)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            self._settlement_layout.addLayout(row)

        self._settle_btn.setEnabled(True)
        self._print_settle_btn.setEnabled(True)

    def _clear_settlement(self) -> None:
        self._clear_settlement_layout()
        self._settlement_layout.addWidget(self._settlement_placeholder)
        self._settle_btn.setEnabled(False)
        self._print_settle_btn.setEnabled(False)

    def _clear_settlement_layout(self) -> None:
        # Remove placeholder if present
        if self._settlement_placeholder.parent() == self._settlement_content:
            self._settlement_layout.removeWidget(self._settlement_placeholder)

        while self._settlement_layout.count():
            item = self._settlement_layout.takeAt(0)
            w = item.widget()
            if w and w is not self._settlement_placeholder:
                w.deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

    def _on_settle(self) -> None:
        if self._selected_trip_id is None:
            return
        ok, msg = self._ctrl.settle_trip(self._selected_trip_id)
        if ok:
            self._selected_trip_id = None
            self._clear_settlement()
            self._refresh_all()
        else:
            self._show_error(msg)

    def _on_settle_print(self) -> None:
        if self._selected_trip_id is None:
            return
        ok, msg = self._ctrl.settle_trip(
            self._selected_trip_id, print_receipt=True
        )
        if ok:
            self._selected_trip_id = None
            self._clear_settlement()
            self._refresh_all()
        else:
            self._show_error(msg)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _refresh_summary(self) -> None:
        summary = self._ctrl.get_daily_summary()
        if not summary:
            self._summary_label.setText("لا توجد بيانات لليوم")
            return

        total_trips = sum(s.get("trip_count", 0) for s in summary)
        total_orders = sum(s.get("order_count", 0) for s in summary)
        total_fees = sum(s.get("fees_earned", 0) for s in summary)
        drivers = len(summary)

        self._summary_label.setText(
            f"سائقين: {drivers}  •  رحلات: {total_trips}  "
            f"•  طلبات: {total_orders}  "
            f"•  رسوم التوصيل: {total_fees:.0f} ج.م"
        )

    def _on_print_summary(self) -> None:
        ok = self._ctrl.print_daily_summary()
        if not ok:
            self._show_error("فشلت عملية الطباعة")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_all()

    def _show_error(self, msg: str) -> None:
        QMessageBox.warning(self, "خطأ", msg)
