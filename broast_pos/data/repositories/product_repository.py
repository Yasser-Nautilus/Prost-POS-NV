"""
Product repository — product and category database queries.

Simplified: no modifier queries, no join tables. Products are self-contained.
Sort order matters — the POS grid displays in configured order.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from broast_pos.core.models.product import Category, Product
from broast_pos.data.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """CRUD and query operations for products and categories."""

    # ------------------------------------------------------------------
    # Core contract (for Product)
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[Product]:
        row = self._db.fetch_one("SELECT * FROM products WHERE id = ?", (entity_id,))
        return self._row_to_product(row) if row else None

    def save(self, entity: Product) -> Product:
        return self.save_product(entity)

    def delete(self, entity_id: int) -> None:
        """Soft-delete: deactivate product."""
        self._db.execute(
            "UPDATE products SET is_active = 0 WHERE id = ?", (entity_id,)
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Category queries
    # ------------------------------------------------------------------

    def get_categories(self) -> List[Category]:
        """Sorted list of active categories — for POS tab bar."""
        rows = self._db.fetch_all(
            "SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order, name"
        )
        return [self._row_to_category(r) for r in rows]

    def get_category_by_id(self, category_id: int) -> Optional[Category]:
        """Fetch a single category."""
        row = self._db.fetch_one(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        )
        return self._row_to_category(row) if row else None

    def save_category(self, category: Category) -> Category:
        """Insert or update a category."""
        if category.id is None:
            self._db.execute(
                "INSERT INTO categories (name, sort_order, is_active) VALUES (?, ?, ?)",
                (category.name, category.sort_order, 1 if category.is_active else 0),
            )
            category.id = self._last_insert_id()
        else:
            self._db.execute(
                """UPDATE categories SET name = ?, sort_order = ?, is_active = ?
                   WHERE id = ?""",
                (category.name, category.sort_order,
                 1 if category.is_active else 0, category.id),
            )
        self._db.commit()
        return category

    def delete_category(self, category_id: int) -> None:
        """Soft-delete: deactivate category."""
        self._db.execute(
            "UPDATE categories SET is_active = 0 WHERE id = ?", (category_id,)
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Product queries
    # ------------------------------------------------------------------

    def get_products_by_category(self, category_id: int) -> List[Product]:
        """Sorted products for a category — for POS grid display."""
        rows = self._db.fetch_all(
            """SELECT * FROM products
               WHERE category_id = ? AND is_active = 1
               ORDER BY sort_order, name""",
            (category_id,),
        )
        return [self._row_to_product(r) for r in rows]

    def search_products(self, query: str) -> List[Product]:
        """Text search across product names."""
        rows = self._db.fetch_all(
            "SELECT * FROM products WHERE name LIKE ? AND is_active = 1 ORDER BY name",
            (f"%{query}%",),
        )
        return [self._row_to_product(r) for r in rows]

    def get_all_active_products(self) -> List[Product]:
        """All active products — for product management screen."""
        rows = self._db.fetch_all(
            "SELECT * FROM products WHERE is_active = 1 ORDER BY category_id, sort_order"
        )
        return [self._row_to_product(r) for r in rows]

    def save_product(self, product: Product) -> Product:
        """Insert or update a product."""
        if product.id is None:
            self._db.execute(
                """INSERT INTO products
                       (name, price, category_id, is_active, sort_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (product.name, product.price, product.category_id,
                 1 if product.is_active else 0, product.sort_order),
            )
            product.id = self._last_insert_id()
        else:
            self._db.execute(
                """UPDATE products SET
                       name = ?, price = ?, category_id = ?,
                       is_active = ?, sort_order = ?
                   WHERE id = ?""",
                (product.name, product.price, product.category_id,
                 1 if product.is_active else 0, product.sort_order,
                 product.id),
            )
        self._db.commit()
        return product

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_product(self, row: sqlite3.Row) -> Product:
        return Product(
            id=row["id"],
            name=row["name"],
            price=row["price"],
            category_id=row["category_id"],
            is_active=bool(row["is_active"]),
            sort_order=row["sort_order"],
        )

    def _row_to_category(self, row: sqlite3.Row) -> Category:
        return Category(
            id=row["id"],
            name=row["name"],
            sort_order=row["sort_order"],
            is_active=bool(row["is_active"]),
        )
