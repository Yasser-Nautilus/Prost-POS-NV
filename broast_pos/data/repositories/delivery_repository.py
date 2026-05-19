"""
Delivery repository — trip lifecycle, driver attendance, and settlement queries.

Trip lifecycle: created → dispatched → returned → settled (each step independent).
No settlement blocking — driver can go on new trips with unsettled previous trips.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from broast_pos.core.models.delivery import (
    DeliveryTrip,
    DriverAttendance,
    DriverStatus,
)
from broast_pos.data.repositories.base_repository import BaseRepository


class DeliveryRepository(BaseRepository[DeliveryTrip]):
    """CRUD and query operations for delivery trips and driver attendance."""

    # ------------------------------------------------------------------
    # Core contract (for DeliveryTrip)
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[DeliveryTrip]:
        row = self._db.fetch_one(
            "SELECT * FROM delivery_trips WHERE id = ?", (entity_id,)
        )
        if row is None:
            return None
        trip = self._row_to_trip(row)
        trip.order_ids = self._load_trip_order_ids(entity_id)
        return trip

    def save(self, entity: DeliveryTrip) -> DeliveryTrip:
        return self.create_trip(entity.driver_id, entity.order_ids,
                                entity.driver_name)

    def delete(self, entity_id: int) -> None:
        """Trips are never deleted — they are historical records."""
        pass  # No-op

    # ------------------------------------------------------------------
    # Driver attendance
    # ------------------------------------------------------------------

    def check_in(self, driver_id: int) -> DriverAttendance:
        """Create attendance record with check_in_at timestamp."""
        self._db.execute(
            "INSERT INTO driver_attendance (driver_id) VALUES (?)",
            (driver_id,),
        )
        att_id = self._last_insert_id()
        self._db.commit()
        return DriverAttendance(id=att_id, driver_id=driver_id)

    def check_out(self, driver_id: int) -> None:
        """Update the latest open attendance record with check_out_at."""
        self._db.execute(
            """UPDATE driver_attendance
               SET check_out_at = datetime('now')
               WHERE driver_id = ? AND check_out_at IS NULL""",
            (driver_id,),
        )
        self._db.commit()

    def get_checked_in_drivers(self) -> List[DriverAttendance]:
        """All currently active drivers (checked in, not checked out)."""
        rows = self._db.fetch_all(
            """SELECT * FROM driver_attendance
               WHERE check_out_at IS NULL
               ORDER BY check_in_at"""
        )
        return [self._row_to_attendance(r) for r in rows]

    def get_driver_status(self, driver_id: int) -> DriverStatus:
        """Determine current driver status: CHECKED_OUT / AVAILABLE / OUT."""
        # Check if driver is checked in
        att = self._db.fetch_one(
            """SELECT * FROM driver_attendance
               WHERE driver_id = ? AND check_out_at IS NULL""",
            (driver_id,),
        )
        if att is None:
            return DriverStatus.CHECKED_OUT

        # Check if driver has an active (dispatched but not returned) trip
        active_trip = self._db.fetch_one(
            """SELECT id FROM delivery_trips
               WHERE driver_id = ? AND dispatched_at IS NOT NULL
                 AND returned_at IS NULL""",
            (driver_id,),
        )
        if active_trip is not None:
            return DriverStatus.OUT

        return DriverStatus.AVAILABLE

    # ------------------------------------------------------------------
    # Trip lifecycle
    # ------------------------------------------------------------------

    def create_trip(self, driver_id: int, order_ids: List[int],
                    driver_name: str = "") -> DeliveryTrip:
        """Create a new trip record with associated orders."""
        self._db.execute(
            "INSERT INTO delivery_trips (driver_id, driver_name) VALUES (?, ?)",
            (driver_id, driver_name),
        )
        trip_id = self._last_insert_id()

        # Link orders to trip
        for order_id in order_ids:
            self._db.execute(
                "INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (?, ?)",
                (trip_id, order_id),
            )
        self._db.commit()

        return DeliveryTrip(
            id=trip_id, driver_id=driver_id, driver_name=driver_name,
            order_ids=order_ids,
        )

    def mark_dispatched(self, trip_id: int) -> None:
        """Set dispatched_at timestamp."""
        self._db.execute(
            "UPDATE delivery_trips SET dispatched_at = datetime('now') WHERE id = ?",
            (trip_id,),
        )
        self._db.commit()

    def mark_returned(self, trip_id: int) -> None:
        """Set returned_at timestamp."""
        self._db.execute(
            "UPDATE delivery_trips SET returned_at = datetime('now') WHERE id = ?",
            (trip_id,),
        )
        self._db.commit()

    def mark_settled(self, trip_id: int, cash_collected: float,
                     total_delivery_fees: float) -> None:
        """Set settled_at timestamp and financial snapshots."""
        self._db.execute(
            """UPDATE delivery_trips SET
                   settled_at = datetime('now'), is_settled = 1,
                   cash_collected = ?, total_delivery_fees = ?
               WHERE id = ?""",
            (cash_collected, total_delivery_fees, trip_id),
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Trip queries
    # ------------------------------------------------------------------

    def get_active_trips(self) -> List[DeliveryTrip]:
        """Trips dispatched but not yet returned."""
        rows = self._db.fetch_all(
            """SELECT * FROM delivery_trips
               WHERE dispatched_at IS NOT NULL AND returned_at IS NULL
               ORDER BY dispatched_at"""
        )
        return [self._row_to_trip_with_orders(r) for r in rows]

    def get_unsettled_trips(self, driver_id: Optional[int] = None) -> List[DeliveryTrip]:
        """Returned but not settled trips (optional driver filter)."""
        if driver_id is not None:
            rows = self._db.fetch_all(
                """SELECT * FROM delivery_trips
                   WHERE returned_at IS NOT NULL AND is_settled = 0
                     AND driver_id = ?
                   ORDER BY returned_at""",
                (driver_id,),
            )
        else:
            rows = self._db.fetch_all(
                """SELECT * FROM delivery_trips
                   WHERE returned_at IS NOT NULL AND is_settled = 0
                   ORDER BY returned_at"""
            )
        return [self._row_to_trip_with_orders(r) for r in rows]

    def get_trip_with_orders(self, trip_id: int) -> Optional[DeliveryTrip]:
        """Full trip detail including order list."""
        return self.get_by_id(trip_id)

    # ------------------------------------------------------------------
    # End-of-day queries
    # ------------------------------------------------------------------

    def get_all_drivers_daily_summary(self, date_str: str) -> List[Dict]:
        """Per-driver summary: trip count, order count, fees earned."""
        rows = self._db.fetch_all(
            """SELECT
                   dt.driver_id,
                   dt.driver_name,
                   COUNT(DISTINCT dt.id) AS trip_count,
                   COUNT(dto.order_id) AS order_count,
                   COALESCE(SUM(dt.total_delivery_fees), 0) AS fees_earned
               FROM delivery_trips dt
               LEFT JOIN delivery_trip_orders dto ON dto.trip_id = dt.id
               WHERE DATE(dt.created_at) = ?
               GROUP BY dt.driver_id, dt.driver_name
               ORDER BY dt.driver_name""",
            (date_str,),
        )
        return [
            {
                "driver_id": r["driver_id"],
                "driver_name": r["driver_name"],
                "trip_count": r["trip_count"],
                "order_count": r["order_count"],
                "fees_earned": r["fees_earned"],
            }
            for r in rows
        ]

    def get_driver_daily_trips(self, driver_id: int,
                               date_str: str) -> List[DeliveryTrip]:
        """All trips for one driver on a date."""
        rows = self._db.fetch_all(
            """SELECT * FROM delivery_trips
               WHERE driver_id = ? AND DATE(created_at) = ?
               ORDER BY created_at""",
            (driver_id, date_str),
        )
        return [self._row_to_trip_with_orders(r) for r in rows]

    def get_daily_summary(self, date_str: str) -> List[Dict]:
        """Alias for get_all_drivers_daily_summary — used by ReportService."""
        return self.get_all_drivers_daily_summary(date_str)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_trip_order_ids(self, trip_id: int) -> List[int]:
        """Load order IDs for a trip from the join table."""
        rows = self._db.fetch_all(
            "SELECT order_id FROM delivery_trip_orders WHERE trip_id = ?",
            (trip_id,),
        )
        return [r["order_id"] for r in rows]

    def _row_to_trip(self, row: sqlite3.Row) -> DeliveryTrip:
        return DeliveryTrip(
            id=row["id"],
            driver_id=row["driver_id"],
            driver_name=row["driver_name"],
            created_at=row["created_at"],
            dispatched_at=row["dispatched_at"],
            returned_at=row["returned_at"],
            settled_at=row["settled_at"],
            cash_collected=row["cash_collected"],
            total_delivery_fees=row["total_delivery_fees"],
            is_settled=bool(row["is_settled"]),
        )

    def _row_to_trip_with_orders(self, row: sqlite3.Row) -> DeliveryTrip:
        trip = self._row_to_trip(row)
        trip.order_ids = self._load_trip_order_ids(trip.id)
        return trip

    def _row_to_attendance(self, row: sqlite3.Row) -> DriverAttendance:
        return DriverAttendance(
            id=row["id"],
            driver_id=row["driver_id"],
            check_in_at=row["check_in_at"],
            check_out_at=row["check_out_at"],
        )
