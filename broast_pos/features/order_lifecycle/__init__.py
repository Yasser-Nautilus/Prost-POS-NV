"""
order_lifecycle — Full order flow orchestration.

Modules:
    order_controller: Main entry point for UI → service coordination.
    invoice_manager: Race-safe sequential invoice numbering.
    payment_coordinator: Payment method validation and change calculation.
    amendment_tracker: Tracks item changes for amendment kitchen tickets.
"""

from broast_pos.features.order_lifecycle.order_controller import OrderController
from broast_pos.features.order_lifecycle.invoice_manager import InvoiceManager
from broast_pos.features.order_lifecycle.payment_coordinator import (
    PaymentCoordinator,
    PaymentResult,
)
from broast_pos.features.order_lifecycle.amendment_tracker import AmendmentTracker

__all__ = [
    "OrderController",
    "InvoiceManager",
    "PaymentCoordinator",
    "PaymentResult",
    "AmendmentTracker",
]
