"""
Customer models — Customer, CustomerAddress, Zone.

Phone is the primary key for customer lookup (11-digit Egyptian, starts with 01).
Zone-based delivery fees ensure pricing consistency across all orders.
One customer can have multiple addresses (home, work, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Zone:
    """
    A delivery zone with a fixed delivery fee.

    - Managed by the manager via admin UI (stored in DB, not in config).
    - `delivery_fee` is fixed — cashier cannot change it per order.
    - `is_active` allows disabling zones without deleting.
    """
    id: Optional[int] = None
    name: str = ""              # e.g. "مدينة فاقوس", "شارع الانتاج", "الغابة"
    delivery_fee: float = 0.0   # fixed per zone (e.g. 20, 15, 80)
    is_active: bool = True


@dataclass
class CustomerAddress:
    """
    A single address for a customer.

    - `street_name` is just the street (e.g. "شارع المشالي") — no building numbers.
    - `zone_name` and `delivery_fee` are denormalized from Zone at creation time
      to preserve the fee that was current when the address was added.
    """
    id: Optional[int] = None
    customer_id: Optional[int] = None
    street_name: str = ""
    zone_id: Optional[int] = None
    zone_name: str = ""         # denormalized for display
    delivery_fee: float = 0.0   # copied from zone at creation time


@dataclass
class Customer:
    """
    A customer identified by their Egyptian phone number.

    - `phone` is UNIQUE and the primary lookup key (11 digits, starts with 01).
    - One customer can have multiple addresses.
    - `notes` is optional free text (e.g. allergies, preferences).
    """
    id: Optional[int] = None
    name: str = ""
    phone: str = ""             # 11-digit Egyptian (starts with 01)
    notes: Optional[str] = None
    created_at: Optional[str] = None
    addresses: List[CustomerAddress] = field(default_factory=list)
