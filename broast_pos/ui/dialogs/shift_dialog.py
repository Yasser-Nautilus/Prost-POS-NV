"""
Shift management dialog — open, view summary, add expense, close.

States:
    NO_SHIFT  → big "فتح وردية" button
    ACTIVE    → live summary dashboard + expense entry + close button

Business rules from FinancialService:
    - Only one shift active at a time
    - Close requires: manager PIN + summary printed + drivers settled
    - Expenses are immutable after creation
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.core.models.financial import (
    CashTransaction,
    Shift,
    ShiftSummary,
)
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)


class ShiftDialog(QDialog):
    """Modal shift management dialog.

    Usage::

        dialog = ShiftDialog(
            financial_service=financial_svc,
            user_id=current_user.id,
            user_name=current_user.display_name,
        )
        dialog.shift_state_changed.connect(on_shift_change)
        dialog.exec()

    Signals:
        shift_state_changed(bool is_open):
            Emitted when shift is opened or closed.
    """

    shift_state_changed = pyqtSignal(bool)  # is_open

    def __init__(
        self,
        financial_service: FinancialService,
        user_id: int,
        user_name: str = "",
        on_add_expense: Optional[Callable] = None,
        on_close_shift: Optional[Callable] = None,
        on_print_summary: Optional[Callable] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._financial = financial_service
        self._user_id = user_id
        self._user_name = user_name
        self._add_expense_cb = on_add_expense
        self._close_shift_cb = on_close_shift
        self._print_summary_cb = on_print_summary

        self._active_shift: Optional[Shift] = None
        self._summary: Optional[ShiftSummary] = None

        self._setup_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("إدارة الوردية")
        self.setModal(True)
        self.setMinimumSize(480, 520)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('primary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(20, 16, 20, 20)
        self._root.setSpacing(16)

        # Header
        header = QLabel("⏱  إدارة الوردية")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color('text_primary')};
        """)
        self._root.addWidget(header)

        # Content area — swapped based on shift state
        self._content = QVBoxLayout()
        self._root.addLayout(self._content, 1)

        # Close dialog button
        close_btn = QPushButton("✕  إغلاق")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_neutral')};
                color: {get_color('text_secondary')};
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-size: 15px;
                min-height: 44px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.08);
                color: {get_color('text_primary')};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        self._root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _refresh(self) -> None:
        """Load shift state and rebuild content."""
        try:
            self._active_shift = self._financial.ensure_shift_active()
        except ValueError:
            self._active_shift = None

        # Clear old content
        while self._content.count():
            item = self._content.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

        if self._active_shift is None:
            self._build_no_shift_view()
        else:
            self._build_active_shift_view()

    def _clear_layout(self, layout) -> None:
        """Recursively delete layout contents."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    # ------------------------------------------------------------------
    # No shift — open button
    # ------------------------------------------------------------------

    def _build_no_shift_view(self) -> None:
        """Show the 'open shift' state."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # Icon
        icon = QLabel("🔴")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon)

        # Message
        msg = QLabel("لا توجد وردية مفتوحة")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {get_color('text_secondary')};
        """)
        layout.addWidget(msg)

        sub = QLabel("يجب فتح وردية قبل بدء العمل")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('text_muted')};
        """)
        layout.addWidget(sub)

        # Open button
        open_btn = QPushButton("🟢  فتح وردية جديدة")
        open_btn.setObjectName("openShiftBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setMinimumHeight(56)
        open_btn.setMinimumWidth(280)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_green')};
                color: #ffffff;
                border: none;
                border-radius: 12px;
                font-size: 18px;
                font-weight: bold;
                padding: 12px 32px;
            }}
            QPushButton:hover {{
                background-color: {_lighten(get_color('accent_green'), 12)};
            }}
            QPushButton:pressed {{
                background-color: {_darken(get_color('accent_green'), 10)};
            }}
        """)
        open_btn.clicked.connect(self._on_open_shift)
        layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._content.addWidget(container)

    # ------------------------------------------------------------------
    # Active shift — summary dashboard
    # ------------------------------------------------------------------

    def _build_active_shift_view(self) -> None:
        """Show active shift summary with metrics."""
        shift = self._active_shift
        if shift is None:
            return

        # Load summary
        try:
            self._summary = self._financial.get_shift_summary(shift.id)
        except Exception:
            self._summary = ShiftSummary()

        # Shift info bar
        info = QFrame()
        info.setObjectName("infoFrame")
        info.setStyleSheet(f"""
            QFrame#infoFrame {{
                background-color: rgba(40, 167, 69, 0.15);
                border: 1px solid {get_color('accent_green')};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(12, 8, 12, 8)

        status_dot = QLabel("🟢")
        status_dot.setStyleSheet("font-size: 16px;")
        info_layout.addWidget(status_dot)

        status_text = QLabel(f"وردية مفتوحة  —  #{shift.id}")
        status_text.setStyleSheet(f"""
            font-size: 15px;
            font-weight: bold;
            color: {get_color('accent_green')};
        """)
        info_layout.addWidget(status_text)
        info_layout.addStretch()

        opened_at = (shift.opened_at or "")[:16].replace("T", "  ")
        time_lbl = QLabel(f"منذ {opened_at}")
        time_lbl.setStyleSheet(f"""
            font-size: 12px;
            color: {get_color('text_muted')};
        """)
        info_layout.addWidget(time_lbl)

        self._content.addWidget(info)

        # Metrics grid
        s = self._summary
        metrics = [
            ("💰", "المبيعات", f"{s.total_sales:.2f}", "accent_green"),
            ("📤", "المصروفات", f"{s.total_expenses:.2f}", "accent_red"),
            ("⏳", "معلق", f"{s.total_pending:.2f}", "accent_yellow"),
            ("🏦", "المتوقع بالدرج", f"{s.expected_cash:.2f}", "accent_blue"),
        ]

        grid = QGridLayout()
        grid.setSpacing(10)

        for i, (icon, label, value, color_key) in enumerate(metrics):
            card = self._build_metric_card(icon, label, value, color_key)
            row = i // 2
            col = i % 2
            grid.addWidget(card, row, col)

        self._content.addLayout(grid)

        # Order breakdown
        if s.order_breakdown:
            breakdown_lbl = QLabel("تفاصيل الطلبات")
            breakdown_lbl.setStyleSheet(f"""
                font-size: 14px;
                font-weight: bold;
                color: {get_color('text_secondary')};
                margin-top: 4px;
            """)
            self._content.addWidget(breakdown_lbl)

            breakdown_row = QHBoxLayout()
            breakdown_row.setSpacing(8)

            type_labels = {
                "dine_in": "صالة",
                "takeaway": "تيك اواي",
                "delivery": "دليفري",
                "pickup": "استلام",
            }

            for key, data in s.order_breakdown.items():
                if isinstance(data, dict):
                    count = data.get("count", 0)
                    revenue = data.get("revenue", 0.0)
                    label = type_labels.get(key, key)
                    chip = QLabel(f"{label}: {count} ({revenue:.0f})")
                    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    chip.setStyleSheet(f"""
                        background-color: {get_color('secondary_bg')};
                        border: 1px solid {get_color('border_color')};
                        border-radius: 6px;
                        padding: 6px 10px;
                        font-size: 13px;
                        color: {get_color('text_primary')};
                    """)
                    breakdown_row.addWidget(chip)

            self._content.addLayout(breakdown_row)

        # Action buttons
        actions = QHBoxLayout()
        actions.setSpacing(10)

        # Add expense
        expense_btn = QPushButton("📤  إضافة مصروف")
        expense_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        expense_btn.setMinimumHeight(48)
        expense_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_orange')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {_lighten(get_color('accent_orange'), 10)};
            }}
        """)
        expense_btn.clicked.connect(self._on_add_expense)
        actions.addWidget(expense_btn)

        # Print summary
        print_btn = QPushButton("🖨  طباعة التقرير")
        print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        print_btn.setMinimumHeight(48)
        print_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_blue')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {_lighten(get_color('accent_blue'), 10)};
            }}
        """)
        print_btn.clicked.connect(self._on_print_summary)
        actions.addWidget(print_btn)

        self._content.addLayout(actions)

        # Close shift button
        close_shift_btn = QPushButton("🔴  إغلاق الوردية")
        close_shift_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_shift_btn.setMinimumHeight(48)
        close_shift_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_cancel')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {_lighten(get_color('button_cancel'), 10)};
            }}
        """)
        close_shift_btn.clicked.connect(self._on_close_shift)
        self._content.addWidget(close_shift_btn)

    def _build_metric_card(
        self, icon: str, label: str, value: str, color_key: str
    ) -> QFrame:
        """Build a single metric card for the dashboard."""
        card = QFrame()
        card.setObjectName("metricCard")
        card.setStyleSheet(f"""
            QFrame#metricCard {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
                padding: 12px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Icon + label row
        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 18px;")
        top.addWidget(icon_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_secondary')};
        """)
        top.addWidget(name_lbl)
        top.addStretch()
        layout.addLayout(top)

        # Value
        val_lbl = QLabel(f"{value} ج.م")
        val_lbl.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color(color_key)};
        """)
        layout.addWidget(val_lbl)

        return card

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_open_shift(self) -> None:
        """Open a new shift."""
        try:
            shift = self._financial.open_shift(self._user_id)
            logger.info("Shift #%d opened by %s", shift.id, self._user_name)
            self.shift_state_changed.emit(True)
            self._refresh()
        except ValueError as exc:
            logger.warning("Cannot open shift: %s", exc)

    def _on_add_expense(self) -> None:
        """Delegate to expense callback (opens ExpenseDialog)."""
        if self._add_expense_cb:
            self._add_expense_cb()
        self._refresh()

    def _on_print_summary(self) -> None:
        """Mark summary as printed (prerequisite for close)."""
        if self._active_shift is None:
            return
        try:
            self._financial.mark_summary_printed(self._active_shift.id)
            logger.info("Summary marked as printed for shift #%d", self._active_shift.id)
            if self._print_summary_cb:
                self._print_summary_cb(self._active_shift.id)
            self._refresh()
        except Exception as exc:
            logger.warning("Print summary failed: %s", exc)

    def _on_close_shift(self) -> None:
        """Close shift — delegates to callback which shows PIN dialog."""
        if self._close_shift_cb:
            self._close_shift_cb()
        self._refresh()


# ============================================================================
# Colour helpers
# ============================================================================

def _lighten(hex_color: str, amount: int = 10) -> str:
    hex_color = hex_color.lstrip("#")
    r = min(255, int(hex_color[0:2], 16) + amount)
    g = min(255, int(hex_color[2:4], 16) + amount)
    b = min(255, int(hex_color[4:6], 16) + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, amount: int = 10) -> str:
    hex_color = hex_color.lstrip("#")
    r = max(0, int(hex_color[0:2], 16) - amount)
    g = max(0, int(hex_color[2:4], 16) - amount)
    b = max(0, int(hex_color[4:6], 16) - amount)
    return f"#{r:02x}{g:02x}{b:02x}"
