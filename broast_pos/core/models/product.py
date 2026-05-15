"""
Product models — Product and Category.

No Modifier model — each product variation is a separate product entry.
Example: "تشيكن فرايز حار" and "تشيكن فرايز عادي" are two distinct products.

Sort order matters — the POS grid displays products in the configured order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Category:
    """
    Product category displayed as a tab/filter in the POS grid.

    - `sort_order` controls tab position (lower = first).
    - `is_active` allows hiding categories without deleting.
    - Color is assigned from the rotating palette in restaurant.json.
    """
    id: Optional[int] = None
    name: str = ""
    sort_order: int = 0
    is_active: bool = True


@dataclass
class Product:
    """
    A single product displayed in the POS grid.

    - Tap product → goes directly to order panel (no popup dialog).
    - `sort_order` controls position within its category grid.
    - `price` is the unit price (always >= 0).
    - `category_id` links to a Category for grid filtering.
    """
    id: Optional[int] = None
    name: str = ""
    price: float = 0.0
    category_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0
