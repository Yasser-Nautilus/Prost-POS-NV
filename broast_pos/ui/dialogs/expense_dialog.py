"""
Expense dialog — touch-friendly cash expense entry dialog.

Allows cashiers or managers to record cash payouts from the register.
Valid categories: supplies, delivery_fees, other.
Requires amount, category, and description.
All entries are immutable after save.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)


class ExpenseDialog(QDialog):
    """Modal dialog to enter cash expenses.

    Usage::

        dialog = ExpenseDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            amount, category, description = dialog.get_data()
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("إضافة مصروف")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('primary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Header
        header = QLabel("💰  تسجيل مصروف جديد")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {get_color('text_primary')};
            padding-bottom: 4px;
        """)
        root.addWidget(header)

        # Amount Input
        amount_lbl = QLabel("المبلغ:")
        amount_lbl.setStyleSheet(f"font-size: 13px; color: {get_color('text_secondary')};")
        root.addWidget(amount_lbl)

        self._amount_input = QLineEdit()
        self._amount_input.setPlaceholderText("0")
        self._amount_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._amount_input.setValidator(QDoubleValidator(0.0, 999999.99, 2))
        self._amount_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('input_bg')};
                color: {get_color('text_primary')};
                border: 2px solid {get_color('border_color')};
                border-radius: 8px;
                padding: 10px;
                font-size: 22px;
                font-weight: bold;
                min-height: 36px;
            }}
            QLineEdit:focus {{
                border-color: {get_color('accent_blue')};
            }}
        """)
        self._amount_input.textChanged.connect(self._validate)
        root.addWidget(self._amount_input)

        # Category
        cat_lbl = QLabel("الفئة:")
        cat_lbl.setStyleSheet(f"font-size: 13px; color: {get_color('text_secondary')};")
        root.addWidget(cat_lbl)

        self._cat_combo = QComboBox()
        self._cat_combo.addItem("مصاريف نثريات / Supplies", "supplies")
        self._cat_combo.addItem("أجور دليفري / Delivery Fees", "delivery_fees")
        self._cat_combo.addItem("أخرى / Other", "other")
        self._cat_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self._cat_combo)

        # Description
        desc_lbl = QLabel("البيان / الوصف:")
        desc_lbl.setStyleSheet(f"font-size: 13px; color: {get_color('text_secondary')};")
        root.addWidget(desc_lbl)

        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("أدخل سبب الصرف (مثال: شراء كرتون بيض)")
        self._desc_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {get_color('input_bg')};
                color: {get_color('text_primary')};
                border: 2px solid {get_color('border_color')};
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border-color: {get_color('accent_blue')};
            }}
        """)
        root.addWidget(self._desc_input)

        root.addStretch()

        # Actions
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        cancel_btn = QPushButton("✕  إلغاء")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setMinimumHeight(44)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_neutral')};
                color: {get_color('text_secondary')};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.05);
                color: {get_color('text_primary')};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        self._confirm_btn = QPushButton("✓  حفظ المصروف")
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.setMinimumHeight(44)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_confirm')};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {_lighten(get_color('button_confirm'), 10)};
            }}
            QPushButton:disabled {{
                background-color: {get_color('border_color')};
                color: {get_color('text_muted')};
            }}
        """)
        self._confirm_btn.clicked.connect(self._on_save)
        bottom.addWidget(self._confirm_btn)

        root.addLayout(bottom)

        # Focus the amount input on open
        self._amount_input.setFocus()

    def _validate(self) -> None:
        try:
            text = self._amount_input.text().strip()
            amt = float(text) if text else 0.0
        except ValueError:
            amt = 0.0
        self._confirm_btn.setEnabled(amt > 0)

    def _on_save(self) -> None:
        """Verify description is present before accepting."""
        desc = self._desc_input.text().strip()
        if not desc:
            self._desc_input.setFocus()
            self._desc_input.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {get_color('input_bg')};
                    color: {get_color('text_primary')};
                    border: 2px solid {get_color('accent_red')};
                    border-radius: 8px;
                    padding: 8px;
                }}
            """)
            return
        self.accept()

    def keyPressEvent(self, event) -> None:
        """Handle Enter/Escape for dialog-level shortcuts."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._confirm_btn.isEnabled():
                self._on_save()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
        else:
            super().keyPressEvent(event)

    def get_data(self) -> tuple[float, str, str]:
        """Return the user entered amount, category, and description."""
        text = self._amount_input.text().strip()
        amt = float(text) if text else 0.0
        cat = self._cat_combo.currentData()
        desc = self._desc_input.text().strip()
        return amt, cat, desc


def _lighten(hex_color: str, amount: int = 10) -> str:
    hex_color = hex_color.lstrip("#")
    r = min(255, int(hex_color[0:2], 16) + amount)
    g = min(255, int(hex_color[2:4], 16) + amount)
    b = min(255, int(hex_color[4:6], 16) + amount)
    return f"#{r:02x}{g:02x}{b:02x}"

