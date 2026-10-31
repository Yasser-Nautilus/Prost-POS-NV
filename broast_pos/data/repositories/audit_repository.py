"""
Audit repository — centralized audit trail logging.

Every privileged action (cancel, discount, shift open/close, user changes)
is logged here with event type, user info, and optional JSON details.

INSERT-only: audit entries are immutable and never deleted.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from broast_pos.data.repositories.base_repository import BaseRepository


class AuditEntry:
    """A single audit log entry (not a full model — read-only DTO)."""

    __slots__ = (
        "id", "event_type", "user_id", "user_name",
        "order_id", "details", "timestamp",
        # Extended fields (v3 migration)
        "entity_type", "entity_id", "action", "reason",
        "before_data", "after_data",
    )

    def __init__(
        self,
        id: Optional[int] = None,
        event_type: str = "",
        user_id: int = 0,
        user_name: str = "",
        order_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        action: Optional[str] = None,
        reason: Optional[str] = None,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.id = id
        self.event_type = event_type
        self.user_id = user_id
        self.user_name = user_name
        self.order_id = order_id
        self.details = details
        self.timestamp = timestamp
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.action = action
        self.reason = reason
        self.before_data = before_data
        self.after_data = after_data


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
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            action=entity.action,
            reason=entity.reason,
            before_data=entity.before_data,
            after_data=entity.after_data,
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
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        action: Optional[str] = None,
        reason: Optional[str] = None,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Insert an audit log entry.

        The original 5-parameter signature is preserved for backward
        compatibility. New callers should use the extended parameters.

        Event types should come from AuditEventType constants:
            from broast_pos.core.models.audit import AuditEventType
        """
        details_json = json.dumps(details, ensure_ascii=False) if details else None
        before_json = json.dumps(before_data, ensure_ascii=False) if before_data else None
        after_json = json.dumps(after_data, ensure_ascii=False) if after_data else None

        self._db.execute(
            """INSERT INTO audit_log
                   (event_type, user_id, user_name, order_id, details,
                    entity_type, entity_id, action, reason, before_data, after_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, user_id, user_name, order_id, details_json,
             entity_type, entity_id, action, reason, before_json, after_json),
        )
        entry_id = self._last_insert_id()
        self._db.commit()
        return AuditEntry(
            id=entry_id,
            event_type=event_type,
            user_id=user_id,
            user_name=user_name,
            order_id=order_id,
            details=details,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            reason=reason,
            before_data=before_data,
            after_data=after_data,
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

    def get_logs_filtered(
        self,
        date_str: Optional[str] = None,
        user_id: Optional[int] = None,
        event_type: Optional[str] = None,
        order_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Flexible filter for the Audit Log viewer.

        All parameters are optional — combine as needed.
        Results are ordered by timestamp DESC (most recent first).
        """
        clauses = []
        params: list = []

        if date_str:
            clauses.append("DATE(timestamp) = ?")
            params.append(date_str)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if order_id is not None:
            clauses.append("order_id = ?")
            params.append(order_id)
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = self._db.fetch_all(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ?",
            tuple(params),
        )
        return [self._row_to_entry(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> AuditEntry:
        details_raw = row["details"]
        details = json.loads(details_raw) if details_raw else None

        # Extended fields (may be absent in old DB rows — use .get with fallback)
        def _safe_json(key: str) -> Optional[Dict]:
            try:
                raw = row[key]
                return json.loads(raw) if raw else None
            except (IndexError, KeyError):
                return None

        def _safe_str(key: str) -> Optional[str]:
            try:
                return row[key]
            except (IndexError, KeyError):
                return None

        def _safe_int(key: str) -> Optional[int]:
            try:
                return row[key]
            except (IndexError, KeyError):
                return None

        return AuditEntry(
            id=row["id"],
            event_type=row["event_type"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            order_id=row["order_id"],
            details=details,
            timestamp=row["timestamp"],
            entity_type=_safe_str("entity_type"),
            entity_id=_safe_int("entity_id"),
            action=_safe_str("action"),
            reason=_safe_str("reason"),
            before_data=_safe_json("before_data"),
            after_data=_safe_json("after_data"),
        )
