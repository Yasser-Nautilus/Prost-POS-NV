"""
Delivery system controller — orchestrates driver lifecycle and trip management.

Connects the Delivery View to DeliveryService + OrderService + PrintTriggers.
Handles: driver check-in/out, trip creation, dispatch, return, settlement,
and end-of-day driver summary.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from broast_pos.core.models.delivery import DeliveryTrip
from broast_pos.core.models.order import OrderStatus, PaymentMethod
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.order_service import OrderService
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers

logger = logging.getLogger(__name__)


class DeliveryController:
    """Orchestrates driver lifecycle and trip management.

    This is the single entry point for the Delivery View.
    """

    def __init__(
        self,
        delivery_service: DeliveryService,
        order_service: OrderService,
        print_triggers: PrintTriggers,
        cashier_slot: int = 1,
    ) -> None:
        self._delivery_svc = delivery_service
        self._order_svc = order_service
        self._print = print_triggers
        self._cashier_slot = cashier_slot

        # UI callbacks
        self._on_drivers_changed: Optional[Callable] = None
        self._on_trips_changed: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_drivers_changed(self, callback: Callable) -> None:
        self._on_drivers_changed = callback

    def on_trips_changed(self, callback: Callable) -> None:
        self._on_trips_changed = callback

    # ------------------------------------------------------------------
    # 1. Driver Management
    # ------------------------------------------------------------------

    def check_in_driver(self, driver_id: int) -> Tuple[bool, str]:
        """Activate driver for current shift."""
        try:
            self._delivery_svc.check_in_driver(driver_id)
            self._notify_drivers()
            return True, "تم تسجيل حضور السائق"
        except Exception as exc:
            return False, str(exc)

    def check_out_driver(self, driver_id: int) -> Tuple[bool, str]:
        """Deactivate driver at end of shift."""
        try:
            self._delivery_svc.check_out_driver(driver_id)
            self._notify_drivers()
            return True, "تم تسجيل انصراف السائق"
        except Exception as exc:
            return False, str(exc)

    def get_available_drivers(self) -> List[Dict[str, Any]]:
        """Return all active drivers with their check-in status."""
        try:
            all_drivers = self._delivery_svc.get_all_drivers()
            checked_in_users = self._delivery_svc.get_active_drivers()
            checked_in_ids = {d.id for d in checked_in_users}
            return [
                {
                    "id": d.id,
                    "username": d.username,
                    "display_name": d.display_name or d.username,
                    "role": d.role.value,
                    "cashier_slot": d.cashier_slot,
                    "is_active": d.is_active,
                    "is_checked_in": d.id in checked_in_ids,
                    "status": self._get_driver_status(d.id),
                }
                for d in all_drivers
            ]
        except Exception:
            return []

    def get_active_drivers(self) -> List[Dict[str, Any]]:
        """Return list of checked-in drivers for the dispatch list."""
        return self.get_available_drivers()

    def _get_driver_status(self, driver_id: int) -> str:
        """Determine driver display status using the repo's authoritative logic."""
        try:
            status = self._delivery_svc._delivery.get_driver_status(driver_id)
            from broast_pos.core.models.delivery import DriverStatus
            if status == DriverStatus.OUT:
                return "out"
            elif status == DriverStatus.AVAILABLE:
                return "available"
            else:  # CHECKED_OUT
                return "off_duty"
        except Exception:
            return "available"

    # ------------------------------------------------------------------
    # 2. Unassigned Orders
    # ------------------------------------------------------------------

    def get_unassigned_deliveries(self) -> List[Dict[str, Any]]:
        """Return delivery orders not yet assigned to a driver."""
        try:
            orders = self._order_svc.get_unassigned_deliveries()
            return [
                {
                    "id": o.id,
                    "invoice_no": o.invoice_no,
                    "customer_name": o.customer_name or "",
                    "customer_phone": o.customer_phone or "",
                    "customer_address": o.customer_address or "",
                    "customer_zone": o.customer_zone or "",
                    "total": o.total or 0,
                    "delivery_fee": o.delivery_fee or 0,
                    "payment_method": o.payment_method.value if o.payment_method else "cash",
                }
                for o in orders
            ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 3. Create & Dispatch Trip
    # ------------------------------------------------------------------

    def create_trip(
        self,
        driver_id: int,
        order_ids: List[int],
    ) -> Tuple[bool, Any]:
        """Create a delivery trip with selected orders.

        Cross-cashier trips allowed. Mixed payment trips allowed.
        """
        if not order_ids:
            return False, "يجب اختيار طلب واحد على الأقل"

        try:
            trip = self._delivery_svc.create_trip(driver_id, order_ids)
            self._notify_trips()
            self._notify_drivers()
            return True, trip
        except Exception as exc:
            return False, str(exc)

    def dispatch_trip(self, trip_id: int) -> Tuple[bool, str]:
        """Mark trip as dispatched (driver physically left)."""
        try:
            trip = self._delivery_svc.mark_dispatched(trip_id)
            self._notify_trips()
            self._notify_drivers()
            return True, "تم تسجيل خروج الرحلة"
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # 4. Mark Returned
    # ------------------------------------------------------------------

    def mark_returned(self, trip_id: int) -> Tuple[bool, str]:
        """Mark trip as returned (driver back at restaurant)."""
        try:
            trip = self._delivery_svc.mark_returned(trip_id)
            self._notify_trips()
            self._notify_drivers()
            return True, "تم تسجيل عودة السائق"
        except Exception as exc:
            return False, str(exc)

    def return_trip(self, trip_id: int) -> Tuple[bool, str]:
        """Alias for mark_returned to align with bridge naming."""
        return self.mark_returned(trip_id)

    # ------------------------------------------------------------------
    # 5. Settlement
    # ------------------------------------------------------------------

    def get_settlement_details(self, trip_id: int) -> Optional[Dict[str, Any]]:
        """Get trip details for settlement view.

        Returns breakdown of orders, cash collected, delivery fees,
        and amount to hand over.
        """
        try:
            trip = self._delivery_svc.get_trip(trip_id)
            if trip is None:
                return None

            orders = []
            total_cash = 0.0
            total_fees = 0.0

            for oid in trip.order_ids:
                order = self._order_svc.get_order_by_id(oid)
                if order is None:
                    continue
                is_cash = order.payment_method == PaymentMethod.CASH
                collected = order.total if is_cash else 0.0
                if is_cash:
                    total_cash += order.total

                total_fees += order.delivery_fee or 0

                orders.append({
                    "invoice_no": order.invoice_no,
                    "total": order.total,
                    "delivery_fee": order.delivery_fee or 0,
                    "payment_method": order.payment_method.value if order.payment_method else "cash",
                    "collected": collected,
                })

            return {
                "trip_id": trip.id,
                "driver_name": trip.driver_name,
                "orders": orders,
                "cash_collected": total_cash,
                "total_delivery_fees": total_fees,
                "amount_to_hand_over": total_cash,
            }
        except Exception:
            return None

    def settle_trip(self, trip_id: int, print_receipt: bool = False) -> Tuple[bool, str]:
        """Confirm settlement — driver hands over cash.

        Args:
            trip_id: The trip to settle.
            print_receipt: Whether to print a settlement receipt.

        Returns:
            (success, message)
        """
        # Capture details BEFORE settling — data may be stale after
        settlement_details = None
        if print_receipt:
            settlement_details = self.get_settlement_details(trip_id)

        try:
            trip = self._delivery_svc.settle_trip(trip_id)
        except Exception as exc:
            return False, str(exc)

        # Print settlement receipt if requested
        if print_receipt and settlement_details:
            self._print.on_driver_settled(settlement_details, self._cashier_slot)

        self._notify_trips()
        return True, "تم تسوية الرحلة"

    def get_unsettled_trips(self, driver_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all returned but unsettled trips."""
        try:
            if driver_id is not None:
                trips = self._delivery_svc.get_unsettled_trips(driver_id)
            else:
                # Get all active drivers' unsettled trips
                trips = []
                drivers = self._delivery_svc.get_active_drivers()
                for d in drivers:
                    trips.extend(self._delivery_svc.get_unsettled_trips(d.id))

            return [
                {
                    "id": t.id,
                    "driver_name": t.driver_name,
                    "order_count": len(t.order_ids) if t.order_ids else 0,
                    "dispatched_at": str(t.dispatched_at) if t.dispatched_at else "",
                    "returned_at": str(t.returned_at) if t.returned_at else "",
                    "is_settled": t.is_settled,
                }
                for t in trips
            ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 7. End-of-Day Driver Summary
    # ------------------------------------------------------------------

    def get_daily_summary(self) -> List[Dict[str, Any]]:
        """Get end-of-day summary for all drivers.

        Returns:
            List of driver summaries with trips, orders, and fees.
        """
        try:
            return self._delivery_svc.get_all_drivers_daily_summary()
        except Exception:
            return []

    def get_driver_summary(self, driver_id: int) -> Optional[Dict[str, Any]]:
        """Get daily summary for a specific driver."""
        try:
            return self._delivery_svc.get_driver_daily_summary(driver_id)
        except Exception:
            return None

    def print_daily_summary(self) -> bool:
        """Print the end-of-day driver summary."""
        try:
            summary = self.get_daily_summary()
            if summary:
                self._print.on_driver_summary(summary, self._cashier_slot)
                return True
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Active Trips (for Delivery View display)
    # ------------------------------------------------------------------

    def get_active_trips(self) -> List[Dict[str, Any]]:
        """Return all live trips: in-transit + returned-but-unsettled.

        Uses the repo directly because DeliveryService.get_unsettled_trips()
        only returns already-returned trips, not in-transit ones.
        """
        try:
            repo = self._delivery_svc._delivery
            # In-transit: dispatched but driver hasn't returned yet
            in_transit = repo.get_active_trips()
            # Returned but not yet settled (cash handover pending)
            unsettled = repo.get_unsettled_trips()

            all_trips: List[Dict[str, Any]] = []

            def _serialize(t: Any, status: str) -> Dict[str, Any]:
                return {
                    "id": t.id,
                    "driver_id": t.driver_id,
                    "driver_name": getattr(t, "driver_name", ""),
                    "order_ids": t.order_ids or [],
                    "order_count": len(t.order_ids) if t.order_ids else 0,
                    "status": status,
                    "dispatched_at": str(t.dispatched_at) if t.dispatched_at else None,
                    "returned_at": str(t.returned_at) if t.returned_at else None,
                    "settled_at": str(t.settled_at) if getattr(t, "settled_at", None) else None,
                    "is_settled": bool(getattr(t, "is_settled", False)),
                    "cash_collected": float(getattr(t, "cash_collected", 0) or 0),
                    "total_delivery_fees": float(getattr(t, "total_delivery_fees", 0) or 0),
                }

            seen_ids: set = set()
            for t in in_transit:
                all_trips.append(_serialize(t, "dispatched"))
                seen_ids.add(t.id)
            for t in unsettled:
                if t.id not in seen_ids:
                    all_trips.append(_serialize(t, "returned"))
                    seen_ids.add(t.id)

            return all_trips
        except Exception as exc:
            logger.error("get_active_trips error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _notify_drivers(self) -> None:
        if self._on_drivers_changed:
            self._on_drivers_changed()

    def _notify_trips(self) -> None:
        if self._on_trips_changed:
            self._on_trips_changed()
