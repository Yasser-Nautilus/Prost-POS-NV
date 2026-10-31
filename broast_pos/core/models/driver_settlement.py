"""
Driver settlement model — a permanent financial record of end-of-day settlement.

When a manager settles a driver, this record is created and immutable.
It captures exactly what was paid/collected at that point in time.
Even if delivery_trip data changes later, the settlement record is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DriverSettlement:
    """A permanent settlement record created when a driver is settled for the day.

    Financial fields are calculated from actual order data at settlement time —
    never trusted from the frontend. The driver does NOT need to be fully
    checked out for settlement; trips are settled independently.
    """
    id: Optional[int] = None

    # Driver info (denormalized for historical record)
    driver_id: int = 0
    driver_name: str = ""
    settlement_date: str = ""           # YYYY-MM-DD (business date)

    # Trip / order counts
    trip_count: int = 0
    order_count: int = 0

    # Financial summary (calculated server-side from order records)
    total_order_value: float = 0.0     # SUM of all delivered order totals
    cash_collected: float = 0.0        # SUM where payment_method = 'cash'
    online_paid: float = 0.0           # SUM where payment_method = 'online'
    total_delivery_fees: float = 0.0   # SUM of delivery_fee for ALL orders

    # Who settled
    settled_by_id: int = 0
    settled_by_name: str = ""

    # Optional manager notes
    notes: Optional[str] = None

    # Timestamps (set by DB)
    settled_at: Optional[str] = None   # ISO 8601 timestamp
