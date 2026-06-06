"""
Discount dialog — numeric entry for applying an order discount.

Flow (called AFTER manager PIN is verified in PosView):
    1. Shows current order subtotal as context.
    2. Cashier selects mode: flat (ج.م) or percent (%).
    3. Enters value via on-screen numpad (keyboard also works).
    4. Live preview line shows resulting discount + new total.
    5. Confirm → emits discount_applied(value, discount_type).
    6. Cancel → rejects without change.

Design mirrors PinDialog: dark theme, RTL, touch-friendly buttons.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import MAX_DISCOUNT_PERCENT
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

_MAX_INPUT_LENGTH = 7   # e.g. "9999.99"
_FLAT_MODE  = "flat"
_PCT_MODE   = "percent"


class DiscountDialog(QDialog):
    """Modal discount entry dialog.

    Usage::

        dlg = DiscountDialog(subtotal=order.subtotal, parent=self)
        dlg.discount_applied.connect(on_discount_applied)
        dlg.exec()

    Args:
        subtotal: Current order subtotal (EGP) — shown as context.
        current_discount: Pre-existing discount amount (to show current state).
        parent: Parent widget.

    Signals:
        discount_applied(value: float, discount_type: str):
            Emitted when the cashier confirms a valid discount.
            ``discount_type`` is either ``"flat"`` or ``"percent"``.
    """

    discount_applied = pyqtSignal(float, str)  # value, discount_type

    def __init__(
        self,
        subtotal: float = 0.0,
        current_discount: float = 0.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._subtotal = max(0.0, subtotal)
        self._current_discount = max(0.0, current_discount)
        self._mode = _FLAT_MODE
        self._input_chars: list[str] = []
        self._setup_ui()
        self._update_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("تطبيق خصم")
        self.setModal(True)
        self.setMinimumSize(380, 560)
        self.setMaximumSize(480, 640)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('primary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────────
        header = QLabel("💰  تطبيق خصم")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {get_color('text_primary')};
            padding-bottom: 4px;
        """)
        root.addWidget(header)

        # ── Subtotal context ───────────────────────────────────────────
        subtotal_lbl = QLabel(f"المجموع الفرعي: {self._subtotal:,.2f} ج.م")
        subtotal_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtotal_lbl.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('text_secondary')};
            background-color: {get_color('secondary_bg')};
            border-radius: 8px;
            padding: 6px 12px;
        """)
        root.addWidget(subtotal_lbl)

        # ── Mode toggle ────────────────────────────────────────────────
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)

        self._flat_btn = QPushButton("مبلغ ثابت  ج.م")
        self._flat_btn.setMinimumHeight(40)
        self._flat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._flat_btn.clicked.connect(lambda: self._set_mode(_FLAT_MODE))
        mode_row.addWidget(self._flat_btn)

        self._pct_btn = QPushButton("نسبة مئوية  %")
        self._pct_btn.setMinimumHeight(40)
        self._pct_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pct_btn.clicked.connect(lambda: self._set_mode(_PCT_MODE))
        mode_row.addWidget(self._pct_btn)

        root.addLayout(mode_row)

        # ── Input display ──────────────────────────────────────────────
        display_frame = QFrame()
        display_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 10px;
            }}
        """)
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(12, 8, 12, 8)

        self._display_lbl = QLabel("0")
        self._display_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display_lbl.setStyleSheet(f"""
            font-size: 36px;
            font-weight: bold;
            color: {get_color('accent_orange')};
            min-height: 52px;
        """)
        display_layout.addWidget(self._display_lbl)

        self._unit_lbl = QLabel("ج.م")
        self._unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unit_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_muted')};
        """)
        display_layout.addWidget(self._unit_lbl)

        root.addWidget(display_frame)

        # ── Numpad ─────────────────────────────────────────────────────
        numpad = QGridLayout()
        numpad.setSpacing(8)

        keys = [
            ("7", "8", "9"),
            ("4", "5", "6"),
            ("1", "2", "3"),
            (".", "0", "⌫"),
        ]
        for r, row_keys in enumerate(keys):
            for c, key in enumerate(row_keys):
                btn = QPushButton(key)
                btn.setMinimumSize(72, 56)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)

                if key == "⌫":
                    btn.setStyleSheet(self._special_btn_style("neutral"))
                    btn.clicked.connect(self._on_backspace)
                else:
                    btn.setStyleSheet(self._digit_btn_style())
                    btn.clicked.connect(lambda _, k=key: self._on_key(k))

                numpad.addWidget(btn, r, c)

        root.addLayout(numpad)

        # ── Error label ────────────────────────────────────────────────
        self._error_lbl = QLabel("")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('accent_red')};
            min-height: 18px;
        """)
        root.addWidget(self._error_lbl)

        # ── Preview ────────────────────────────────────────────────────
        self._preview_lbl = QLabel("")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setWordWrap(True)
        self._preview_lbl.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('accent_green')};
            background-color: {get_color('secondary_bg')};
            border-radius: 8px;
            padding: 6px 10px;
            min-height: 36px;
        """)
        root.addWidget(self._preview_lbl)

        # ── Footer buttons ─────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)

        cancel_btn = QPushButton("إلغاء")
        cancel_btn.setMinimumHeight(44)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_cancel')};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #c82333; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        self._apply_btn = QPushButton("✓  تطبيق الخصم")
        self._apply_btn.setMinimumHeight(44)
        self._apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_green')};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #218838; }}
        """)
        self._apply_btn.clicked.connect(self._on_apply)
        footer.addWidget(self._apply_btn, 2)

        root.addLayout(footer)

        # Initialise mode button styles
        self._refresh_mode_buttons()

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        """Switch between flat and percent modes, resetting input."""
        if self._mode == mode:
            return
        self._mode = mode
        self._input_chars = []
        self._error_lbl.setText("")
        self._refresh_mode_buttons()
        self._update_display()
        self._update_preview()

    def _refresh_mode_buttons(self) -> None:
        active_style = f"""
            QPushButton {{
                background-color: {get_color('accent_orange')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background-color: {get_color('button_neutral')};
                color: {get_color('text_secondary')};
                border: 1px solid {get_color('border_color')};
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {get_color('text_primary')};
                background-color: rgba(255,255,255,0.06);
            }}
        """
        self._flat_btn.setStyleSheet(
            active_style if self._mode == _FLAT_MODE else inactive_style
        )
        self._pct_btn.setStyleSheet(
            active_style if self._mode == _PCT_MODE else inactive_style
        )
        self._unit_lbl.setText("ج.م" if self._mode == _FLAT_MODE else "%")

    # ------------------------------------------------------------------
    # Numpad input
    # ------------------------------------------------------------------

    def _on_key(self, key: str) -> None:
        """Handle a digit or decimal point press."""
        raw = "".join(self._input_chars)

        # Only one decimal point allowed
        if key == "." and "." in raw:
            return

        # Don't allow leading zero before a digit (e.g. "07")
        if key != "." and raw == "0":
            self._input_chars = [key]
            self._update_display()
            self._update_preview()
            return

        if len(raw) >= _MAX_INPUT_LENGTH:
            return

        self._input_chars.append(key)
        self._error_lbl.setText("")
        self._update_display()
        self._update_preview()

    def _on_backspace(self) -> None:
        """Remove the last character."""
        if self._input_chars:
            self._input_chars.pop()
            self._error_lbl.setText("")
            self._update_display()
            self._update_preview()

    def _current_value(self) -> float:
        """Parse the current input string to a float. Returns 0 on empty/invalid."""
        raw = "".join(self._input_chars).strip(".")
        try:
            return float(raw) if raw else 0.0
        except ValueError:
            return 0.0

    def _update_display(self) -> None:
        """Refresh the big numeric display."""
        raw = "".join(self._input_chars)
        self._display_lbl.setText(raw if raw else "0")

    def _update_preview(self) -> None:
        """Compute and show the discount + new total preview."""
        value = self._current_value()
        if value <= 0:
            self._preview_lbl.setText("أدخل قيمة الخصم")
            self._preview_lbl.setStyleSheet(f"""
                font-size: 14px;
                color: {get_color('text_muted')};
                background-color: {get_color('secondary_bg')};
                border-radius: 8px;
                padding: 6px 10px;
                min-height: 36px;
            """)
            return

        if self._mode == _PCT_MODE:
            discount_amount = round(self._subtotal * value / 100, 2)
        else:
            discount_amount = round(value, 2)

        new_total = max(0.0, self._subtotal - discount_amount)

        self._preview_lbl.setText(
            f"الخصم: {discount_amount:,.2f} ج.م  ←  المجموع الجديد: {new_total:,.2f} ج.م"
        )
        self._preview_lbl.setStyleSheet(f"""
            font-size: 14px;
            color: {get_color('accent_green')};
            background-color: {get_color('secondary_bg')};
            border-radius: 8px;
            padding: 6px 10px;
            min-height: 36px;
        """)

    # ------------------------------------------------------------------
    # Apply / validate
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        """Validate input and emit discount_applied signal."""
        value = self._current_value()

        if value <= 0:
            self._error_lbl.setText("⚠️  يجب إدخال قيمة أكبر من صفر")
            return

        if self._mode == _PCT_MODE:
            if value > MAX_DISCOUNT_PERCENT:
                self._error_lbl.setText(
                    f"⚠️  النسبة يجب أن تكون ≤ {MAX_DISCOUNT_PERCENT}%"
                )
                return
            discount_amount = round(self._subtotal * value / 100, 2)
        else:
            discount_amount = round(value, 2)

        if discount_amount > self._subtotal:
            self._error_lbl.setText(
                f"⚠️  الخصم ({discount_amount:,.2f}) يتجاوز المجموع ({self._subtotal:,.2f})"
            )
            return

        logger.info(
            "Discount confirmed: %.2f (%s) on subtotal %.2f",
            value, self._mode, self._subtotal,
        )
        self.discount_applied.emit(value, self._mode)
        self.accept()

    # ------------------------------------------------------------------
    # Keyboard support
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        text = event.text()
        if text.isdigit():
            self._on_key(text)
            event.accept()
        elif text == ".":
            self._on_key(".")
            event.accept()
        elif event.key() == Qt.Key.Key_Backspace:
            self._on_backspace()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_apply()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Style helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _digit_btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: {get_color('secondary_bg')};
                color: {get_color('text_primary')};
                border: 1px solid {get_color('border_color')};
                border-radius: 10px;
                font-size: 22px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.08);
            }}
            QPushButton:pressed {{
                background-color: rgba(255,255,255,0.15);
            }}
        """

    @staticmethod
    def _special_btn_style(variant: str) -> str:
        bg = get_color("button_neutral") if variant == "neutral" else get_color("button_cancel")
        return f"""
            QPushButton {{
                background-color: {bg};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """
