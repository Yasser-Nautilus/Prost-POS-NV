"""
Delivery service — driver lifecycle, trip management, and settlement.

Drivers: check-in → available → dispatched → returned → settled.
Orders can be reassigned between drivers mid-transit.
Settlement = cashier confirms cash handover after driver returns.

Status changes now route through OrderService.change_order_status() so that
every transition is recorded in order_status_history.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from broast_pos.core.models.audit import AuditEventType
from broast_pos.core.models.delivery import (
    DeliveryTrip,
    DriverAttendance,
    DriverStatus,
)
from broast_pos.core.models.order import OrderStatus, OrderType, PaymentMethod
from broast_pos.core.models.user import User
from broast_pos.data.repositories.audit_repository import AuditRepository
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
        audit_repo: Optional[AuditRepository] = None,
        order_service=None,    # Optional[OrderService] — avoids circular import
        settlement_svc=None,   # Optional[DriverSettlementService] — B-07
    ) -> None:
        self._delivery = delivery_repo or DeliveryRepository()
        self._orders = order_repo or OrderRepository()
        self._users = user_repo or UserRepository()
        self._audit = audit_repo or AuditRepository()
        self._order_svc = order_service    # Used for status transitions + history
        self._settlement_svc = settlement_svc  # B-07: creates driver_settlements record

    # ------------------------------------------------------------------
    # Internal helper: change order status (with history recording)
    # ------------------------------------------------------------------

    def _change_order_status(
        self,
        order_id: int,
        new_status: OrderStatus,
        changed_by_name: str = "نظام",
        reason: Optional[str] = None,
    ) -> None:
        """Route status changes through OrderService (the authoritative path).

        B-06: No silent fallback. If OrderService is not injected or raises,
        the error propagates so the caller knows the transition failed.
        """
        if self._order_svc is None:
            raise RuntimeError(
                "OrderService not injected into DeliveryService — "
                "cannot change order status without it"
            )
        self._order_svc.change_order_status(
            order_id=order_id,
            new_status=new_status,
            changed_by_id=None,
            changed_by_name=changed_by_name,
            reason=reason,
        )

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

    def get_driver_status(self, driver_id: int) -> DriverStatus:
        """Return the authoritative driver status from the repository.

        Public wrapper so controllers/bridge do not need to reach into
        private ``_delivery`` attribute directly.
        """
        return self._delivery.get_driver_status(driver_id)

    def create_trip(
        self,
        driver_id: int,
        order_ids: List[int],
    ) -> DeliveryTrip:
        """Create a new delivery trip with selected orders.

        Backend is the authoritative enforcer of these rules — the
        frontend filter in DeliveryView.tsx is UX sugar only.

        Raises:
            ValueError: if no orders provided, driver is unavailable,
                        or any order is already on an unsettled trip.
        """
        if not order_ids:
            raise ValueError("يجب اختيار طلب واحد على الأقل")

        # ── Guard 1: driver must be available ────────────────────────────
        status = self._delivery.get_driver_status(driver_id)
        if status == DriverStatus.OUT:
            raise ValueError(
                "السائق في رحلة توصيل حالياً — لا يمكن تعيينه لرحلة أخرى"
            )
        if status == DriverStatus.CHECKED_OUT:
            raise ValueError(
                "السائق غير مسجل حضور — يجب تسجيل الحضور أولاً"
            )

        if len(set(order_ids)) != len(order_ids):
            raise ValueError("لا يمكن تكرار الطلب داخل الرحلة")

        # A created-but-undispatched trip still reserves its driver.
        if any(t.driver_id == driver_id for t in self._delivery.get_created_trips()):
            raise ValueError("السائق لديه رحلة قيد التجهيز بالفعل")

        driver = self._users.get_by_id(driver_id)
        if driver is None or not driver.is_active:
            raise ValueError("السائق غير موجود أو غير مفعل")

        # ── Guard 2: validate all orders exist and are unassigned ─────────
        for oid in order_ids:
            order = self._orders.get_by_id(oid)
            if order is None:
                raise ValueError(f"الطلب #{oid} غير موجود")
            if order.order_type != OrderType.DELIVERY:
                raise ValueError(f"الطلب #{oid} ليس طلب توصيل")
            if order.status in (OrderStatus.CANCELLED, OrderStatus.COMPLETED):
                raise ValueError(f"الطلب #{oid} غير صالح للتوصيل")
            existing_trip = self._delivery.get_trip_for_order(oid)
            if existing_trip is not None:
                raise ValueError(
                    f"الطلب #{oid} مسند بالفعل لرحلة أخرى غير مسواة"
                )

        # Get driver display name
        driver_name = driver.display_name if driver else f"سائق #{driver_id}"

        trip = self._delivery.create_trip(driver_id, order_ids, driver_name)

        # Audit event
        try:
            self._audit.log(
                event_type=AuditEventType.TRIP_CREATED,
                user_id=driver_id,
                user_name=driver_name,
                details={
                    "trip_id": trip.id,
                    "order_ids": order_ids,
                    "order_count": len(order_ids),
                },
                entity_type="trip",
                entity_id=trip.id,
            )
        except Exception:
            pass

        return trip

    def mark_dispatched(self, trip_id: int) -> DeliveryTrip:
        """Record that the driver has left with the orders.

        Updates all orders on the trip to OUT_FOR_DELIVERY status.
        B-06: Accepts orders in NEW, PREPARING, or READY state
              (not just NEW) so KDS workflows don’t block dispatch.

        Raises:
            ValueError: if trip not found, already dispatched, or any
                        status transition is invalid.
        """
        trip = self._delivery.get_trip_by_id(trip_id)
        if trip is None:
            raise ValueError("الرحلة غير موجودة")
        if trip.is_dispatched:
            raise ValueError("الرحلة تم إرسالها بالفعل")

        self._delivery.mark_dispatched(trip_id)

        # B-06: dispatch from NEW, PREPARING, or READY — errors propagate
        _dispatchable = {OrderStatus.NEW, OrderStatus.PREPARING, OrderStatus.READY}
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order and order.status in _dispatchable:
                self._change_order_status(
                    order_id=oid,
                    new_status=OrderStatus.OUT_FOR_DELIVERY,
                    changed_by_name=trip.driver_name or "سائق",
                )

        # Audit event
        try:
            self._audit.log(
                event_type=AuditEventType.TRIP_DISPATCHED,
                user_id=trip.driver_id or 0,
                user_name=trip.driver_name or "",
                details={"trip_id": trip_id, "order_count": len(trip.order_ids)},
                entity_type="trip",
                entity_id=trip_id,
            )
        except Exception:
            pass

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

        # Update order statuses through the centralized change_order_status
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order and order.status == OrderStatus.OUT_FOR_DELIVERY:
                self._change_order_status(
                    order_id=oid,
                    new_status=OrderStatus.DELIVERED,
                    changed_by_name=trip.driver_name or "سائق",
                )

        # Audit event
        try:
            self._audit.log(
                event_type=AuditEventType.TRIP_RETURNED,
                user_id=trip.driver_id or 0,
                user_name=trip.driver_name or "",
                details={"trip_id": trip_id},
                entity_type="trip",
                entity_id=trip_id,
            )
        except Exception:
            pass

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

        B-07: If a DriverSettlementService is injected, delegates to
        settle_driver() which atomically:
          - Creates a driver_settlements record.
          - Marks the trip as settled.
          - Completes orders (DELIVERED → COMPLETED).

        Falls back to the legacy settle_trip path when settlement_svc
        is not injected (backward-compatible).

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

        # B-07: delegate to the unified settlement path if available.
        # This guarantees a driver_settlements record is always created.
        if self._settlement_svc is not None and trip.driver_id:
            # settle_driver() handles: mark_settled + complete orders + audit
            self._settlement_svc.settle_driver(
                driver_id=trip.driver_id,
                settled_by_id=0,           # system-initiated (cashier unknown here)
                settled_by_name="نظام تسوية",
            )
            updated_trip = self._delivery.get_trip_by_id(trip_id)
            return updated_trip or trip

        # ── Legacy path (no settlement_svc injected) ────────────────────────
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

        # Complete orders via centralized path
        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if order and order.status == OrderStatus.DELIVERED:
                self._change_order_status(
                    order_id=oid,
                    new_status=OrderStatus.COMPLETED,
                    changed_by_name="تسوية",
                )

        # Audit event
        try:
            self._audit.log(
                event_type=AuditEventType.TRIP_SETTLED,
                user_id=trip.driver_id or 0,
                user_name=trip.driver_name or "",
                details={
                    "trip_id": trip_id,
                    "cash_collected": cash_total,
                    "delivery_fees": fees_total,
                },
                entity_type="trip",
                entity_id=trip_id,
                after={"cash_collected": cash_total, "fees": fees_total},
            )
        except Exception:
            pass

        updated_trip = self._delivery.get_trip_by_id(trip_id)
        return updated_trip or trip

    def get_unsettled_trips(self, driver_id: Optional[int] = None) -> List[DeliveryTrip]:
        """Returned trips awaiting settlement, optionally for one driver."""
        return self._delivery.get_unsettled_trips(driver_id)

    def get_active_trips(self) -> List[DeliveryTrip]:
        """All trips currently in transit (dispatched but not returned)."""
        return self._delivery.get_active_trips()

    def is_driver_out(self, driver_id: int) -> bool:
        """Return True if driver has an in-transit trip."""
        active = self._delivery.get_active_trips()
        return any(t.driver_id == driver_id for t in active)

    def get_trip_details(self, trip_id: int) -> Optional[Dict]:
        """Full trip details for settlement dialog.

        Returns dict with:
            trip_id, driver_name, dispatched_at, returned_at,
            orders: list of {invoice_no, customer_name, customer_address,
                             customer_zone, total, delivery_fee},
            total_order_value, total_delivery_fees
        """
        trip = self._delivery.get_trip_by_id(trip_id)
        if not trip:
            return None

        orders_data = []
        total_order = 0.0
        total_fees = 0.0
        cash_collected = 0.0

        for oid in trip.order_ids:
            order = self._orders.get_by_id(oid)
            if not order:
                continue
            fee = order.delivery_fee or 0.0
            total = order.total or 0.0
            total_order += total
            total_fees += fee
            is_cash = order.payment_method == PaymentMethod.CASH
            collected = total if is_cash else 0.0
            cash_collected += collected
            orders_data.append({
                "order_id": oid,
                "invoice_no": order.invoice_no,
                "customer_name": order.customer_name or "—",
                "customer_phone": order.customer_phone or "",
                "customer_address": order.customer_address or "—",
                "customer_zone": order.customer_zone or "",
                "total": total,
                "delivery_fee": fee,
                "payment_method": order.payment_method.value if order.payment_method else "cash",
                "collected": collected,
            })

        return {
            "trip_id": trip.id,
            "driver_id": trip.driver_id,
            "driver_name": trip.driver_name or "—",
            "dispatched_at": str(trip.dispatched_at) if trip.dispatched_at else None,
            "returned_at": str(trip.returned_at) if trip.returned_at else None,
            "is_settled": trip.is_settled,
            "orders": orders_data,
            "total_order_value": total_order,
            "total_delivery_fees": total_fees,
            "cash_collected": cash_collected,
            "amount_to_hand_over": cash_collected,
        }

    def get_driver_attendance_today(self) -> List[Dict]:
        """All attendance records for today — for the attendance panel."""
        try:
            records = self._delivery.get_attendance_for_date(date.today().isoformat())
        except Exception:
            records = []
        result = []
        for rec in records:
            result.append({
                "driver_id": rec.driver_id,
                "check_in_at": str(rec.check_in_at) if rec.check_in_at else None,
                "check_out_at": str(rec.check_out_at) if rec.check_out_at else None,
            })
        return result

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
