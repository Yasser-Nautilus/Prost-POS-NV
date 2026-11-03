"""
Financial models — Shift, ShiftTransfer, CashTransaction, ShiftSummary.

Shift is the primary accounting period. All orders and expenses belong to a shift.
ShiftSummary is computed (not stored) — it aggregates live data for display.

Expected cash formula (corrected in batch 1.2 — FIN-001):
    expected_cash = cash_sales − total_expenses − all_pending
    (pending = money not yet physically in the drawer)

    total_sales is kept separately as a “total revenue” figure for
    reporting; it must NOT be used for drawer reconciliation because it
    includes Visa/online orders that never entered the cash drawer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Shift:
    """
    An accounting period opened and closed by a manager.

    - `next_invoice_no` starts at 1 and increments with each order.
    - `is_active` — only one shift can be active at a time.
    - `summary_printed_at` — must print summary before closing shift.
    """
    id: int | None = None
    opened_by: int | None = None     # user_id
    opened_at: str | None = None
    closed_by: int | None = None     # user_id, NULL while open
    closed_at: str | None = None     # NULL while open
    next_invoice_no: int = 1            # resets to 1 each new shift
    is_active: bool = True
    summary_printed_at: str | None = None

    @property
    def is_open(self) -> bool:
        """Shift is open if not closed."""
        return self.is_active and self.closed_at is None

    def can_close(self) -> bool:
        """Shift can only close after summary has been printed."""
        return self.summary_printed_at is not None


@dataclass
class ShiftTransfer:
    """
    Record of a shift handover between two users.

    `summary_snapshot` is a JSON string capturing the financial state
    at the moment of transfer (sales, expenses, pending amounts).
    """
    id: int | None = None
    shift_id: int | None = None
    from_user_id: int | None = None
    to_user_id: int | None = None
    timestamp: str | None = None
    summary_snapshot: str = "{}"    # JSON: sales, expenses, pending at transfer time


@dataclass
class CashTransaction:
    """
    A cash expense record. Immutable — cannot be edited after creation.

    Only “expense” type — cash going out of the drawer.
    Categories: delivery_fees, supplies, other.
    """
    id: int | None = None
    shift_id: int | None = None
    type: str = "expense"       # always "expense"
    amount: float = 0.0
    description: str = ""
    category: str = "other"     # "delivery_fees" | "supplies" | "other"
    timestamp: str | None = None
    user_id: int | None = None


@dataclass
class ShiftSummary:
    """
    Computed summary of a shift — NOT stored in database.

    Aggregated from live order and expense data for dashboard display.

    Fields:
        total_sales   — ALL paid orders (is_paid=1), all payment methods.
                        Used for revenue reporting only.
        cash_sales    — CASH orders that are is_paid=1 (money is physically
                        in the drawer).  B-01 fix: DELIVERED orders (driver
                        still holds cash) are NOT counted here.
        expected_cash — Cash that should be in the drawer right now:
                        cash_sales − total_expenses − pending_cash_not_collected

    Do NOT use total_sales for expected_cash — Visa/online orders never
    enter the cash drawer and must not inflate the reconciliation figure.
    DELIVERED (unsettled) cash orders are pending, not yet in the drawer.
    """
    total_sales: float = 0.0            # ALL completed orders (revenue reporting)
    cash_sales: float = 0.0             # cash-only completed orders (reconciliation)
    total_expenses: float = 0.0         # all cash-out entries
    pending_delivery: float = 0.0       # unsettled driver orders
    pending_dinein: float = 0.0         # unpaid dine-in tables
    pending_kitchen: float = 0.0        # orders still being prepared
    order_breakdown: dict[str, dict] = field(default_factory=dict)
    # e.g. {"dine_in": {"count": 15, "revenue": 2500.0}, ...}

    @property
    def total_pending(self) -> float:
        """Sum of all pending amounts."""
        return round(
            self.pending_delivery + self.pending_dinein + self.pending_kitchen,
            2,
        )

    @property
    def expected_cash(self) -> float:
        """Cash that should be in the drawer right now.

        Formula (B-01 corrected):
            cash_sales (is_paid=1, CASH only)
          − total_expenses
          − pending_delivery (CASH unsettled trips only — ONLINE excluded)
          − pending_dinein   (unpaid cash dine-in)
          − pending_kitchen  (new/preparing/ready cash orders)
        """
        return round(
            self.cash_sales - self.total_expenses - self.total_pending,
            2,
        )
