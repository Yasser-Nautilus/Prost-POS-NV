# core/models package — pure Python dataclasses, no DB/UI imports
from broast_pos.core.models.audit import AuditEventType
from broast_pos.core.models.customer import Customer, CustomerAddress, Zone
from broast_pos.core.models.delivery import (
    DeliveryTrip,
    DriverAttendance,
    DriverStatus,
)
from broast_pos.core.models.driver_settlement import DriverSettlement
from broast_pos.core.models.financial import (
    CashTransaction,
    Shift,
    ShiftSummary,
    ShiftTransfer,
)
from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.core.models.order_status_history import OrderStatusHistory
from broast_pos.core.models.product import Category, Product
from broast_pos.core.models.user import User, UserRole

__all__ = [
    "AuditEventType",
    # Financial
    "CashTransaction",
    # Product
    "Category",
    # Customer
    "Customer",
    "CustomerAddress",
    # Delivery
    "DeliveryTrip",
    "DriverAttendance",
    "DriverSettlement",
    "DriverStatus",
    # Order
    "Order",
    "OrderItem",
    "OrderStatus",
    # New models
    "OrderStatusHistory",
    "OrderType",
    "PaymentMethod",
    "Product",
    "Shift",
    "ShiftSummary",
    "ShiftTransfer",
    # User
    "User",
    "UserRole",
    "Zone",
]
