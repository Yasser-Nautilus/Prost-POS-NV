"""
Audit repository — centralized audit trail logging.

Every privileged action (cancel, discount, shift open/close, user changes)
is logged here with event type, user info, and optional JSON details.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from broast_pos.data.repositories.base_repository import BaseRepository


class AuditEntry:
    """A single audit log entry (not a full model — read-only DTO)."""

    __slots__ = ("id", "event_type", "user_id", "user_name",
                 "order_id", "details", "timestamp")

    def __init__(
        self,
        id: Optional[int] = None,
        event_type: str = "",
        user_id: int = 0,
        user_name: str = "",
        order_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        self.id = id
        self.event_type = event_type
        self.user_id = user_id
        self.user_name = user_name
        self.order_id = order_id
        self.details = details
        self.timestamp = timestamp


class AuditRepository(BaseRepository[AuditEntry]):
    """Write and query the audit_log table."""

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[AuditEntry]:
        row = self._db.fetch_one("SELECT * FROM audit_log WHERE id = ?", (entity_id,))
        return self._row_to_entry(row) if row else None

    def save(self, entity: AuditEntry) -> AuditEntry:
        """Insert only — audit entries are immutable."""
        return self.log(
            event_type=entity.event_type,
            user_id=entity.user_id,
            user_name=entity.user_name,
            order_id=entity.order_id,
            details=entity.details,
        )

    def delete(self, entity_id: int) -> None:
        """Audit entries are NEVER deleted."""
        pass  # No-op

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def log(
        self,
        event_type: str,
        user_id: int,
        user_name: str,
        order_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Insert an audit log entry.

        Event types:
            order_cancelled, discount_applied, item_removed,
            shift_opened, shift_closed, shift_transferred,
            user_created, user_updated
        """
        details_json = json.dumps(details, ensure_ascii=False) if details else None
        self._db.execute(
            """INSERT INTO audit_log
                   (event_type, user_id, user_name, order_id, details)
               VALUES (?, ?, ?, ?, ?)""",
            (event_type, user_id, user_name, order_id, details_json),
        )
        entry_id = self._last_insert_id()
        self._db.commit()
        return AuditEntry(
            id=entry_id, event_type=event_type,
            user_id=user_id, user_name=user_name,
            order_id=order_id, details=details,
        )

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_logs_for_date(self, date_str: str) -> List[AuditEntry]:
        """All audit entries for a given date (YYYY-MM-DD)."""
        rows = self._db.fetch_all(
            "SELECT * FROM audit_log WHERE DATE(timestamp) = ? ORDER BY timestamp",
            (date_str,),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_logs_for_order(self, order_id: int) -> List[AuditEntry]:
        """Audit trail for a specific order."""
        rows = self._db.fetch_all(
            "SELECT * FROM audit_log WHERE order_id = ? ORDER BY timestamp",
            (order_id,),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_logs_by_user(self, user_id: int, limit: int = 50) -> List[AuditEntry]:
        """Audit trail for a specific user (most recent first)."""
        rows = self._db.fetch_all(
            """SELECT * FROM audit_log
               WHERE user_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (user_id, limit),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_logs_by_event_type(
        self,
        event_type: str,
        date_str: Optional[str] = None,
    ) -> List[AuditEntry]:
        """All logs of a specific event type, optionally scoped to a date."""
        if date_str:
            rows = self._db.fetch_all(
                """SELECT * FROM audit_log
                   WHERE event_type = ? AND DATE(timestamp) = ?
                   ORDER BY timestamp""",
                (event_type, date_str),
            )
        else:
            rows = self._db.fetch_all(
                """SELECT * FROM audit_log
                   WHERE event_type = ?
                   ORDER BY timestamp DESC LIMIT 100""",
                (event_type,),
            )
        return [self._row_to_entry(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        details_raw = row["details"]
        details = json.loads(details_raw) if details_raw else None
        return AuditEntry(
            id=row["id"],
            event_type=row["event_type"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            order_id=row["order_id"],
            details=details,
            timestamp=row["timestamp"],
        )
