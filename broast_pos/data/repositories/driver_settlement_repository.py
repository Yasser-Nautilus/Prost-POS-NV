"""
Driver settlement repository — INSERT-only permanent financial records.

Settlement records are immutable once created. They represent the
authoritative historical record of what was paid on a given date.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from broast_pos.core.models.driver_settlement import DriverSettlement
from broast_pos.data.repositories.base_repository import BaseRepository


class DriverSettlementRepository(BaseRepository[DriverSettlement]):
    """Persistence for driver settlement records."""

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[DriverSettlement]:
        row = self._db.fetch_one(
            "SELECT * FROM driver_settlements WHERE id = ?", (entity_id,)
        )
        return self._row_to_settlement(row) if row else None

    def save(self, entity: DriverSettlement) -> DriverSettlement:
        """Insert a new settlement record.

        Settlement records are immutable — no UPDATE path.
        """
        return self.create_settlement(entity)

    def delete(self, entity_id: int) -> None:
        """Settlement records are NEVER deleted — financial history."""
        pass  # No-op

    # ------------------------------------------------------------------
    # Primary insert
    # ------------------------------------------------------------------

    def create_settlement(self, settlement: DriverSettlement) -> DriverSettlement:
        """Persist a new settlement record and return it with DB-assigned id.

        This is called from within an existing transaction (BEGIN by the
        DriverSettlementService), so we do NOT commit here.
        """
        self._db.execute(
            """INSERT INTO driver_settlements
                   (driver_id, driver_name, settlement_date,
                    trip_count, order_count,
                    total_order_value, cash_collected, online_paid, total_delivery_fees,
                    settled_by_id, settled_by_name, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                settlement.driver_id,
                settlement.driver_name,
                settlement.settlement_date,
                settlement.trip_count,
                settlement.order_count,
                settlement.total_order_value,
                settlement.cash_collected,
                settlement.online_paid,
                settlement.total_delivery_fees,
                settlement.settled_by_id,
                settlement.settled_by_name,
                settlement.notes,
            ),
        )
        settlement.id = self._last_insert_id()
        return settlement

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_by_driver_date(
        self, driver_id: int, date_str: str
    ) -> Optional[DriverSettlement]:
        """Find settlement record for a specific driver on a specific date."""
        row = self._db.fetch_one(
            """SELECT * FROM driver_settlements
               WHERE driver_id = ? AND settlement_date = ?
               ORDER BY settled_at DESC LIMIT 1""",
            (driver_id, date_str),
        )
        return self._row_to_settlement(row) if row else None

    def get_by_driver(self, driver_id: int) -> List[DriverSettlement]:
        """All settlement records for a driver, newest first."""
        rows = self._db.fetch_all(
            """SELECT * FROM driver_settlements
               WHERE driver_id = ?
               ORDER BY settlement_date DESC, settled_at DESC""",
            (driver_id,),
        )
        return [self._row_to_settlement(r) for r in rows]

    def get_for_date(self, date_str: str) -> List[DriverSettlement]:
        """All settlement records for a specific date."""
        rows = self._db.fetch_all(
            """SELECT * FROM driver_settlements
               WHERE settlement_date = ?
               ORDER BY settled_at ASC""",
            (date_str,),
        )
        return [self._row_to_settlement(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_settlement(self, row: sqlite3.Row) -> DriverSettlement:
        return DriverSettlement(
            id=row["id"],
            driver_id=row["driver_id"],
            driver_name=row["driver_name"],
            settlement_date=row["settlement_date"],
            trip_count=row["trip_count"],
            order_count=row["order_count"],
            total_order_value=row["total_order_value"],
            cash_collected=row["cash_collected"],
            online_paid=row["online_paid"],
            total_delivery_fees=row["total_delivery_fees"],
            settled_by_id=row["settled_by_id"],
            settled_by_name=row["settled_by_name"],
            notes=row["notes"],
            settled_at=row["settled_at"],
        )
