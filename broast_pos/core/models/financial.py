"""
Financial models — Shift, ShiftTransfer, CashTransaction, ShiftSummary.

Shift is the primary accounting period. All orders and expenses belong to a shift.
ShiftSummary is computed (not stored) — it aggregates live data for display.

Expected cash formula:
    expected_cash = total_sales - total_expenses - all_pending
    (pending = money not yet physically in the drawer)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Shift:
    """
    An accounting period opened and closed by a manager.

    - `next_invoice_no` starts at 1 and increments with each order.
    - `is_active` — only one shift can be active at a time.
    - `summary_printed_at` — must print summary before closing shift.
    """
    id: Optional[int] = None
    opened_by: Optional[int] = None     # user_id
    opened_at: Optional[str] = None
    closed_by: Optional[int] = None     # user_id, NULL while open
    closed_at: Optional[str] = None     # NULL while open
    next_invoice_no: int = 1            # resets to 1 each new shift
    is_active: bool = True
    summary_printed_at: Optional[str] = None

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
    id: Optional[int] = None
    shift_id: Optional[int] = None
    from_user_id: Optional[int] = None
    to_user_id: Optional[int] = None
    timestamp: Optional[str] = None
    summary_snapshot: str = "{}"    # JSON: sales, expenses, pending at transfer time


@dataclass
class CashTransaction:
    """
    A cash expense record. Immutable — cannot be edited after creation.

    Only "expense" type — cash going out of the drawer.
    Categories: delivery_fees, supplies, other.
    """
    id: Optional[int] = None
    shift_id: Optional[int] = None
    type: str = "expense"       # always "expense"
    amount: float = 0.0
    description: str = ""
    category: str = "other"     # "delivery_fees" | "supplies" | "other"
    timestamp: Optional[str] = None
    user_id: Optional[int] = None


@dataclass
class ShiftSummary:
    """
    Computed summary of a shift — NOT stored in database.

    Aggregated from live order and expense data for dashboard display.

    expected_cash = total_sales - total_expenses - all pending
    (pending orders are deducted because the cash isn't physically in the drawer)
    """
    total_sales: float = 0.0            # all completed orders
    total_expenses: float = 0.0         # all cash-out entries
    pending_delivery: float = 0.0       # unsettled driver orders
    pending_dinein: float = 0.0         # unpaid dine-in tables
    pending_kitchen: float = 0.0        # orders still being prepared
    order_breakdown: Dict[str, dict] = field(default_factory=dict)
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
        """Cash that should be in the drawer right now."""
        return round(
            self.total_sales - self.total_expenses - self.total_pending,
            2,
        )
