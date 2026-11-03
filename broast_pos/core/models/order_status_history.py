"""
Order status history model — records every status transition for an order.

Each record captures: which order, old status, new status, who changed it,
why, and when. Together they form the complete order lifecycle timeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderStatusHistory:
    """A single status transition record for an order.

    Created whenever an order moves from one status to another.
    The first record for any order has old_status = None (NEW order created).
    """
    id: int | None = None
    order_id: int = 0
    old_status: str | None = None    # None for the initial NEW record
    new_status: str = ""
    changed_by_id: int | None = None
    changed_by_name: str | None = None
    reason: str | None = None        # e.g. cancellation reason
    changed_at: str | None = None    # ISO 8601 timestamp (set by DB)
