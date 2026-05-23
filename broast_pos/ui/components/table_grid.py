"""
Table grid — visual grid of restaurant tables for dine-in orders.

Layout: TABLE_COUNT buttons in a grid (auto columns).
    • Green  = free   → click creates a new order for that table
    • Red    = occupied → click loads the existing order

Emits:
    table_selected(int table_no) — when a table button is tapped.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Set

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

from broast_pos.config.config import TABLE_COUNT
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

_GRID_COLUMNS = 5
_BTN_SIZE = 80


class TableGrid(QDialog):
    """Modal dialog showing restaurant tables as a coloured grid.

    Usage::

        dialog = TableGrid(occupied_tables={3: "#12", 7: "#15"})
        dialog.table_selected.connect(on_table_chosen)
        dialog.exec()

    Signals:
        table_selected(int table_no):
            Emitted when a table button is clicked.
    """

    table_selected = pyqtSignal(int)  # table_no

    def __init__(
        self,
        occupied_tables: Optional[Dict[int, str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._occupied = occupied_tables or {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("اختر طاولة")
        self.setModal(True)
        self.setMinimumSize(480, 400)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('primary_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("🍽  اختر رقم الطاولة")
        title.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {get_color('text_primary')};
        """)
        header.addWidget(title)
        header.addStretch()

        # Legend
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for color_key, label in [("table_free", "متاحة"), ("table_occupied", "مشغولة")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {get_color(color_key)}; font-size: 14px;")
            txt = QLabel(label)
            txt.setStyleSheet(f"color: {get_color('text_secondary')}; font-size: 13px;")
            legend.addWidget(dot)
            legend.addWidget(txt)

        header.addLayout(legend)
        root.addLayout(header)

        # Grid
        grid = QGridLayout()
        grid.setSpacing(10)

        for i in range(TABLE_COUNT):
            table_no = i + 1
            is_occupied = table_no in self._occupied
            order_ref = self._occupied.get(table_no, "")

            btn = self._create_table_button(table_no, is_occupied, order_ref)
            row = i // _GRID_COLUMNS
            col = i % _GRID_COLUMNS
            grid.addWidget(btn, row, col)

        root.addLayout(grid, 1)

        # Cancel button
        cancel_btn = QPushButton("✕  إلغاء")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
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
        cancel_btn.clicked.connect(self.reject)
        root.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _create_table_button(
        self, table_no: int, is_occupied: bool, order_ref: str
    ) -> QPushButton:
        """Build a single table button — green (free) or red (occupied)."""
        if is_occupied:
            label = f"طاولة {table_no}\n{order_ref}"
            color = get_color("table_occupied")
        else:
            label = f"طاولة {table_no}"
            color = get_color("table_free")

        btn = QPushButton(label)
        btn.setObjectName(f"table_{table_no}")
        btn.setFixedSize(_BTN_SIZE, _BTN_SIZE)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {_lighten(color, 15)};
            }}
            QPushButton:pressed {{
                background-color: {_darken(color, 10)};
            }}
        """)
        btn.clicked.connect(lambda _, t=table_no: self._on_table_click(t))
        return btn

    def _on_table_click(self, table_no: int) -> None:
        """Handle table button click — emit signal and close dialog."""
        logger.debug("Table %d selected", table_no)
        self.table_selected.emit(table_no)
        self.accept()


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
