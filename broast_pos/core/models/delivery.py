"""
Delivery models — DeliveryTrip, DriverAttendance, DriverStatus.

Trip lifecycle: created → dispatched → returned → settled (each step independent).
No settlement blocking — driver can go on new trips with unsettled previous trips.

Settlement depends on payment method:
  - Cash orders: driver collected the money.
  - Online orders: driver collected nothing.
  - Driver earns fees from ALL orders, paid at end of day as expense.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DriverStatus(Enum):
    """
    Driver availability status.

    CHECKED_OUT — not working (default / off-duty)
    AVAILABLE   — checked in, ready for delivery
    OUT         — currently on a delivery trip
    """
    CHECKED_OUT = "checked_out"
    AVAILABLE = "available"
    OUT = "out"


@dataclass
class DeliveryTrip:
    """
    A single delivery trip carrying one or more orders.

    Financial fields are calculated and stored as snapshots at settlement time:
    - `cash_collected`: sum of order.total WHERE payment_method = 'cash'
    - `total_delivery_fees`: sum of delivery_fee for ALL orders on this trip
    """
    id: Optional[int] = None
    driver_id: Optional[int] = None
    driver_name: str = ""

    # Trip lifecycle timestamps
    created_at: Optional[str] = None
    dispatched_at: Optional[str] = None
    returned_at: Optional[str] = None
    settled_at: Optional[str] = None

    # Orders on this trip
    order_ids: List[int] = field(default_factory=list)

    # Financial snapshots (set at settlement time)
    cash_collected: Optional[float] = None
    total_delivery_fees: Optional[float] = None

    # Settlement flag
    is_settled: bool = False

    @property
    def is_dispatched(self) -> bool:
        """Trip has been sent out."""
        return self.dispatched_at is not None

    @property
    def is_returned(self) -> bool:
        """Driver has returned from trip."""
        return self.returned_at is not None


@dataclass
class DriverAttendance:
    """
    Check-in/check-out record for a driver.

    - `check_out_at` is NULL while driver is still checked in.
    """
    id: Optional[int] = None
    driver_id: Optional[int] = None
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None  # NULL = still checked in
