"""
Financial repository — shift lifecycle, expense tracking, and reconciliation.

Shift is the primary accounting period. All orders and expenses belong to a shift.
Pending calculations are critical for expected cash — close prerequisites prevent data loss.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional

from broast_pos.core.models.financial import (
    CashTransaction,
    Shift,
    ShiftSummary,
    ShiftTransfer,
)
from broast_pos.data.repositories.base_repository import BaseRepository


class FinancialRepository(BaseRepository[Shift]):
    """CRUD and query operations for shifts, transfers, and expenses."""

    # ------------------------------------------------------------------
    # Core contract (for Shift)
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[Shift]:
        row = self._db.fetch_one("SELECT * FROM shifts WHERE id = ?", (entity_id,))
        return self._row_to_shift(row) if row else None

    def save(self, entity: Shift) -> Shift:
        """Not used directly — use open_shift / close_shift instead."""
        return entity

    def delete(self, entity_id: int) -> None:
        """Shifts are never deleted — they are historical records."""
        pass  # No-op

    # ------------------------------------------------------------------
    # Shift lifecycle
    # ------------------------------------------------------------------

    def open_shift(self, user_id: int) -> Shift:
        """Create shift record, reset invoice counter to 1."""
        self._db.execute(
            "INSERT INTO shifts (opened_by, next_invoice_no, is_active) VALUES (?, 1, 1)",
            (user_id,),
        )
        shift_id = self._last_insert_id()
        self._db.commit()
        return self.get_by_id(shift_id)

    def close_shift(self, shift_id: int, closed_by: int) -> None:
        """Set closed_at, is_active = false."""
        self._db.execute(
            """UPDATE shifts SET
                   closed_by = ?, closed_at = datetime('now'), is_active = 0
               WHERE id = ?""",
            (closed_by, shift_id),
        )
        self._db.commit()

    def get_active_shift(self) -> Optional[Shift]:
        """Currently open shift (or None)."""
        row = self._db.fetch_one(
            "SELECT * FROM shifts WHERE is_active = 1 LIMIT 1"
        )
        return self._row_to_shift(row) if row else None

    def get_shift_history(self) -> List[Shift]:
        """Past closed shifts, most recent first."""
        rows = self._db.fetch_all(
            "SELECT * FROM shifts WHERE is_active = 0 ORDER BY closed_at DESC"
        )
        return [self._row_to_shift(r) for r in rows]

    # ------------------------------------------------------------------
    # Shift transfer
    # ------------------------------------------------------------------

    def save_transfer(self, shift_id: int, from_user: int,
                      to_user: int, snapshot: dict) -> ShiftTransfer:
        """Record transfer checkpoint with financial snapshot."""
        self._db.execute(
            """INSERT INTO shift_transfers
                   (shift_id, from_user_id, to_user_id, summary_snapshot)
               VALUES (?, ?, ?, ?)""",
            (shift_id, from_user, to_user, json.dumps(snapshot, ensure_ascii=False)),
        )
        transfer_id = self._last_insert_id()
        self._db.commit()
        return ShiftTransfer(
            id=transfer_id, shift_id=shift_id,
            from_user_id=from_user, to_user_id=to_user,
            summary_snapshot=json.dumps(snapshot, ensure_ascii=False),
        )

    def get_transfers_for_shift(self, shift_id: int) -> List[ShiftTransfer]:
        """All transfers in a shift."""
        rows = self._db.fetch_all(
            "SELECT * FROM shift_transfers WHERE shift_id = ? ORDER BY timestamp",
            (shift_id,),
        )
        return [self._row_to_transfer(r) for r in rows]

    # ------------------------------------------------------------------
    # Expenses (immutable — no update/delete)
    # ------------------------------------------------------------------

    def add_expense(self, transaction: CashTransaction) -> CashTransaction:
        """Insert cash-out entry. Immutable — cannot be edited after creation."""
        self._db.execute(
            """INSERT INTO cash_transactions
                   (shift_id, type, amount, description, category, user_id)
               VALUES (?, 'expense', ?, ?, ?, ?)""",
            (
                transaction.shift_id, transaction.amount,
                transaction.description, transaction.category,
                transaction.user_id,
            ),
        )
        transaction.id = self._last_insert_id()
        self._db.commit()
        return transaction

    def get_shift_expenses(self, shift_id: int) -> List[CashTransaction]:
        """All expenses for a shift."""
        rows = self._db.fetch_all(
            "SELECT * FROM cash_transactions WHERE shift_id = ? ORDER BY timestamp",
            (shift_id,),
        )
        return [self._row_to_transaction(r) for r in rows]

    def get_expenses_for_date(self, date_str: str) -> List[CashTransaction]:
        """All expenses for a date — for export to Excel/Sheets."""
        rows = self._db.fetch_all(
            "SELECT * FROM cash_transactions WHERE DATE(timestamp) = ? ORDER BY timestamp",
            (date_str,),
        )
        return [self._row_to_transaction(r) for r in rows]

    # ------------------------------------------------------------------
    # Reporting queries
    # ------------------------------------------------------------------

    def get_shift_order_summary(self, shift_id: int) -> Dict[str, dict]:
        """Aggregate orders by type: {type: {count, revenue}}."""
        rows = self._db.fetch_all(
            """SELECT order_type, COUNT(*) AS count,
                      COALESCE(SUM(total - delivery_fee), 0) AS revenue
               FROM orders
               WHERE shift_id = ? AND status != 'cancelled'
               GROUP BY order_type""",
            (shift_id,),
        )
        return {
            r["order_type"]: {"count": r["count"], "revenue": r["revenue"]}
            for r in rows
        }

    def get_pending_delivery_total(self, shift_id: int) -> float:
        """Unsettled driver orders total — money not yet in drawer."""
        row = self._db.fetch_one(
            """SELECT COALESCE(SUM(o.total), 0) AS pending
               FROM orders o
               JOIN delivery_trip_orders dto ON dto.order_id = o.id
               JOIN delivery_trips dt ON dt.id = dto.trip_id
               WHERE o.shift_id = ? AND dt.is_settled = 0
                 AND o.status NOT IN ('cancelled')""",
            (shift_id,),
        )
        return row["pending"] if row else 0.0

    def get_pending_dinein_total(self, shift_id: int) -> float:
        """Unpaid dine-in tables total."""
        row = self._db.fetch_one(
            """SELECT COALESCE(SUM(total), 0) AS pending
               FROM orders
               WHERE shift_id = ? AND order_type = 'dine_in'
                 AND is_paid = 0 AND status NOT IN ('cancelled')""",
            (shift_id,),
        )
        return row["pending"] if row else 0.0

    def get_pending_kitchen_total(self, shift_id: int) -> float:
        """Orders still in preparation total."""
        row = self._db.fetch_one(
            """SELECT COALESCE(SUM(total), 0) AS pending
               FROM orders
               WHERE shift_id = ? AND status IN ('new', 'preparing')""",
            (shift_id,),
        )
        return row["pending"] if row else 0.0

    def has_unsettled_trips(self) -> bool:
        """Check if there are any unsettled delivery trips — prerequisite for close."""
        row = self._db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM delivery_trips WHERE is_settled = 0 AND returned_at IS NOT NULL"
        )
        return (row["cnt"] if row else 0) > 0

    def has_printed_daily_summary(self, shift_id: int) -> bool:
        """Check if daily summary has been printed."""
        row = self._db.fetch_one(
            "SELECT summary_printed_at FROM shifts WHERE id = ?", (shift_id,)
        )
        return row is not None and row["summary_printed_at"] is not None

    def mark_summary_printed(self, shift_id: int) -> None:
        """Set summary_printed_at = NOW() — called when daily summary is first printed."""
        self._db.execute(
            "UPDATE shifts SET summary_printed_at = datetime('now') WHERE id = ?",
            (shift_id,),
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Invoice (atomic, race-safe for 2 cashiers)
    # ------------------------------------------------------------------

    def get_next_invoice_no(self, shift_id: int) -> int:
        """Atomic increment: UPDATE … SET next_invoice_no = next_invoice_no + 1 RETURNING …

        Race-safe because SQLite serialises writes.
        """
        # SQLite RETURNING requires 3.35+; fallback to two-step
        self._db.execute(
            "UPDATE shifts SET next_invoice_no = next_invoice_no + 1 WHERE id = ?",
            (shift_id,),
        )
        row = self._db.fetch_one(
            "SELECT next_invoice_no FROM shifts WHERE id = ?", (shift_id,)
        )
        self._db.commit()
        # We incremented, so the invoice we should use is (current - 1)
        return (row["next_invoice_no"] - 1) if row else 1

    # ------------------------------------------------------------------
    # Computed summary (not stored in DB)
    # ------------------------------------------------------------------

    def build_shift_summary(self, shift_id: int) -> ShiftSummary:
        """Build a live ShiftSummary from aggregated data."""
        # Total sales (all completed non-cancelled orders)
        sales_row = self._db.fetch_one(
            """SELECT COALESCE(SUM(total), 0) AS total_sales
               FROM orders
               WHERE shift_id = ? AND status != 'cancelled'""",
            (shift_id,),
        )
        total_sales = sales_row["total_sales"] if sales_row else 0.0

        # Total expenses
        exp_row = self._db.fetch_one(
            """SELECT COALESCE(SUM(amount), 0) AS total_expenses
               FROM cash_transactions WHERE shift_id = ?""",
            (shift_id,),
        )
        total_expenses = exp_row["total_expenses"] if exp_row else 0.0

        return ShiftSummary(
            total_sales=total_sales,
            total_expenses=total_expenses,
            pending_delivery=self.get_pending_delivery_total(shift_id),
            pending_dinein=self.get_pending_dinein_total(shift_id),
            pending_kitchen=self.get_pending_kitchen_total(shift_id),
            order_breakdown=self.get_shift_order_summary(shift_id),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_shift(self, row: sqlite3.Row) -> Shift:
        return Shift(
            id=row["id"],
            opened_by=row["opened_by"],
            opened_at=row["opened_at"],
            closed_by=row["closed_by"],
            closed_at=row["closed_at"],
            next_invoice_no=row["next_invoice_no"],
            is_active=bool(row["is_active"]),
            summary_printed_at=row["summary_printed_at"],
        )

    def _row_to_transfer(self, row: sqlite3.Row) -> ShiftTransfer:
        return ShiftTransfer(
            id=row["id"],
            shift_id=row["shift_id"],
            from_user_id=row["from_user_id"],
            to_user_id=row["to_user_id"],
            timestamp=row["timestamp"],
            summary_snapshot=row["summary_snapshot"],
        )

    def _row_to_transaction(self, row: sqlite3.Row) -> CashTransaction:
        return CashTransaction(
            id=row["id"],
            shift_id=row["shift_id"],
            type=row["type"],
            amount=row["amount"],
            description=row["description"],
            category=row["category"],
            timestamp=row["timestamp"],
            user_id=row["user_id"],
        )
