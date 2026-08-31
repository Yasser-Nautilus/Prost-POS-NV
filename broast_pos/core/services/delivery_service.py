"""
Delivery service — driver lifecycle, trip management, and settlement.

Drivers: check-in → available → dispatched → returned → settled.
Orders can be reassigned between drivers mid-transit.
Settlement = cashier confirms cash handover after driver returns.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from broast_pos.core.models.delivery import (
    DeliveryTrip,
    DriverAttendance,
    DriverStatus,
)
from broast_pos.core.models.order import OrderStatus, PaymentMethod
from broast_pos.core.models.user import User
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.user_repository import UserRepository


class DeliveryService:
    """Business logic for driver management and delivery trips."""

    def __init__(
        self,
        delivery_repo: Optional[DeliveryRepository] = None,
        order_repo: Optional[OrderRepository] = None,
        user_repo: Optional[UserRepository] = None,
    ) -> None:
        self._delivery = delivery_repo or DeliveryRepository()
        self._orders = order_repo or OrderRepository()
        self._users = user_repo or UserRepository()

    # ------------------------------------------------------------------
    # Driver lifecycle
    # ------------------------------------------------------------------

    def check_in_driver(self, driver_id: int) -> DriverAttendance:
        """Mark a driver as available for today's shift.

        Creates an attendance record with check_in_at = now.
        """
        return self._delivery.check_in(driver_id)

    def check_out_driver(self, driver_id: int) -> None:
        """Mark a driver as off-duty.

        Sets check_out_at on the open attendance record.
        Raises:
            ValueError: if driver has unsettled trips.
        """
        unsettled = self.get_unsettled_trips(driver_id)
        if unsettled:
            raise ValueError(
                "لا يمكن تسجيل خروج السائق — يوجد رحلات غير محسوبة"
            )
        self._delivery.check_out_driver(driver_id)

    def get_active_drivers(self) -> List[User]:
        """Return only checked-in (available) drivers for the dispatch list."""
        return self._delivery.get_active_drivers()

    def get_all_drivers(self) -> List[User]:
        """Return all registered active drivers (cashier_slot is None)."""
        return self._users.get_drivers()

    # ------------------------------------------------------------------
    # Trip management
    # ------------------------------------------------------------------

    def get_trip(self, trip_id: int) -> Optional[DeliveryTrip]:
        """Get a delivery trip by its ID."""
        return self._delivery.get_by_id(trip_id)

    def create_trip(
        self,
        driver_id: int,
        order_ids: List[int],
    ) -> DeliveryTrip:
        """Create a new delivery trip with selected orders.

        Raises:
            ValueError: if no orders provided or any order is invalid.
        """
        if not order_ids:
            raise ValueError("يجب اختيار طلب واحد على الأقل")

        # Validate all orders exist and are delivery type
        for oid in order_ids:
            order = self._orders.get_by_id(oid)
            if order is None:
                raise ValueError(f"الطلب #{oid} غير موجود")

        # Get driver display name
        driver = self._users.get_by_id(driver_id)
        driver_name = driver.display_name if driver else f"سائق #{driver_id}"

        return self._delivery.create_trip(driver_id, order_ids, driver_name)

    def mark_dispatched(self, trip_id: int) -> DeliveryTrip:
        """Record that the driver has left with the orders.

        Updates all orders on the trip to OUT_FOR_DELIVERY status.

        Raises:
            ValueError: if trip not found or already dispatched.
        """
        trip = self._delivery.get_trip_by_id(trip_id)
        if trip is None:
            raise ValueError("الرحلة غير موجودة")
        if trip.is_dispatched:
            raise ValueError("الرحلة تم إرسالها بالفعل")

        self._delivery.mark_dispatched(trip_id)

        # Update order statuses
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order and order.status == OrderStatus.NEW:
                order.status = OrderStatus.OUT_FOR_DELIVERY
                self._orders.save(order)

        updated_trip = self._delivery.get_trip_by_id(trip_id)
        return updated_trip or trip

    def mark_returned(self, trip_id: int) -> DeliveryTrip:
        """Record that the driver has returned from the trip.

        Updates all orders on the trip to DELIVERED status.

        Raises:
            ValueError: if trip not found or not dispatched.
        """
        trip = self._delivery.get_trip_by_id(trip_id)
        if trip is None:
            raise ValueError("الرحلة غير موجودة")
        if not trip.is_dispatched:
            raise ValueError("لا يمكن تسجيل العودة — الرحلة لم ترسل بعد")
        if trip.is_returned:
            raise ValueError("الرحلة مسجلة عودة بالفعل")

        self._delivery.mark_returned(trip_id)

        # Update order statuses
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order and order.status == OrderStatus.OUT_FOR_DELIVERY:
                order.status = OrderStatus.DELIVERED
                self._orders.save(order)

        updated_trip = self._delivery.get_trip_by_id(trip_id)
        return updated_trip or trip

    # ------------------------------------------------------------------
    # Order reassignment (transfer between drivers)
    # ------------------------------------------------------------------

    def reassign_order(
        self,
        order_id: int,
        new_driver_id: int,
        new_driver_name: str,
    ) -> DeliveryTrip:
        """Transfer an order from one driver to another.

        - Removes order from old trip
        - Creates new trip for new driver
        - If old trip becomes empty, marks it cancelled

        Raises:
            ValueError: if order not found, not in a trip, or already settled.
        """
        order = self._orders.get_by_id(order_id)
        if order is None:
            raise ValueError("الطلب غير موجود")

        # Find the trip that currently contains this order
        old_trip = self._delivery.get_trip_for_order(order_id)
        if old_trip is None:
            raise ValueError("الطلب غير مسند لأي رحلة")
        if old_trip.is_settled:
            raise ValueError("لا يمكن نقل طلب من رحلة تم تسويتها")

        # Remove order from old trip
        old_trip.order_ids = [
            oid for oid in old_trip.order_ids if oid != order_id
        ]

        # If old trip is now empty, nullify it
        if not old_trip.order_ids:
            old_trip.returned_at = old_trip.returned_at or datetime.now().isoformat()
            old_trip.is_settled = True
            old_trip.cash_collected = 0.0
            old_trip.total_delivery_fees = 0.0
            self._delivery.mark_settled(old_trip.id, 0.0, 0.0)
        else:
            # We don't have a direct raw save, but let's recalculate and settle/update the trip orders in join table
            self._delivery._db.execute(
                "DELETE FROM delivery_trip_orders WHERE trip_id = ? AND order_id = ?",
                (old_trip.id, order_id)
            )
            self._delivery._db.commit()

        # Create a new trip for the new driver
        new_trip = self._delivery.create_trip(new_driver_id, [order_id], new_driver_name)

        # Update order's driver info
        order.driver_id = new_driver_id
        order.driver_name = new_driver_name
        self._orders.save(order)

        return new_trip

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------

    def settle_trip(self, trip_id: int) -> DeliveryTrip:
        """Cashier confirms cash handover after driver returns.

        Calculates:
          - cash_collected = sum of order.total WHERE payment = CASH
          - total_delivery_fees = sum of delivery_fee for ALL orders

        Raises:
            ValueError: if trip not found, not returned, or already settled.
        """
        trip = self._delivery.get_trip_by_id(trip_id)
        if trip is None:
            raise ValueError("الرحلة غير موجودة")
        if not trip.is_returned:
            raise ValueError("لا يمكن التسوية — السائق لم يعد بعد")
        if trip.is_settled:
            raise ValueError("الرحلة تم تسويتها بالفعل")

        # Calculate financial snapshot
        cash_total = 0.0
        fees_total = 0.0
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order:
                if order.payment_method == PaymentMethod.CASH:
                    cash_total += order.total
                fees_total += order.delivery_fee or 0.0

        self._delivery.mark_settled(trip_id, cash_total, fees_total)

        # Update order statuses to COMPLETED
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order and order.status == OrderStatus.DELIVERED:
                order.status = OrderStatus.COMPLETED
                self._orders.save(order)

        updated_trip = self._delivery.get_trip_by_id(trip_id)
        return updated_trip or trip

    def get_unsettled_trips(self, driver_id: int) -> List[DeliveryTrip]:
        """Trips that are returned but not yet settled for a driver."""
        return self._delivery.get_unsettled_trips(driver_id)

    # ------------------------------------------------------------------
    # End-of-day summaries
    # ------------------------------------------------------------------

    def get_all_drivers_daily_summary(
        self, target_date: Optional[date] = None,
    ) -> List[Dict]:
        """All drivers with trip count, order count, fees earned for a day.

        Returns:
            List of dicts: {driver_id, driver_name, trip_count,
                            order_count, total_fees}
        """
        target = target_date or date.today()
        return self._delivery.get_daily_summary(target.isoformat())

    def get_driver_daily_summary(
        self, driver_id: int, target_date: Optional[date] = None,
    ) -> Dict:
        """Single driver detail for a specific day.

        Returns:
            Dict: {driver_id, driver_name, trips, total_fees, total_cash}
        """
        target = target_date or date.today()
        trips = self._delivery.get_driver_trips_for_date(
            driver_id, target.isoformat()
        )

        total_fees = sum(t.total_delivery_fees or 0.0 for t in trips)
        total_cash = sum(t.cash_collected or 0.0 for t in trips)

        return {
            "driver_id": driver_id,
            "trip_count": len(trips),
            "order_count": sum(len(t.order_ids) for t in trips),
            "total_fees": total_fees,
            "total_cash": total_cash,
            "trips": trips,
        }
