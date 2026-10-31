"""
Customer repository — customer, address, and zone database queries.

Phone is the primary lookup key (11-digit Egyptian, starts with 01).
Zone delivery fee is fixed — cashier cannot change it per order.

Customer history methods query the orders table directly — no extra
tables are needed since customers are always linked to orders by customer_id.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from broast_pos.core.models.customer import Customer, CustomerAddress, Zone
from broast_pos.data.repositories.base_repository import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """CRUD and query operations for customers, addresses, and zones."""

    # ------------------------------------------------------------------
    # Core contract (for Customer)
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[Customer]:
        row = self._db.fetch_one("SELECT * FROM customers WHERE id = ?", (entity_id,))
        if row is None:
            return None
        customer = self._row_to_customer(row)
        customer.addresses = self.get_addresses(customer.id)
        return customer

    def save(self, entity: Customer) -> Customer:
        return self.save_customer(entity)

    def delete(self, entity_id: int) -> None:
        """Customers are never deleted — they are historical records."""
        pass  # No-op: customers don't have is_active

    # ------------------------------------------------------------------
    # Customer queries
    # ------------------------------------------------------------------

    def find_by_phone(self, phone: str) -> Optional[Customer]:
        """Exact phone match — return customer with all addresses, or None."""
        row = self._db.fetch_one(
            "SELECT * FROM customers WHERE phone = ?", (phone,)
        )
        if row is None:
            return None
        customer = self._row_to_customer(row)
        customer.addresses = self.get_addresses(customer.id)
        return customer

    def save_customer(self, customer: Customer) -> Customer:
        """Insert or update a customer."""
        if customer.id is None:
            self._db.execute(
                "INSERT INTO customers (name, phone, notes) VALUES (?, ?, ?)",
                (customer.name, customer.phone, customer.notes),
            )
            customer.id = self._last_insert_id()
        else:
            self._db.execute(
                "UPDATE customers SET name = ?, phone = ?, notes = ? WHERE id = ?",
                (customer.name, customer.phone, customer.notes, customer.id),
            )
        self._db.commit()
        return customer

    # ------------------------------------------------------------------
    # Address queries
    # ------------------------------------------------------------------

    def get_addresses(self, customer_id: int) -> List[CustomerAddress]:
        """All saved addresses for a customer."""
        rows = self._db.fetch_all(
            "SELECT * FROM customer_addresses WHERE customer_id = ?",
            (customer_id,),
        )
        return [self._row_to_address(r) for r in rows]

    def save_address(self, address: CustomerAddress) -> CustomerAddress:
        """Create a new address (street_name + zone_id + copied fee)."""
        if address.id is None:
            self._db.execute(
                """INSERT INTO customer_addresses
                       (customer_id, street_name, zone_id, zone_name, delivery_fee)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    address.customer_id, address.street_name,
                    address.zone_id, address.zone_name, address.delivery_fee,
                ),
            )
            address.id = self._last_insert_id()
        else:
            self._db.execute(
                """UPDATE customer_addresses SET
                       street_name = ?, zone_id = ?, zone_name = ?, delivery_fee = ?
                   WHERE id = ?""",
                (
                    address.street_name, address.zone_id,
                    address.zone_name, address.delivery_fee, address.id,
                ),
            )
        self._db.commit()
        return address

    # ------------------------------------------------------------------
    # Customer order history
    # ------------------------------------------------------------------

    def get_customer_order_history(
        self,
        customer_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Order history for a customer (newest first).

        Returns lightweight dicts (not full Order objects) to keep the
        query fast and the payload small for the frontend.
        """
        rows = self._db.fetch_all(
            """SELECT id, invoice_no, order_type, status,
                      total, payment_method, is_paid,
                      customer_address, customer_zone,
                      created_at, cancelled_at, cancel_reason
               FROM orders
               WHERE customer_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (customer_id, limit, offset),
        )
        return [
            {
                "id": r["id"],
                "invoice_no": r["invoice_no"],
                "order_type": r["order_type"],
                "status": r["status"],
                "total": r["total"],
                "payment_method": r["payment_method"],
                "is_paid": bool(r["is_paid"]),
                "customer_address": r["customer_address"],
                "customer_zone": r["customer_zone"],
                "created_at": r["created_at"],
                "cancelled_at": r["cancelled_at"],
                "cancel_reason": r["cancel_reason"],
            }
            for r in rows
        ]

    def get_customer_statistics(self, customer_id: int) -> Dict[str, Any]:
        """Aggregate stats for a customer (single query, no Python loop)."""
        row = self._db.fetch_one(
            """SELECT
                   COUNT(*)  AS total_orders,
                   SUM(CASE WHEN status = 'completed'  THEN 1 ELSE 0 END) AS completed_orders,
                   SUM(CASE WHEN status = 'cancelled'  THEN 1 ELSE 0 END) AS cancelled_orders,
                   SUM(CASE WHEN status NOT IN ('completed','cancelled') THEN 1 ELSE 0 END) AS active_orders,
                   SUM(CASE WHEN status = 'completed'  THEN total ELSE 0 END) AS total_spent,
                   AVG(CASE WHEN status = 'completed'  THEN total END)       AS avg_order_value,
                   MAX(CASE WHEN status = 'completed'  THEN total END)       AS largest_order,
                   MIN(created_at) AS first_order_at,
                   MAX(created_at) AS last_order_at
               FROM orders
               WHERE customer_id = ?""",
            (customer_id,),
        )
        if row is None:
            return {
                "total_orders": 0, "completed_orders": 0, "cancelled_orders": 0,
                "active_orders": 0, "total_spent": 0.0, "avg_order_value": 0.0,
                "largest_order": 0.0, "first_order_at": None, "last_order_at": None,
            }
        return {
            "total_orders": row["total_orders"] or 0,
            "completed_orders": row["completed_orders"] or 0,
            "cancelled_orders": row["cancelled_orders"] or 0,
            "active_orders": row["active_orders"] or 0,
            "total_spent": round(row["total_spent"] or 0.0, 2),
            "avg_order_value": round(row["avg_order_value"] or 0.0, 2),
            "largest_order": round(row["largest_order"] or 0.0, 2),
            "first_order_at": row["first_order_at"],
            "last_order_at": row["last_order_at"],
        }

    # ------------------------------------------------------------------
    # Zone queries (manager only)
    # ------------------------------------------------------------------

    def get_all_active_zones(self) -> List[Zone]:
        """All active zones — for dropdown in customer panel."""
        rows = self._db.fetch_all(
            "SELECT * FROM zones WHERE is_active = 1 ORDER BY name"
        )
        return [self._row_to_zone(r) for r in rows]

    def get_zones(self) -> List[Zone]:
        """All zones (active and inactive) — for zone management screen."""
        rows = self._db.fetch_all(
            "SELECT * FROM zones ORDER BY name"
        )
        return [self._row_to_zone(r) for r in rows]

    def get_zone_by_id(self, zone_id: int) -> Optional[Zone]:
        """Fetch a single zone."""
        row = self._db.fetch_one("SELECT * FROM zones WHERE id = ?", (zone_id,))
        return self._row_to_zone(row) if row else None

    def save_zone(self, zone: Zone) -> Zone:
        """Create or update a zone (name + delivery_fee)."""
        if zone.id is None:
            self._db.execute(
                "INSERT INTO zones (name, delivery_fee, is_active) VALUES (?, ?, ?)",
                (zone.name, zone.delivery_fee, 1 if zone.is_active else 0),
            )
            zone.id = self._last_insert_id()
        else:
            self._db.execute(
                """UPDATE zones SET name = ?, delivery_fee = ?, is_active = ?
                   WHERE id = ?""",
                (zone.name, zone.delivery_fee, 1 if zone.is_active else 0, zone.id),
            )
        self._db.commit()
        return zone

    def deactivate_zone(self, zone_id: int) -> None:
        """Soft-delete a zone."""
        self._db.execute(
            "UPDATE zones SET is_active = 0 WHERE id = ?", (zone_id,)
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_customer(self, row: sqlite3.Row) -> Customer:
        return Customer(
            id=row["id"],
            name=row["name"],
            phone=row["phone"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def _row_to_address(self, row: sqlite3.Row) -> CustomerAddress:
        return CustomerAddress(
            id=row["id"],
            customer_id=row["customer_id"],
            street_name=row["street_name"],
            zone_id=row["zone_id"],
            zone_name=row["zone_name"],
            delivery_fee=row["delivery_fee"],
        )

    def _row_to_zone(self, row: sqlite3.Row) -> Zone:
        return Zone(
            id=row["id"],
            name=row["name"],
            delivery_fee=row["delivery_fee"],
            is_active=bool(row["is_active"]),
        )
