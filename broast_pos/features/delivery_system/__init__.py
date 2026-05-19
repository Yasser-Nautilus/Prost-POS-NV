"""
delivery_system — Driver lifecycle, trip assignment, and financial settlement.

Modules:
    delivery_controller: Main entry point for Delivery View → service coordination.
"""

from broast_pos.features.delivery_system.delivery_controller import DeliveryController

__all__ = ["DeliveryController"]
