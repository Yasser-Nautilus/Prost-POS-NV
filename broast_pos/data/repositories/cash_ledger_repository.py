"""
CashLedgerRepository — append-only access to the cash_ledger table.

The DB enforces immutability via triggers:
  - BEFORE UPDATE → RAISE ABORT
  - BEFORE DELETE → RAISE ABORT

The DB enforces idempotency via partial unique indexes:
  - UNIQUE(order_id) WHERE entry_type = 'SALE_CASH'
  - UNIQUE(trip_id)  WHERE entry_type = 'DRIVER_REMITTANCE'

This repo only adds entries and reads them. It NEVER updates or deletes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from broast_pos.core.models.cashier_session import CashLedgerEntry, LedgerEntryType


class CashLedgerRepository:
    """Append-only access to cash_ledger. All balance calculations go through here."""

    def __init__(self, db=None) -> None:
        from broast_pos.data.database.connection import DatabaseConnection
        self._db = db or DatabaseConnection.get_instance()

    def _last_insert_id(self) -> int:
        row = self._db.fetch_one("SELECT last_insert_rowid() AS id")
        return row["id"] if row else 0

    # ------------------------------------------------------------------
    # The one financial formula
    # ------------------------------------------------------------------

    def get_session_balance_pt(self, session_id: int) -> int:
        """
        Compute the current expected drawer balance for a session.

        Formula (the ONLY authorised way to compute drawer balance):
            SUM(amount_pt) WHERE session_id = ?

        Returns piasters (integer). Divide by 100 for EGP display.
        """
        row = self._db.fetch_one(
            "SELECT COALESCE(SUM(amount_pt), 0) AS balance FROM cash_ledger WHERE session_id = ?",
            (session_id,),
        )
        return int(row["balance"]) if row else 0

    def get_day_balance_pt(self, day_id: int) -> int:
        """Aggregate balance across all sessions of a business day."""
        row = self._db.fetch_one(
            "SELECT COALESCE(SUM(amount_pt), 0) AS balance FROM cash_ledger WHERE day_id = ?",
            (day_id,),
        )
        return int(row["balance"]) if row else 0

    def get_session_balance_by_type(self, session_id: int) -> dict:
        """
        Break down the session balance by entry_type.

        Returns: {entry_type_value: total_pt, ...}
        Useful for X-Report and Z-Report breakdown.
        """
        rows = self._db.fetch_all(
            """SELECT entry_type, COALESCE(SUM(amount_pt), 0) AS total
               FROM cash_ledger
               WHERE session_id = ?
               GROUP BY entry_type""",
            (session_id,),
        )
        return {r["entry_type"]: int(r["total"]) for r in rows}

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(self, entry: CashLedgerEntry) -> CashLedgerEntry:
        """
        Add a single entry to the ledger.

        Raises:
            sqlite3.IntegrityError: duplicate SALE_CASH for same order,
                duplicate DRIVER_REMITTANCE for same trip,
                or any other constraint violation.
            sqlite3.OperationalError: if the table triggers fire (should not
                happen through this repo).
        """
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """INSERT INTO cash_ledger
               (day_id, session_id, entry_type, amount_pt,
                order_id, trip_id, expense_id, reverses_entry_id,
                actor_id, approved_by, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.day_id,
                entry.session_id,
                entry.entry_type.value,
                entry.amount_pt,
                entry.order_id,
                entry.trip_id,
                entry.expense_id,
                entry.reverses_entry_id,
                entry.actor_id,
                entry.approved_by,
                entry.reason,
                entry.created_at or now,
            ),
        )
        entry.id = self._last_insert_id()
        entry.created_at = entry.created_at or now
        return entry

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_entries_for_session(self, session_id: int) -> List[CashLedgerEntry]:
        """All ledger entries for a session in chronological order."""
        rows = self._db.fetch_all(
            "SELECT * FROM cash_ledger WHERE session_id = ? ORDER BY created_at, id",
            (session_id,),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_entries_for_day(self, day_id: int) -> List[CashLedgerEntry]:
        """All ledger entries for a business day."""
        rows = self._db.fetch_all(
            "SELECT * FROM cash_ledger WHERE day_id = ? ORDER BY created_at, id",
            (day_id,),
        )
        return [self._row_to_entry(r) for r in rows]

    def get_entry_by_order(
        self, order_id: int, entry_type: LedgerEntryType
    ) -> Optional[CashLedgerEntry]:
        """Find the ledger entry for a specific order + entry_type (idempotency check)."""
        row = self._db.fetch_one(
            "SELECT * FROM cash_ledger WHERE order_id = ? AND entry_type = ?",
            (order_id, entry_type.value),
        )
        return self._row_to_entry(row) if row else None

    def get_entry_by_trip(
        self, trip_id: int, entry_type: LedgerEntryType
    ) -> Optional[CashLedgerEntry]:
        """Find the ledger entry for a specific trip + entry_type."""
        row = self._db.fetch_one(
            "SELECT * FROM cash_ledger WHERE trip_id = ? AND entry_type = ?",
            (trip_id, entry_type.value),
        )
        return self._row_to_entry(row) if row else None

    def get_cash_sales_total_pt(self, session_id: int) -> int:
        """Sum of all SALE_CASH entries for a session (gross cash collected)."""
        row = self._db.fetch_one(
            """SELECT COALESCE(SUM(amount_pt), 0) AS total FROM cash_ledger
               WHERE session_id = ? AND entry_type = 'SALE_CASH'""",
            (session_id,),
        )
        return int(row["total"]) if row else 0

    def get_driver_remittance_total_pt(self, session_id: int) -> int:
        """Sum of all DRIVER_REMITTANCE entries for a session."""
        row = self._db.fetch_one(
            """SELECT COALESCE(SUM(amount_pt), 0) AS total FROM cash_ledger
               WHERE session_id = ? AND entry_type = 'DRIVER_REMITTANCE'""",
            (session_id,),
        )
        return int(row["total"]) if row else 0

    def get_expense_total_pt(self, session_id: int) -> int:
        """Sum of all EXPENSE entries (absolute value) for a session."""
        row = self._db.fetch_one(
            """SELECT COALESCE(SUM(ABS(amount_pt)), 0) AS total FROM cash_ledger
               WHERE session_id = ? AND entry_type = 'EXPENSE'""",
            (session_id,),
        )
        return int(row["total"]) if row else 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> CashLedgerEntry:
        return CashLedgerEntry(
            id=row["id"],
            day_id=row["day_id"],
            session_id=row["session_id"],
            entry_type=LedgerEntryType(row["entry_type"]),
            amount_pt=row["amount_pt"],
            order_id=row["order_id"],
            trip_id=row["trip_id"],
            expense_id=row["expense_id"],
            reverses_entry_id=row["reverses_entry_id"],
            actor_id=row["actor_id"],
            approved_by=row["approved_by"],
            reason=row["reason"],
            created_at=row["created_at"],
        )
