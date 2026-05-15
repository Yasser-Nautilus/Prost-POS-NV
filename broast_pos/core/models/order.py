"""
Order models — Order, OrderItem, OrderType, OrderStatus, PaymentMethod.

Pure dataclasses with computed financial properties. No DB / UI imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OrderType(Enum):
    """نوع الطلب — determines required fields and UI flow."""
    DINE_IN = "dine_in"       # صالة — requires table_no
    TAKEAWAY = "takeaway"     # تيك اواي — no extras
    DELIVERY = "delivery"     # دليفري — requires phone, address, zone
    PICKUP = "pickup"         # استلام محل — requires phone


class OrderStatus(Enum):
    """
    Order lifecycle — strict forward progression.

    جديد → قيد التحضير → جاهز → خارج للتوصيل → تم التوصيل → مكتمل / ملغي
    """
    NEW = "new"                         # جديد
    PREPARING = "preparing"             # قيد التحضير
    READY = "ready"                     # جاهز
    OUT_FOR_DELIVERY = "out_for_delivery"  # خارج للتوصيل (delivery only)
    DELIVERED = "delivered"             # تم التوصيل (delivery only)
    COMPLETED = "completed"            # مكتمل
    CANCELLED = "cancelled"            # ملغي


class PaymentMethod(Enum):
    """
    Three payment methods only.

    Note: Visa is NOT available for delivery orders — only at the counter.
    """
    CASH = "cash"       # كاش
    VISA = "visa"       # فيزا (counter only — not for delivery)
    ONLINE = "online"   # اونلاين (prepaid — driver collects nothing)

    @property
    def is_prepaid(self) -> bool:
        """Online orders are prepaid — driver doesn't collect cash."""
        return self == PaymentMethod.ONLINE


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------

@dataclass
class OrderItem:
    """
    A single line item in an order.

    No modifiers — product name itself contains the variation
    (e.g. "تشيكن فرايز حار"). Notes are per-item free text for
    special instructions (e.g. "3 pieces cold").
    """
    product_id: int
    product_name: str
    quantity: int               # always int — no fractional quantities
    unit_price: float
    notes: str = ""
    id: Optional[int] = None    # set after DB insert

    @property
    def total_price(self) -> float:
        """quantity × unit_price, rounded to 2 decimals."""
        return round(self.quantity * self.unit_price, 2)


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

@dataclass
class Order:
    """
    Full order with financial breakdown and lifecycle tracking.

    Financial formula:
        subtotal  = Σ(item.total_price)
        total     = subtotal - discount_amount + service_amount + delivery_fee

    Restaurant revenue (for shift reports):
        restaurant_revenue = total - delivery_fee
    """
    # Identity
    id: Optional[int] = None
    invoice_no: Optional[int] = None
    shift_id: Optional[int] = None

    # Type & status
    order_type: OrderType = OrderType.DINE_IN
    status: OrderStatus = OrderStatus.NEW
    table_no: Optional[int] = None

    # Items
    items: List[OrderItem] = field(default_factory=list)

    # Customer (denormalized for receipt/history)
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_address: Optional[str] = None
    customer_zone: Optional[str] = None
    delivery_fee: float = 0.0

    # Driver (delivery only)
    driver_id: Optional[int] = None
    driver_name: Optional[str] = None

    # Financial breakdown (stored in DB)
    subtotal: float = 0.0
    discount_amount: float = 0.0
    discount_type: Optional[str] = None    # "flat" | "percent"
    service_amount: float = 0.0
    total: float = 0.0

    # Payment
    payment_method: Optional[PaymentMethod] = None
    amount_paid: float = 0.0
    change_given: float = 0.0
    is_paid: bool = False
    paid_at: Optional[str] = None

    # Creator
    created_by_id: Optional[int] = None
    created_by_name: str = ""
    cashier_slot: int = 1

    # Cancellation
    cancelled_by_id: Optional[int] = None
    cancelled_by_name: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[str] = None

    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    def compute_subtotal(self) -> float:
        """Sum of all item totals."""
        return round(sum(item.total_price for item in self.items), 2)

    def compute_total(self) -> float:
        """subtotal - discount + service + delivery_fee."""
        return round(
            self.subtotal
            - self.discount_amount
            + self.service_amount
            + self.delivery_fee,
            2,
        )

    @property
    def restaurant_revenue(self) -> float:
        """Total minus delivery_fee — the actual restaurant income.

        Critical for shift reports and driver settlement calculations.
        """
        return round(self.total - self.delivery_fee, 2)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def is_delivery(self) -> bool:
        """True if this is a delivery order."""
        return self.order_type == OrderType.DELIVERY

    def can_be_cancelled(self) -> bool:
        """An order can be cancelled unless it's already completed or cancelled."""
        return self.status not in (OrderStatus.COMPLETED, OrderStatus.CANCELLED)

    def recalculate(self) -> None:
        """Recompute subtotal and total from items. Call after adding/removing items."""
        self.subtotal = self.compute_subtotal()
        self.total = self.compute_total()
