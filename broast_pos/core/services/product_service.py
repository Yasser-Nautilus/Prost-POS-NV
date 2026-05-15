"""
Product service — category and product CRUD with search.

No modifiers — each product variation is a separate database entry.
Sort order matters: the POS grid displays in configured order.
Search must be instant (<100ms at 300+ orders/day).
"""

from __future__ import annotations

from typing import List, Optional

from broast_pos.core.models.product import Category, Product
from broast_pos.data.repositories.product_repository import ProductRepository


class ProductService:
    """Business logic for products and categories."""

    def __init__(
        self, product_repo: Optional[ProductRepository] = None,
    ) -> None:
        self._products = product_repo or ProductRepository()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    def get_categories(self) -> List[Category]:
        """Sorted list of active categories for POS grid tabs."""
        return self._products.get_categories()

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
        name: Optional[str] = None,
        sort_order: Optional[int] = None,
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
        products = self._products.get_by_category(category_id)
        if products:
            raise ValueError(
                "لا يمكن حذف الفئة — يوجد منتجات مرتبطة بها"
            )

        self._products.delete_category(category_id)

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def get_products_by_category(self, category_id: int) -> List[Product]:
        """Sorted products for a specific category grid."""
        return self._products.get_by_category(category_id)

    def search_products(self, query: str) -> List[Product]:
        """Fast text search across product names."""
        query = query.strip()
        if not query:
            return []
        return self._products.search(query)

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
        if price < 0:
            raise ValueError("السعر يجب أن يكون أكبر من أو يساوي صفر")

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
        name: Optional[str] = None,
        price: Optional[float] = None,
        category_id: Optional[int] = None,
        sort_order: Optional[int] = None,
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
            product.name = name

        if price is not None:
            if price < 0:
                raise ValueError("السعر يجب أن يكون أكبر من أو يساوي صفر")
            product.price = price

        if category_id is not None:
            product.category_id = category_id

        if sort_order is not None:
            product.sort_order = sort_order

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
