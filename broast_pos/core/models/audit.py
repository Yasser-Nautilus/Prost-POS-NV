"""
Audit event type constants — single source of truth for all audit event strings.

Using constants prevents typos like "driver_settled" vs "trip_settled" vs
"driverSettlement" spreading across the codebase.
"""

from __future__ import annotations


class AuditEventType:
    """All valid audit event type strings.

    Usage::

        from broast_pos.core.models.audit import AuditEventType

        audit_service.log(event_type=AuditEventType.ORDER_CANCELLED, ...)
    """

    # Order events
    ORDER_CREATED = "order_created"
    ORDER_AMENDED = "order_amended"
    ORDER_CANCELLED = "order_cancelled"

    # Item events (part of order)
    DISCOUNT_APPLIED = "discount_applied"
    ITEM_REMOVED = "item_removed"

    # Delivery events
    DRIVER_ASSIGNED = "driver_assigned"
    TRIP_CREATED = "trip_created"
    TRIP_DISPATCHED = "trip_dispatched"
    TRIP_RETURNED = "trip_returned"
    TRIP_SETTLED = "trip_settled"

    # Settlement events
    DRIVER_SETTLEMENT_COMPLETED = "driver_settlement_completed"

    # Customer events
    CUSTOMER_CREATED = "customer_created"
    CUSTOMER_UPDATED = "customer_updated"

    # Shift events
    SHIFT_OPENED = "shift_opened"
    SHIFT_CLOSED = "shift_closed"
    SHIFT_TRANSFERRED = "shift_transferred"

    # User management events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
