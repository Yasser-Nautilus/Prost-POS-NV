"""
PIN dialog — manager override numpad for privileged actions.

Used for:
    - Discount application
    - Item removal from saved orders
    - Order cancellation
    - Shift close / transfer

Flow:
    1. 4-digit PIN entry via numpad (masked with ●)
    2. Confirm → verifies against AuthService.verify_pin()
    3. Success → emits pin_verified(str pin_hash) + closes
    4. Failure → shakes + shows error, stays open for retry

Design:
    - No QLineEdit — visual dots only (touch-first)
    - Backspace clears last digit
    - Auto-submit on 4th digit
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

_PIN_LENGTH = 4


class PinDialog(QDialog):
    """Modal PIN entry for manager override.

    Usage::

        dialog = PinDialog(
            title="خصم يتطلب صلاحية مدير",
            verify_fn=auth_service.verify_pin,
        )
        dialog.pin_verified.connect(on_pin_ok)
        dialog.exec()

    Args:
        title: Arabic description of why PIN is needed.
        verify_fn: Callable(str pin) → User|None. Returns manager
            user if valid, None if invalid.

    Signals:
        pin_verified(str raw_pin):
            Emitted when the PIN is valid. Carries the raw PIN
            string so the caller can pass it to the service layer.
    """

    pin_verified = pyqtSignal(str)  # raw PIN

    def __init__(
        self,
        title: str = "أدخل PIN المدير",
        verify_fn=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._title_text = title
        self._verify_fn = verify_fn
        self._pin_digits: list[str] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("تأكيد الصلاحية")
        self.setModal(True)
        self.setMinimumSize(340, 440)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('primary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(16)

        # Title
        title_lbl = QLabel(self._title_text)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {get_color('text_primary')};
            padding: 4px;
        """)
        root.addWidget(title_lbl)

        # PIN dots
        self._dots_container = QWidget()
        dots_layout = QHBoxLayout(self._dots_container)
        dots_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dots_layout.setSpacing(16)

        self._dot_labels: list[QLabel] = []
        for _ in range(_PIN_LENGTH):
            dot = QLabel("○")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setMinimumSize(36, 36)
            dot.setStyleSheet(f"""
                font-size: 28px;
                color: {get_color('text_muted')};
                background-color: {get_color('secondary_bg')};
                border-radius: 20px;
            """)
            dots_layout.addWidget(dot)
            self._dot_labels.append(dot)

        root.addWidget(self._dots_container)

        # Error label
        self._error_lbl = QLabel("")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('accent_red')};
            min-height: 20px;
        """)
        root.addWidget(self._error_lbl)

        # Numpad
        numpad = QGridLayout()
        numpad.setSpacing(8)

        keys = [
            ("1", "2", "3"),
            ("4", "5", "6"),
            ("7", "8", "9"),
            ("✕", "0", "⌫"),
        ]
        for r, row_keys in enumerate(keys):
            for c, key in enumerate(row_keys):
                btn = QPushButton(key)
                btn.setMinimumSize(70, 56)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)

                if key == "✕":
                    btn.setStyleSheet(self._special_btn_style("danger"))
                    btn.clicked.connect(self.reject)
                elif key == "⌫":
                    btn.setStyleSheet(self._special_btn_style("neutral"))
                    btn.clicked.connect(self._on_backspace)
                else:
                    btn.setStyleSheet(self._digit_btn_style())
                    btn.clicked.connect(lambda _, d=key: self._on_digit(d))

                numpad.addWidget(btn, r, c)

        root.addLayout(numpad)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _on_digit(self, digit: str) -> None:
        """Add a digit to the PIN."""
        if len(self._pin_digits) >= _PIN_LENGTH:
            return

        self._pin_digits.append(digit)
        self._update_dots()
        self._error_lbl.setText("")

        # Auto-submit on last digit
        if len(self._pin_digits) == _PIN_LENGTH:
            self._verify_pin()

    def _on_backspace(self) -> None:
        """Remove the last digit."""
        if self._pin_digits:
            self._pin_digits.pop()
            self._update_dots()
            self._error_lbl.setText("")

    def _update_dots(self) -> None:
        """Refresh dot display — filled ● vs empty ○."""
        for i, dot in enumerate(self._dot_labels):
            if i < len(self._pin_digits):
                dot.setText("●")
                dot.setStyleSheet(f"""
                    font-size: 28px;
                    color: {get_color('accent_blue')};
                    background-color: {get_color('secondary_bg')};
                    border-radius: 20px;
                """)
            else:
                dot.setText("○")
                dot.setStyleSheet(f"""
                    font-size: 28px;
                    color: {get_color('text_muted')};
                    background-color: {get_color('secondary_bg')};
                    border-radius: 20px;
                """)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify_pin(self) -> None:
        """Hash and verify the entered PIN."""
        raw_pin = "".join(self._pin_digits)

        if self._verify_fn is None:
            # No verification function — just emit
            logger.warning("PinDialog: no verify_fn set, accepting PIN blindly")
            self.pin_verified.emit(raw_pin)
            self.accept()
            return

        result = self._verify_fn(raw_pin)
        if result is not None:
            logger.info("PIN verified for user: %s", getattr(result, 'display_name', '?'))
            self.pin_verified.emit(raw_pin)
            self.accept()
        else:
            logger.warning("Invalid PIN entered")
            self._on_invalid_pin()

    def _on_invalid_pin(self) -> None:
        """Show error, shake animation, reset dots."""
        self._error_lbl.setText("❌ PIN غير صحيح")
        self._pin_digits.clear()
        self._update_dots()
        self._shake_animation()

    def _shake_animation(self) -> None:
        """Quick horizontal shake on the dots container."""
        anim = QPropertyAnimation(self._dots_container, b"pos")
        anim.setDuration(300)
        start = self._dots_container.pos()
        anim.setStartValue(start)
        anim.setKeyValueAt(0.15, start + type(start)(10, 0))
        anim.setKeyValueAt(0.30, start + type(start)(-10, 0))
        anim.setKeyValueAt(0.45, start + type(start)(8, 0))
        anim.setKeyValueAt(0.60, start + type(start)(-8, 0))
        anim.setKeyValueAt(0.80, start + type(start)(4, 0))
        anim.setEndValue(start)
        anim.setEasingCurve(QEasingCurve.Type.OutElastic)
        # Keep reference to prevent GC
        self._anim = anim
        anim.start()

    def keyPressEvent(self, event) -> None:
        """Handle physical keyboard key presses."""
        text = event.text()
        if text.isdigit() and len(text) == 1:
            self._on_digit(text)
            event.accept()
        elif event.key() == Qt.Key.Key_Backspace:
            self._on_backspace()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Styling helpers
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
        if variant == "danger":
            bg = get_color("button_cancel")
        else:
            bg = get_color("button_neutral")
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
