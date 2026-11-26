"""
Product service — category and product CRUD with search.

No modifiers — each product variation is a separate database entry.
Sort order matters: the POS grid displays in configured order.
Search must be instant (<100ms at 300+ orders/day).
"""

from __future__ import annotations

import math

from broast_pos.core.models.product import Category, Product
from broast_pos.data.repositories.product_repository import ProductRepository

MAX_PRODUCT_PRICE = 50_000.0
PRICE_VALIDATION_MESSAGE = "سعر المنتج يجب أن يكون رقماً من 0 إلى 50,000 ج.م"


class ProductService:
    """Business logic for products and categories."""

    def __init__(
        self, product_repo: ProductRepository | None = None,
    ) -> None:
        self._products = product_repo or ProductRepository()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def get_categories(self) -> list[Category]:
        """Sorted list of active categories for POS grid tabs."""
        return self._products.get_categories()

    def get_product(self, product_id: int) -> Product | None:
        """Look up a single product by id — the authoritative source for
        its name and price (H19: never trust a client-supplied price)."""
        return self._products.get_by_id(product_id)

    def get_all_categories(self) -> list[Category]:
        """Sorted list of all categories (active and inactive)."""
        return self._products.get_all_categories()

    def create_category(self, name: str, sort_order: int = 0) -> Category:
        """Create a new product category.

        Raises:
            ValueError: if name is empty.
        """
        name = name.strip()
        if not name:
            raise ValueError("اسم الفئة مطلوب")

        cat = Category(name=name, sort_order=sort_order, is_active=True)
        return self._products.save_category(cat)

    def update_category(
        self,
        category_id: int,
        name: str | None = None,
        sort_order: int | None = None,
        is_active: bool | None = None,
    ) -> Category:
        """Update an existing category.

        Raises:
            ValueError: if category not found.
        """
        cat = self._products.get_category_by_id(category_id)
        if cat is None:
            raise ValueError("الفئة غير موجودة")

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("اسم الفئة مطلوب")
            cat.name = name

        if sort_order is not None:
            cat.sort_order = sort_order

        if is_active is not None:
            cat.is_active = is_active

        return self._products.save_category(cat)

    def delete_category(self, category_id: int) -> None:
        """Soft-delete a category.

        Raises:
            ValueError: if category not found or has active products.
        """
        cat = self._products.get_category_by_id(category_id)
        if cat is None:
            raise ValueError("الفئة غير موجودة")

        # Check for active products in this category
        products = self._products.get_products_by_category(category_id)
        if products:
            raise ValueError(
                "لا يمكن حذف الفئة — يوجد منتجات مرتبطة بها"
            )

        self._products.delete_category(category_id)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def get_products_by_category(self, category_id: int) -> list[Product]:
        """Sorted products for a specific category grid."""
        return self._products.get_products_by_category(category_id)

    def get_all_products(self) -> list[Product]:
        """All products (active and inactive)."""
        return self._products.get_all_products()

    def search_products(self, query: str) -> list[Product]:
        """Fast text search across product names."""
        query = query.strip()
        if not query:
            return []
        return self._products.search_products(query)

    @staticmethod
    def validate_price(price) -> float:
        if isinstance(price, bool):
            raise ValueError(PRICE_VALIDATION_MESSAGE)
        try:
            value = float(price)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(PRICE_VALIDATION_MESSAGE) from None
        if not math.isfinite(value) or not 0 <= value <= MAX_PRODUCT_PRICE:
            raise ValueError(PRICE_VALIDATION_MESSAGE)
        return value

    def _ensure_unique_name(self, name: str, exclude_id: int | None = None) -> None:
        """Block a second active product with the same name (case-insensitive)."""
        wanted = " ".join(name.split()).casefold()
        for other in self._products.get_all_products():
            if other.id == exclude_id or not other.is_active:
                continue
            if " ".join(other.name.split()).casefold() == wanted:
                raise ValueError("اسم المنتج موجود بالفعل")

    def create_product(
        self,
        name: str,
        price: float,
        category_id: int,
        sort_order: int = 0,
    ) -> Product:
        """Create a new product entry.

        Raises:
            ValueError: if name is empty or price is invalid.
        """
        name = name.strip()
        if not name:
            raise ValueError("اسم المنتج مطلوب")
        price = self.validate_price(price)
        self._ensure_unique_name(name)

        product = Product(
            name=name,
            price=price,
            category_id=category_id,
            sort_order=sort_order,
            is_active=True,
        )
        return self._products.save(product)

    def update_product(
        self,
        product_id: int,
        name: str | None = None,
        price: float | None = None,
        category_id: int | None = None,
        sort_order: int | None = None,
        is_active: bool | None = None,
    ) -> Product:
        """Update an existing product.

        Note: price changes do NOT affect existing orders
        (prices locked at order creation).

        Raises:
            ValueError: if product not found.
        """
        product = self._products.get_by_id(product_id)
        if product is None:
            raise ValueError("المنتج غير موجود")

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("اسم المنتج مطلوب")
            if product.is_active and is_active is not False:
                self._ensure_unique_name(name, exclude_id=product_id)
            product.name = name

        if price is not None:
            product.price = self.validate_price(price)

        if category_id is not None:
            product.category_id = category_id

        if sort_order is not None:
            product.sort_order = sort_order

        if is_active is not None:
            if is_active and not product.is_active:
                self._ensure_unique_name(product.name, exclude_id=product_id)
            product.is_active = is_active

        return self._products.save(product)

    def delete_product(self, product_id: int) -> None:
        """Soft-delete a product (set is_active = 0).

        Raises:
            ValueError: if product not found.
        """
        product = self._products.get_by_id(product_id)
        if product is None:
            raise ValueError("المنتج غير موجود")
        self._products.delete(product_id)

    def remove_product(self, product_id: int) -> None:
        """Permanently delete a product (unlike hide, which only deactivates).

        A product that appears on past orders cannot be deleted without
        breaking those orders and the reports, so it must be hidden instead.

        Raises:
            ValueError: if the product is missing or has order history.
        """
        product = self._products.get_by_id(product_id)
        if product is None:
            raise ValueError("المنتج غير موجود")
        if self._products.has_order_history(product_id):
            raise ValueError(
                "لا يمكن حذف منتج عليه طلبات سابقة، استخدم إخفاء بدلاً من الحذف"
            )
        self._products.hard_delete(product_id)

    def reorder_products(self, category_id: int, ordered_ids: list[int]) -> None:
        """Save a manual order for the products of one category.

        ``ordered_ids`` must list every product of the category (hidden ones
        included) exactly once, in the wanted order.

        Raises:
            ValueError: if the list does not match the category's products.
        """
        try:
            ids = [int(i) for i in ordered_ids]
        except (TypeError, ValueError):
            raise ValueError("قائمة الترتيب غير صالحة") from None
        current = {
            p.id for p in self._products.get_all_products()
            if p.category_id == category_id
        }
        if len(set(ids)) != len(ids) or set(ids) != current:
            raise ValueError("قائمة الترتيب لا تطابق منتجات الفئة")
        self._products.set_sort_orders(ids)
