"""
Product grid — responsive grid of large product buttons.

Each button shows product name + price, colour-coded by category.
Tap a product → signal emitted → POS view adds it to the order panel.
No popup, no confirmation — fastest possible flow.

Products are passed in by the POS view (pre-cached); this widget
never calls the database.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config.config import get_category_colors, get_fonts
from broast_pos.core.models.product import Category, Product
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)

# Grid layout settings
_COLUMNS = 4          # buttons per row (adjusts when grid is very narrow)
_BTN_MIN_W = 120      # minimum button width
_BTN_MIN_H = 80       # minimum button height (spec: 80×60 min)


class ProductGrid(QWidget):
    """Responsive grid of product buttons.

    Signals:
        product_clicked(Product):
            Emitted when a product button is tapped.
            The POS view connects this to add the product to the current order.
    """

    product_clicked = pyqtSignal(object)   # Product dataclass

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._products: List[Product] = []
        self._category_color: str = get_color("accent_blue")
        self._buttons: List[QPushButton] = []
        self._setup_ui()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable container so the grid never gets clipped
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)

        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll)

        # Empty-state label (hidden by default)
        self._empty_lbl = QLabel("لا توجد منتجات")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"""
            font-size: 16px;
            color: {get_color('text_muted')};
            padding: 40px;
        """)
        self._empty_lbl.hide()
        root.addWidget(self._empty_lbl)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_products(
        self,
        products: List[Product],
        category_color: Optional[str] = None,
    ) -> None:
        """Replace the grid contents with *products*.

        Parameters
        ----------
        products : list[Product]
            Active products sorted by sort_order.
        category_color : str, optional
            Hex colour for these buttons (from category_colors palette).
            Falls back to accent_blue.
        """
        self._products = products
        self._category_color = category_color or get_color("accent_blue")
        self._rebuild_grid()

    def clear(self) -> None:
        """Remove all product buttons."""
        self._products = []
        self._rebuild_grid()

    # ------------------------------------------------------------------
    # Grid building
    # ------------------------------------------------------------------

    def _rebuild_grid(self) -> None:
        """Tear down and recreate all buttons."""
        # Clear existing
        self._buttons.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._products:
            self._container.hide()
            self._empty_lbl.show()
            return

        self._empty_lbl.hide()
        self._container.show()

        fonts = get_fonts()
        f_btn = fonts.get("size_button", 16)

        for idx, product in enumerate(self._products):
            btn = self._create_product_button(product, f_btn)
            row = idx // _COLUMNS
            col = idx % _COLUMNS
            self._grid.addWidget(btn, row, col)
            self._buttons.append(btn)

        # Fill remaining cells so the last row doesn't stretch
        remainder = len(self._products) % _COLUMNS
        if remainder:
            row = len(self._products) // _COLUMNS
            for col in range(remainder, _COLUMNS):
                spacer = QWidget()
                spacer.setMinimumSize(_BTN_MIN_W, _BTN_MIN_H)
                spacer.setStyleSheet("background: transparent;")
                self._grid.addWidget(spacer, row, col)

    def _create_product_button(
        self, product: Product, font_size: int
    ) -> QPushButton:
        """Build a single product button with name + price."""
        price_text = f"{product.price:.0f}" if product.price == int(product.price) else f"{product.price:.2f}"
        btn = QPushButton(f"{product.name}\n{price_text} ج.م")
        btn.setObjectName(f"prod_{product.id}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        btn.setMinimumSize(_BTN_MIN_W, _BTN_MIN_H)
        btn.setStyleSheet(self._product_btn_style(self._category_color, font_size))
        btn.clicked.connect(lambda _, p=product: self.product_clicked.emit(p))
        return btn

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    @staticmethod
    def _product_btn_style(color: str, font_size: int) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 4px;
                font-size: {font_size}px;
                font-weight: bold;
                min-height: {_BTN_MIN_H}px;
                min-width: {_BTN_MIN_W}px;
            }}
            QPushButton:hover {{
                background-color: {_lighten(color, 18)};
            }}
            QPushButton:pressed {{
                background-color: {_darken(color, 12)};
            }}
        """


# ============================================================================
# Colour helpers (duplicated from theme — avoids circular import risk)
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
