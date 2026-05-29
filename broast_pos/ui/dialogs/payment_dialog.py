"""
Payment dialog — كاش / فيزا / اونلاين method picker + cash calculator.

Flow:
    1. User taps a payment method button (cash, visa, online)
    2. If CASH → numpad appears to enter amount received → shows change
    3. If VISA / ONLINE → confirm immediately (amount_paid = total)

Business rules:
    - Visa is NOT available for delivery orders
    - Online is NOT available for dine-in or takeaway
    - Cash change = amount_received - order_total

Emits:
    payment_confirmed(str method, float amount_received)
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.core.models.order import OrderType
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

_NUMPAD_KEYS = [
    ("7", "8", "9"),
    ("4", "5", "6"),
    ("1", "2", "3"),
    (".", "0", "⌫"),
]


class PaymentDialog(QDialog):
    """Modal payment dialog — select method, enter cash amount.

    Usage::

        dialog = PaymentDialog(total=250.0, order_type=OrderType.TAKEAWAY)
        dialog.payment_confirmed.connect(on_payment)
        dialog.exec()

    Signals:
        payment_confirmed(str method, float amount_received):
            Emitted when payment is finalised.
    """

    payment_confirmed = pyqtSignal(str, float)  # method, amount_received

    def __init__(
        self,
        total: float,
        order_type: OrderType = OrderType.TAKEAWAY,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._total = total
        self._order_type = order_type
        self._input_str = ""
        self._selected_method: Optional[str] = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("الدفع")
        self.setModal(True)
        self.setFixedSize(420, 640)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('primary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(14)

        # Total display
        total_lbl = QLabel(f"المجموع:  {self._total:.2f} ج.م")
        total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        total_lbl.setStyleSheet(f"""
            font-size: 22px;
            font-weight: bold;
            color: {get_color('accent_yellow')};
            padding: 10px;
            background-color: {get_color('secondary_bg')};
            border-radius: 10px;
        """)
        root.addWidget(total_lbl)

        # Payment method buttons
        methods_lbl = QLabel("طريقة الدفع")
        methods_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        methods_lbl.setStyleSheet(f"font-size: 14px; color: {get_color('text_secondary')};")
        root.addWidget(methods_lbl)

        methods_row = QHBoxLayout()
        methods_row.setSpacing(10)

        # Build method buttons with availability rules
        self._method_buttons = {}
        methods = [
            ("cash", "💵  كاش", True),
            ("visa", "💳  فيزا", self._order_type != OrderType.DELIVERY),
            ("online", "📱  اونلاين", self._order_type == OrderType.DELIVERY),
        ]
        for method_key, label, enabled in methods:
            btn = QPushButton(label)
            btn.setObjectName(f"pay_{method_key}")
            btn.setEnabled(enabled)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(50)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(self._method_btn_style(active=False, enabled=enabled))
            btn.clicked.connect(lambda _, m=method_key: self._on_method_select(m))
            methods_row.addWidget(btn)
            self._method_buttons[method_key] = btn

        root.addLayout(methods_row)

        # Cash input section (hidden until cash selected)
        self._cash_section = QWidget()
        cash_layout = QVBoxLayout(self._cash_section)
        cash_layout.setContentsMargins(0, 0, 0, 0)
        cash_layout.setSpacing(10)

        # Amount display
        self._amount_display = QLabel("0")
        self._amount_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._amount_display.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {get_color('text_primary')};
            background-color: {get_color('input_bg')};
            border: 2px solid {get_color('border_color')};
            border-radius: 8px;
            padding: 10px;
            min-height: 44px;
        """)
        cash_layout.addWidget(self._amount_display)

        # Change display
        self._change_lbl = QLabel("")
        self._change_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._change_lbl.setStyleSheet(f"""
            font-size: 16px;
            color: {get_color('accent_green')};
            min-height: 24px;
        """)
        cash_layout.addWidget(self._change_lbl)

        # Quick amount buttons
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_amounts = [50, 100, 200, 500]
        for amt in quick_amounts:
            qbtn = QPushButton(str(amt))
            qbtn.setMinimumHeight(40)
            qbtn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            qbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            qbtn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color('secondary_bg')};
                    border: 1px solid {get_color('border_color')};
                    border-radius: 6px;
                    color: {get_color('text_primary')};
                    font-size: 15px;
                    min-width: 0px;
                    min-height: 0px;
                    padding: 0px;
                }}
                QPushButton:hover {{
                    background-color: {get_color('accent_blue')};
                }}
            """)
            qbtn.clicked.connect(lambda _, a=amt: self._on_quick_amount(a))
            quick_row.addWidget(qbtn)

        # Exact amount button
        exact_btn = QPushButton("المبلغ بالضبط")
        exact_btn.setMinimumHeight(40)
        exact_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        exact_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exact_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_blue')};
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-size: 14px;
                min-width: 0px;
                min-height: 0px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {get_color('accent_blue')};
                opacity: 0.9;
            }}
        """)
        exact_btn.clicked.connect(self._on_exact_amount)
        quick_row.addWidget(exact_btn)

        cash_layout.addLayout(quick_row)

        # Numpad grid
        numpad = QGridLayout()
        numpad.setSpacing(6)
        for r, row_keys in enumerate(_NUMPAD_KEYS):
            for c, key in enumerate(row_keys):
                nbtn = QPushButton(key)
                nbtn.setMinimumSize(60, 50)
                nbtn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                nbtn.setCursor(Qt.CursorShape.PointingHandCursor)
                nbtn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('secondary_bg')};
                        border: 1px solid {get_color('border_color')};
                        border-radius: 8px;
                        color: {get_color('text_primary')};
                        font-size: 20px;
                        font-weight: bold;
                        min-width: 0px;
                        min-height: 0px;
                        padding: 0px;
                    }}
                    QPushButton:hover {{
                        background-color: rgba(255,255,255,0.08);
                    }}
                    QPushButton:pressed {{
                        background-color: rgba(255,255,255,0.15);
                    }}
                """)
                nbtn.clicked.connect(lambda _, k=key: self._on_numpad(k))
                numpad.addWidget(nbtn, r, c)
        cash_layout.addLayout(numpad)

        self._cash_section.setVisible(False)
        root.addWidget(self._cash_section)

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        cancel_btn = QPushButton("✕  إلغاء")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setMinimumHeight(48)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        self._confirm_btn = QPushButton("✓  تأكيد الدفع")
        self._confirm_btn.setObjectName("confirmBtn")
        self._confirm_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.setMinimumHeight(48)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._on_confirm)
        bottom.addWidget(self._confirm_btn)

        root.addLayout(bottom)

    # ------------------------------------------------------------------
    # Method selection
    # ------------------------------------------------------------------

    def _on_method_select(self, method: str) -> None:
        """Highlight selected method, show/hide cash numpad."""
        self._selected_method = method

        # Update button styles
        for key, btn in self._method_buttons.items():
            if not btn.isEnabled():
                continue
            btn.setStyleSheet(self._method_btn_style(
                active=(key == method),
                enabled=True,
            ))

        # Cash: show numpad
        if method == "cash":
            self._cash_section.setVisible(True)
            self._confirm_btn.setEnabled(False)
            self._input_str = ""
            self._update_display()
        else:
            # Visa / Online → ready to confirm immediately
            self._cash_section.setVisible(False)
            self._confirm_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Cash numpad
    # ------------------------------------------------------------------

    def _on_numpad(self, key: str) -> None:
        """Handle numpad key press."""
        if key == "⌫":
            self._input_str = self._input_str[:-1]
        elif key == ".":
            if "." not in self._input_str:
                self._input_str += "."
        else:
            # Limit to 2 decimal places
            if "." in self._input_str:
                parts = self._input_str.split(".")
                if len(parts[1]) >= 2:
                    return
            self._input_str += key
        self._update_display()

    def _on_quick_amount(self, amount: int) -> None:
        """Set the input to a quick preset amount."""
        self._input_str = str(amount)
        self._update_display()

    def _on_exact_amount(self) -> None:
        """Set input to the exact order total."""
        self._input_str = f"{self._total:.2f}"
        self._update_display()

    def _update_display(self) -> None:
        """Refresh the amount display and change label."""
        display_val = self._input_str or "0"
        self._amount_display.setText(display_val)

        try:
            entered = float(display_val) if display_val else 0.0
        except ValueError:
            entered = 0.0

        if entered >= self._total:
            change = entered - self._total
            self._change_lbl.setText(f"الباقي:  {change:.2f} ج.م")
            self._change_lbl.setStyleSheet(f"""
                font-size: 16px;
                color: {get_color('accent_green')};
                min-height: 24px;
            """)
            self._confirm_btn.setEnabled(True)
        elif entered > 0:
            remaining = self._total - entered
            self._change_lbl.setText(f"متبقي:  {remaining:.2f} ج.م")
            self._change_lbl.setStyleSheet(f"""
                font-size: 16px;
                color: {get_color('accent_red')};
                min-height: 24px;
            """)
            self._confirm_btn.setEnabled(False)
        else:
            self._change_lbl.setText("")
            self._confirm_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    def _on_confirm(self) -> None:
        """Emit payment_confirmed with method + amount."""
        if self._selected_method is None:
            return

        if self._selected_method == "cash":
            try:
                amount = float(self._input_str) if self._input_str else 0.0
            except ValueError:
                return
            if amount < self._total:
                return
        else:
            amount = self._total

        logger.info(
            "Payment confirmed: %s, amount=%.2f, total=%.2f",
            self._selected_method, amount, self._total,
        )
        self.payment_confirmed.emit(self._selected_method, amount)
        self.accept()

    def keyPressEvent(self, event) -> None:
        """Handle physical keyboard key presses."""
        if self._selected_method == "cash" and self._cash_section.isVisible():
            text = event.text()
            if text and text in "0123456789.":
                self._on_numpad(text)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Backspace:
                self._on_numpad("⌫")
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._confirm_btn.isEnabled():
                    self._on_confirm()
                event.accept()
                return

        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Styling helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _method_btn_style(active: bool, enabled: bool) -> str:
        if not enabled:
            return f"""
                QPushButton {{
                    background-color: {get_color('border_color')};
                    color: {get_color('text_muted')};
                    border: 2px solid {get_color('border_color')};
                    border-radius: 10px;
                    font-size: 15px;
                    font-weight: bold;
                    min-width: 0px;
                    padding: 6px;
                }}
            """
        if active:
            return f"""
                QPushButton {{
                    background-color: {get_color('accent_blue')};
                    color: #ffffff;
                    border: 2px solid {get_color('accent_blue')};
                    border-radius: 10px;
                    font-size: 15px;
                    font-weight: bold;
                    min-width: 0px;
                    padding: 6px;
                }}
                QPushButton:hover {{
                    background-color: {get_color('accent_blue')};
                }}
            """
        return f"""
            QPushButton {{
                background-color: {get_color('secondary_bg')};
                color: {get_color('text_primary')};
                border: 2px solid {get_color('border_color')};
                border-radius: 10px;
                font-size: 15px;
                font-weight: bold;
                min-width: 0px;
                padding: 6px;
            }}
            QPushButton:hover {{
                border-color: {get_color('accent_blue')};
                background-color: rgba(0, 123, 255, 0.1);
            }}
        """
