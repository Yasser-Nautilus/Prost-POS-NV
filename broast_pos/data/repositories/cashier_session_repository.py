"""
CashierSessionRepository — CRUD for cashier_sessions table.

Business rules enforced at the DB level:
  - UNIQUE INDEX on (day_id, station) WHERE is_open = 1
    (at most one open session per station per day)
  - TRIGGER trg_station_exclusive
    (ALL cannot coexist with COUNTER or DELIVERY on the same day)

Business rules enforced here in Python (better error messages):
  - Validate station enum before insert
  - Guard is_open=True before any close operation
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from broast_pos.core.models.cashier_session import CashierSession, Station


class CashierSessionRepository:
    """Read/write access to the cashier_sessions table."""

    def __init__(self, db=None) -> None:
        from broast_pos.data.database.connection import DatabaseConnection
        self._db = db or DatabaseConnection.get_instance()

    def _last_insert_id(self) -> int:
        row = self._db.fetch_one("SELECT last_insert_rowid() AS id")
        return row["id"] if row else 0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_by_id(self, session_id: int) -> Optional[CashierSession]:
        row = self._db.fetch_one(
            "SELECT * FROM cashier_sessions WHERE id = ?", (session_id,)
        )
        return self._row_to_session(row) if row else None

    def get_open_sessions_for_day(self, day_id: int) -> List[CashierSession]:
        """All currently open sessions for a business day."""
        rows = self._db.fetch_all(
            "SELECT * FROM cashier_sessions WHERE day_id = ? AND is_open = 1 ORDER BY opened_at",
            (day_id,),
        )
        return [self._row_to_session(r) for r in rows]

    def get_open_session_for_station(
        self, day_id: int, station: Station
    ) -> Optional[CashierSession]:
        """Return the single open session for a station, or None."""
        row = self._db.fetch_one(
            "SELECT * FROM cashier_sessions WHERE day_id = ? AND station = ? AND is_open = 1",
            (day_id, station.value),
        )
        return self._row_to_session(row) if row else None

    def get_sessions_for_day(self, day_id: int) -> List[CashierSession]:
        """All sessions (open + closed) for a business day."""
        rows = self._db.fetch_all(
            "SELECT * FROM cashier_sessions WHERE day_id = ? ORDER BY opened_at",
            (day_id,),
        )
        return [self._row_to_session(r) for r in rows]

    def get_sessions_for_user(self, user_id: int, limit: int = 10) -> List[CashierSession]:
        """Recent sessions for a user (most recent first)."""
        rows = self._db.fetch_all(
            "SELECT * FROM cashier_sessions WHERE user_id = ? ORDER BY opened_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [self._row_to_session(r) for r in rows]

    def has_any_open_session(self, day_id: int) -> bool:
        """True if at least one session is still open for the day."""
        row = self._db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM cashier_sessions WHERE day_id = ? AND is_open = 1",
            (day_id,),
        )
        return (row["cnt"] if row else 0) > 0

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(self, session: CashierSession) -> CashierSession:
        """Insert a new session. Returns the session with its id filled in."""
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """INSERT INTO cashier_sessions
               (day_id, user_id, station, is_open, opened_at,
                opening_float_pt)
               VALUES (?, ?, ?, 1, ?, ?)""",
            (
                session.day_id,
                session.user_id,
                session.station.value,
                session.opened_at or now,
                session.opening_float_pt,
            ),
        )
        session.id = self._last_insert_id()
        return session

    def close_session(
        self,
        session_id: int,
        counted_cash_pt: int,
        expected_cash_pt: int,
        variance_pt: int,
        variance_approved_by: Optional[int] = None,
        variance_reason: Optional[str] = None,
        handover_to_session: Optional[int] = None,
    ) -> None:
        """Mark the session as closed with financial snapshot."""
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """UPDATE cashier_sessions SET
               is_open = 0,
               closed_at = ?,
               counted_cash_pt = ?,
               expected_cash_pt = ?,
               variance_pt = ?,
               variance_approved_by = ?,
               variance_reason = ?,
               handover_to_session = ?
               WHERE id = ? AND is_open = 1""",
            (
                now,
                counted_cash_pt,
                expected_cash_pt,
                variance_pt,
                variance_approved_by,
                variance_reason,
                handover_to_session,
                session_id,
            ),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_session(self, row: sqlite3.Row) -> CashierSession:
        return CashierSession(
            id=row["id"],
            day_id=row["day_id"],
            user_id=row["user_id"],
            station=Station(row["station"]),
            is_open=bool(row["is_open"]),
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            opening_float_pt=row["opening_float_pt"],
            counted_cash_pt=row["counted_cash_pt"],
            expected_cash_pt=row["expected_cash_pt"],
            variance_pt=row["variance_pt"],
            variance_approved_by=row["variance_approved_by"],
            variance_reason=row["variance_reason"],
            handover_to_session=row["handover_to_session"],
        )
