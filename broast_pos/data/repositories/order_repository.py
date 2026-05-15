"""
Order repository — all order-related database queries.

Handles order + items as a unit. No modifier joins — items are self-contained.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.data.repositories.base_repository import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """CRUD and query operations for orders and their items."""

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[Order]:
        row = self._db.fetch_one("SELECT * FROM orders WHERE id = ?", (entity_id,))
        if row is None:
            return None
        order = self._row_to_order(row)
        order.items = self._load_items(entity_id)
        return order

    def save(self, entity: Order) -> Order:
        if entity.id is None:
            return self._insert(entity)
        return self._update(entity)

    def delete(self, entity_id: int) -> None:
        """Soft-delete: cancel the order (orders don't have is_active)."""
        self._db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (OrderStatus.CANCELLED.value, entity_id),
        )

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_by_invoice(self, invoice_no: int, shift_id: int) -> Optional[Order]:
        """Lookup order by invoice number within a shift."""
        row = self._db.fetch_one(
            "SELECT * FROM orders WHERE invoice_no = ? AND shift_id = ?",
            (invoice_no, shift_id),
        )
        if row is None:
            return None
        order = self._row_to_order(row)
        order.items = self._load_items(order.id)
        return order

    def get_by_table(self, table_number: int) -> Optional[Order]:
        """Load the active dine-in order for a table."""
        row = self._db.fetch_one(
            """SELECT * FROM orders
               WHERE table_no = ? AND order_type = 'dine_in'
                 AND status NOT IN ('completed', 'cancelled')
               ORDER BY created_at DESC LIMIT 1""",
            (table_number,),
        )
        if row is None:
            return None
        order = self._row_to_order(row)
        order.items = self._load_items(order.id)
        return order

    def get_active_orders(self) -> List[Order]:
        """All non-completed, non-cancelled orders."""
        rows = self._db.fetch_all(
            "SELECT * FROM orders WHERE status NOT IN ('completed', 'cancelled') ORDER BY created_at"
        )
        return [self._row_to_order_with_items(r) for r in rows]

    def get_active_by_type(self, order_type: OrderType) -> List[Order]:
        """Active orders filtered by type (for tracking views)."""
        rows = self._db.fetch_all(
            """SELECT * FROM orders
               WHERE order_type = ? AND status NOT IN ('completed', 'cancelled')
               ORDER BY created_at""",
            (order_type.value,),
        )
        return [self._row_to_order_with_items(r) for r in rows]

    def get_unassigned_deliveries(self) -> List[Order]:
        """Delivery orders not yet assigned to a driver (from both cashiers)."""
        rows = self._db.fetch_all(
            """SELECT * FROM orders
               WHERE order_type = 'delivery' AND driver_id IS NULL
                 AND status NOT IN ('completed', 'cancelled')
               ORDER BY created_at"""
        )
        return [self._row_to_order_with_items(r) for r in rows]

    def get_today_orders(self) -> List[Order]:
        """All orders created today (current shift)."""
        rows = self._db.fetch_all(
            "SELECT * FROM orders WHERE DATE(created_at) = DATE('now') ORDER BY created_at"
        )
        return [self._row_to_order_with_items(r) for r in rows]

    def get_orders_for_report(self, date_str: str) -> List[Order]:
        """Non-cancelled orders for a specific date (YYYY-MM-DD)."""
        rows = self._db.fetch_all(
            """SELECT * FROM orders
               WHERE DATE(created_at) = ? AND status != 'cancelled'
               ORDER BY invoice_no""",
            (date_str,),
        )
        return [self._row_to_order_with_items(r) for r in rows]

    def get_orders_for_trip(self, order_ids: List[int]) -> List[Order]:
        """Load multiple orders by ID list (for trip details)."""
        if not order_ids:
            return []
        placeholders = ",".join("?" for _ in order_ids)
        rows = self._db.fetch_all(
            f"SELECT * FROM orders WHERE id IN ({placeholders}) ORDER BY invoice_no",
            tuple(order_ids),
        )
        return [self._row_to_order_with_items(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_order(self, row: sqlite3.Row) -> Order:
        """Map a database row to an Order object."""
        return Order(
            id=row["id"],
            invoice_no=row["invoice_no"],
            shift_id=row["shift_id"],
            order_type=OrderType(row["order_type"]),
            status=OrderStatus(row["status"]),
            table_no=row["table_no"],
            customer_id=row["customer_id"],
            customer_name=row["customer_name"],
            customer_phone=row["customer_phone"],
            customer_address=row["customer_address"],
            customer_zone=row["customer_zone"],
            delivery_fee=row["delivery_fee"] or 0.0,
            driver_id=row["driver_id"],
            driver_name=row["driver_name"],
            subtotal=row["subtotal"] or 0.0,
            discount_amount=row["discount_amount"] or 0.0,
            discount_type=row["discount_type"],
            service_amount=row["service_amount"] or 0.0,
            total=row["total"] or 0.0,
            payment_method=PaymentMethod(row["payment_method"]) if row["payment_method"] else None,
            amount_paid=row["amount_paid"] or 0.0,
            change_given=row["change_given"] or 0.0,
            is_paid=bool(row["is_paid"]),
            paid_at=row["paid_at"],
            created_by_id=row["created_by_id"],
            created_by_name=row["created_by_name"],
            cashier_slot=row["cashier_slot"],
            cancelled_by_id=row["cancelled_by_id"],
            cancelled_by_name=row["cancelled_by_name"],
            cancel_reason=row["cancel_reason"],
            cancelled_at=row["cancelled_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_order_with_items(self, row: sqlite3.Row) -> Order:
        """Map row to Order and load its items."""
        order = self._row_to_order(row)
        order.items = self._load_items(order.id)
        return order

    def _load_items(self, order_id: int) -> List[OrderItem]:
        """Load all items for an order — no modifier joins needed."""
        rows = self._db.fetch_all(
            "SELECT * FROM order_items WHERE order_id = ?",
            (order_id,),
        )
        return [
            OrderItem(
                id=r["id"],
                product_id=r["product_id"],
                product_name=r["product_name"],
                quantity=r["quantity"],
                unit_price=r["unit_price"],
                notes=r["notes"] or "",
            )
            for r in rows
        ]

    def _insert(self, order: Order) -> Order:
        """Insert a new order and its items."""
        self._db.execute(
            """INSERT INTO orders (
                   invoice_no, shift_id, order_type, status, table_no,
                   customer_id, customer_name, customer_phone,
                   customer_address, customer_zone, delivery_fee,
                   driver_id, driver_name,
                   subtotal, discount_amount, discount_type, service_amount, total,
                   payment_method, amount_paid, change_given, is_paid, paid_at,
                   created_by_id, created_by_name, cashier_slot,
                   cancelled_by_id, cancelled_by_name, cancel_reason, cancelled_at
               ) VALUES (
                   ?, ?, ?, ?, ?,
                   ?, ?, ?,
                   ?, ?, ?,
                   ?, ?,
                   ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?,
                   ?, ?, ?,
                   ?, ?, ?, ?
               )""",
            (
                order.invoice_no, order.shift_id,
                order.order_type.value, order.status.value, order.table_no,
                order.customer_id, order.customer_name, order.customer_phone,
                order.customer_address, order.customer_zone, order.delivery_fee,
                order.driver_id, order.driver_name,
                order.subtotal, order.discount_amount, order.discount_type,
                order.service_amount, order.total,
                order.payment_method.value if order.payment_method else None,
                order.amount_paid, order.change_given,
                1 if order.is_paid else 0, order.paid_at,
                order.created_by_id, order.created_by_name, order.cashier_slot,
                order.cancelled_by_id, order.cancelled_by_name,
                order.cancel_reason, order.cancelled_at,
            ),
        )
        order.id = self._last_insert_id()
        self._save_items(order.id, order.items)
        self._db.commit()
        return order

    def _update(self, order: Order) -> Order:
        """Update an existing order and replace its items."""
        self._db.execute(
            """UPDATE orders SET
                   order_type = ?, status = ?, table_no = ?,
                   customer_id = ?, customer_name = ?, customer_phone = ?,
                   customer_address = ?, customer_zone = ?, delivery_fee = ?,
                   driver_id = ?, driver_name = ?,
                   subtotal = ?, discount_amount = ?, discount_type = ?,
                   service_amount = ?, total = ?,
                   payment_method = ?, amount_paid = ?, change_given = ?,
                   is_paid = ?, paid_at = ?,
                   cancelled_by_id = ?, cancelled_by_name = ?,
                   cancel_reason = ?, cancelled_at = ?,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (
                order.order_type.value, order.status.value, order.table_no,
                order.customer_id, order.customer_name, order.customer_phone,
                order.customer_address, order.customer_zone, order.delivery_fee,
                order.driver_id, order.driver_name,
                order.subtotal, order.discount_amount, order.discount_type,
                order.service_amount, order.total,
                order.payment_method.value if order.payment_method else None,
                order.amount_paid, order.change_given,
                1 if order.is_paid else 0, order.paid_at,
                order.cancelled_by_id, order.cancelled_by_name,
                order.cancel_reason, order.cancelled_at,
                order.id,
            ),
        )
        # Replace items: delete old, insert new
        self._db.execute("DELETE FROM order_items WHERE order_id = ?", (order.id,))
        self._save_items(order.id, order.items)
        self._db.commit()
        return order

    def _save_items(self, order_id: int, items: List[OrderItem]) -> None:
        """Insert all items for an order."""
        for item in items:
            self._db.execute(
                """INSERT INTO order_items
                       (order_id, product_id, product_name, quantity,
                        unit_price, total_price, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    order_id, item.product_id, item.product_name,
                    item.quantity, item.unit_price, item.total_price,
                    item.notes or None,
                ),
            )
