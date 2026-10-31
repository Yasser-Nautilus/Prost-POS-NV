"""
Order status history repository — insert and query order status transitions.

INSERT-only: history records are never updated or deleted.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from broast_pos.core.models.order_status_history import OrderStatusHistory
from broast_pos.data.repositories.base_repository import BaseRepository


class OrderStatusHistoryRepository(BaseRepository[OrderStatusHistory]):
    """Persistence for order status transition records."""

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[OrderStatusHistory]:
        row = self._db.fetch_one(
            "SELECT * FROM order_status_history WHERE id = ?", (entity_id,)
        )
        return self._row_to_history(row) if row else None

    def save(self, entity: OrderStatusHistory) -> OrderStatusHistory:
        """Insert a new history record (UPDATE/DELETE are intentionally absent)."""
        return self.record_transition(
            order_id=entity.order_id,
            old_status=entity.old_status,
            new_status=entity.new_status,
            changed_by_id=entity.changed_by_id,
            changed_by_name=entity.changed_by_name,
            reason=entity.reason,
        )

    def delete(self, entity_id: int) -> None:
        """Status history records are NEVER deleted — immutable audit trail."""
        pass  # No-op

    # ------------------------------------------------------------------
    # Primary insert
    # ------------------------------------------------------------------

    def record_transition(
        self,
        order_id: int,
        old_status: Optional[str],
        new_status: str,
        changed_by_id: Optional[int] = None,
        changed_by_name: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> OrderStatusHistory:
        """Insert a status transition record and return it with the DB-assigned id."""
        self._db.execute(
            """INSERT INTO order_status_history
                   (order_id, old_status, new_status,
                    changed_by_id, changed_by_name, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (order_id, old_status, new_status,
             changed_by_id, changed_by_name, reason),
        )
        record_id = self._last_insert_id()
        self._db.commit()

        row = self._db.fetch_one(
            "SELECT * FROM order_status_history WHERE id = ?", (record_id,)
        )
        return self._row_to_history(row)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_for_order(self, order_id: int) -> List[OrderStatusHistory]:
        """Full timeline for a single order, chronological order."""
        rows = self._db.fetch_all(
            """SELECT * FROM order_status_history
               WHERE order_id = ?
               ORDER BY changed_at ASC""",
            (order_id,),
        )
        return [self._row_to_history(r) for r in rows]

    def get_for_date(self, date_str: str) -> List[OrderStatusHistory]:
        """All transitions recorded on a specific date (YYYY-MM-DD)."""
        rows = self._db.fetch_all(
            """SELECT * FROM order_status_history
               WHERE DATE(changed_at) = ?
               ORDER BY changed_at ASC""",
            (date_str,),
        )
        return [self._row_to_history(r) for r in rows]

    def get_by_status(self, new_status: str) -> List[OrderStatusHistory]:
        """All transitions TO a specific status (most recent first, limited)."""
        rows = self._db.fetch_all(
            """SELECT * FROM order_status_history
               WHERE new_status = ?
               ORDER BY changed_at DESC LIMIT 200""",
            (new_status,),
        )
        return [self._row_to_history(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_history(self, row: sqlite3.Row) -> OrderStatusHistory:
        return OrderStatusHistory(
            id=row["id"],
            order_id=row["order_id"],
            old_status=row["old_status"],
            new_status=row["new_status"],
            changed_by_id=row["changed_by_id"],
            changed_by_name=row["changed_by_name"],
            reason=row["reason"],
            changed_at=row["changed_at"],
        )
