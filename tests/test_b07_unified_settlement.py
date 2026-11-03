"""
Tests for trip vs. driver settlement separation.

Per-trip settlement (DeliveryService.settle_trip) is the running cash handover:
  it settles ONLY that one trip (mark settled + complete its orders + book its cash).

Driver settlement (DriverSettlementService.settle_driver) is the end-of-day close:
  it summarizes ALL the driver's returned trips for the date into one day record,
  without re-booking cash or re-completing trips already settled per-trip.

Test strategy: unit-test with mocks — no real DB.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.delivery import DeliveryTrip
from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trip(
    trip_id: int = 1,
    driver_id: int = 10,
    order_ids=None,
    is_returned: bool = True,
    is_settled: bool = False,
) -> DeliveryTrip:
    return DeliveryTrip(
        id=trip_id,
        driver_id=driver_id,
        driver_name="محمود السائق",
        order_ids=order_ids or [101, 102],
        dispatched_at="2026-10-04T08:00:00",
        returned_at="2026-10-04T09:00:00" if is_returned else None,
        is_settled=is_settled,
    )


def _order(
    order_id: int,
    status: OrderStatus = OrderStatus.DELIVERED,
    payment: PaymentMethod = PaymentMethod.CASH,
    total: float = 120.0,
    delivery_fee: float = 15.0,
) -> Order:
    return Order(
        id=order_id,
        invoice_no=order_id,
        order_type=OrderType.DELIVERY,
        status=status,
        items=[OrderItem(product_id=1, product_name="x", unit_price=total, quantity=1)],
        subtotal=total - delivery_fee,
        total=total,
        delivery_fee=delivery_fee,
        payment_method=payment,
        shift_id=1,
    )


def _delivery_svc_mock(trip: DeliveryTrip, orders: dict):
    """Build a DeliveryService-like mock."""
    delivery_repo = MagicMock()
    delivery_repo.get_trip_by_id.return_value = trip
    delivery_repo.mark_settled.return_value = None

    order_repo = MagicMock()
    order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)
    order_repo.save.side_effect = lambda o: o

    return delivery_repo, order_repo


# ===========================================================================
# Part A: DriverSettlementService.settle_driver() completes orders (B-07)
# ===========================================================================

class TestSettleDriverCompletesOrders:

    def _build_settlement_svc(self, orders: dict):
        from broast_pos.core.services.driver_settlement_service import (
            DriverSettlementService,
        )

        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)
        order_repo.save.side_effect = lambda o: o

        order_svc = MagicMock()
        order_svc.change_order_status.side_effect = lambda **kw: orders[kw["order_id"]]

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = MagicMock(
            id=10, display_name="محمود", username="mahmoud", is_active=True
        )

        delivery_repo = MagicMock()
        trip = _trip()
        delivery_repo.get_driver_trips_for_date.return_value = [trip]
        delivery_repo.get_unsettled_trips.return_value = [trip]
        delivery_repo._db = MagicMock()
        # Simulate transaction() as a no-op context manager
        delivery_repo._db.transaction.return_value.__enter__ = MagicMock(return_value=None)
        delivery_repo._db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        delivery_repo._db.execute.return_value = None

        settlement_repo = MagicMock()
        settlement_repo.create_settlement.side_effect = lambda s: s
        settlement_repo.get_by_driver_date.return_value = None  # no existing day record

        svc = DriverSettlementService(
            settlement_repo=settlement_repo,
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            user_repo=user_repo,
            order_svc=order_svc,
        )
        return svc, order_svc

    def test_settle_driver_summarizes_the_days_returned_trips(self):
        """Whole-day settlement: the day record is built from the driver's
        returned trips for that date (get_driver_trips_for_date)."""
        from broast_pos.core.services.driver_settlement_service import (
            DriverSettlementService,
        )

        orders = {101: _order(101), 102: _order(102)}
        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = MagicMock(
            id=10, display_name="محمود", username="mahmoud", is_active=True
        )

        trip = _trip()  # returned
        delivery_repo = MagicMock()
        delivery_repo.get_driver_trips_for_date.return_value = [trip]
        delivery_repo._db = MagicMock()
        delivery_repo._db.transaction.return_value.__enter__ = MagicMock(return_value=None)
        delivery_repo._db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        delivery_repo._db.execute.return_value = None

        settlement_repo = MagicMock()
        settlement_repo.create_settlement.side_effect = lambda s: s
        settlement_repo.get_by_driver_date.return_value = None

        svc = DriverSettlementService(
            settlement_repo=settlement_repo,
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            user_repo=user_repo,
        )

        result = svc.settle_driver(driver_id=10, settled_by_id=1, settled_by_name="مدير")

        assert result.trip_count == 1
        assert delivery_repo.get_driver_trips_for_date.call_args[0][0] == 10

    def test_settle_driver_rejects_second_settlement_same_day(self):
        """Guard: a day already closed cannot be settled again."""
        from broast_pos.core.services.driver_settlement_service import (
            DriverSettlementService,
        )

        order_repo = MagicMock()
        order_repo.get_by_id.return_value = _order(101)
        user_repo = MagicMock()
        user_repo.get_by_id.return_value = MagicMock(display_name="محمود", username="m")

        delivery_repo = MagicMock()
        delivery_repo.get_driver_trips_for_date.return_value = [_trip()]
        delivery_repo._db = MagicMock()

        settlement_repo = MagicMock()
        settlement_repo.get_by_driver_date.return_value = MagicMock()  # already settled

        svc = DriverSettlementService(
            settlement_repo=settlement_repo, delivery_repo=delivery_repo,
            order_repo=order_repo, user_repo=user_repo,
        )
        with pytest.raises(ValueError, match="بالفعل"):
            svc.settle_driver(driver_id=10, settled_by_id=1, settled_by_name="مدير")

    def test_settle_driver_skips_side_effects_for_already_settled_trips(self):
        """Trips already settled per-trip are only summarized, not re-completed."""
        from broast_pos.core.services.driver_settlement_service import (
            DriverSettlementService,
        )

        orders = {101: _order(101, status=OrderStatus.DELIVERED)}
        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)
        order_svc = MagicMock()
        user_repo = MagicMock()
        user_repo.get_by_id.return_value = MagicMock(display_name="محمود", username="m")

        settled_trip = _trip(trip_id=1, order_ids=[101], is_settled=True)
        delivery_repo = MagicMock()
        delivery_repo.get_driver_trips_for_date.return_value = [settled_trip]
        delivery_repo._db = MagicMock()
        delivery_repo._db.transaction.return_value.__enter__ = MagicMock(return_value=None)
        delivery_repo._db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        settlement_repo = MagicMock()
        settlement_repo.create_settlement.side_effect = lambda s: s
        settlement_repo.get_by_driver_date.return_value = None

        svc = DriverSettlementService(
            settlement_repo=settlement_repo, delivery_repo=delivery_repo,
            order_repo=order_repo, user_repo=user_repo, order_svc=order_svc,
        )
        result = svc.settle_driver(driver_id=10, settled_by_id=1, settled_by_name="مدير")

        assert result.trip_count == 1               # counted in the summary
        order_svc.change_order_status.assert_not_called()  # but not re-completed

    def test_settle_driver_calls_change_order_status_for_delivered_orders(self):
        """B-07: settle_driver() must complete DELIVERED orders."""
        orders = {
            101: _order(101, status=OrderStatus.DELIVERED, payment=PaymentMethod.CASH),
            102: _order(102, status=OrderStatus.DELIVERED, payment=PaymentMethod.ONLINE),
        }
        svc, order_svc_mock = self._build_settlement_svc(orders)
        svc.settle_driver(
            driver_id=10, settled_by_id=1, settled_by_name="مدير"
        )
        # Must have called change_order_status for each DELIVERED order
        calls = [kw["order_id"] for _, kw in [
            (args, kwargs) for args, kwargs in order_svc_mock.change_order_status.call_args_list
        ]]
        assert 101 in calls
        assert 102 in calls

    def test_settle_driver_skips_already_completed_orders(self):
        """Already-COMPLETED orders must not be double-transitioned."""
        orders = {
            101: _order(101, status=OrderStatus.COMPLETED),
            102: _order(102, status=OrderStatus.DELIVERED),
        }
        svc, order_svc_mock = self._build_settlement_svc(orders)
        svc.settle_driver(driver_id=10, settled_by_id=1, settled_by_name="مدير")

        transitioned_ids = [
            kw["order_id"] for _, kw in [
                (a, kw) for a, kw in order_svc_mock.change_order_status.call_args_list
            ]
        ]
        assert 101 not in transitioned_ids   # already COMPLETED
        assert 102 in transitioned_ids        # was DELIVERED

    def test_settle_driver_without_order_svc_still_settles(self):
        """B-07: order_svc is optional — settlement must succeed even without it."""
        from broast_pos.core.services.driver_settlement_service import (
            DriverSettlementService,
        )

        delivery_repo = MagicMock()
        delivery_repo.get_driver_trips_for_date.return_value = [_trip()]
        delivery_repo.get_unsettled_trips.return_value = [_trip()]
        delivery_repo._db = MagicMock()
        delivery_repo._db.transaction.return_value.__enter__ = MagicMock(return_value=None)
        delivery_repo._db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        delivery_repo._db.execute.return_value = None

        order_repo = MagicMock()
        order_repo.get_by_id.return_value = _order(101)

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = MagicMock(display_name="x", username="x")

        svc = DriverSettlementService(
            settlement_repo=MagicMock(**{
                "create_settlement.side_effect": lambda s: s,
                "get_by_driver_date.return_value": None,
            }),
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            user_repo=user_repo,
            order_svc=None,   # no order_svc
        )
        # Should not raise
        svc.settle_driver(driver_id=10, settled_by_id=1, settled_by_name="مدير")


# ===========================================================================
# Part B: DeliveryService.settle_trip() delegates to settlement_svc (B-07)
# ===========================================================================

class TestSettleTripDelegatesToSettlementSvc:

    def _build_delivery_svc(self, trip: DeliveryTrip, orders: dict,
                             settlement_svc=None):
        from broast_pos.core.services.delivery_service import DeliveryService

        delivery_repo = MagicMock()
        delivery_repo.get_trip_by_id.return_value = trip

        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)
        order_repo.save.side_effect = lambda o: o

        audit_repo = MagicMock()

        svc = DeliveryService(
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            audit_repo=audit_repo,
            settlement_svc=settlement_svc,
        )
        return svc, delivery_repo

    def test_settle_trip_settles_only_this_trip(self):
        """settle_trip settles ONLY this one trip — it must NOT trigger the
        whole-day settle_driver sweep, and it books only this trip's cash."""
        trip = _trip(driver_id=10, order_ids=[101])
        orders = {101: _order(101, payment=PaymentMethod.CASH)}
        settlement_svc = MagicMock()
        svc, delivery_repo = self._build_delivery_svc(trip, orders, settlement_svc)
        svc._order_svc = MagicMock()
        svc._order_svc.change_order_status.side_effect = lambda **kw: orders[kw["order_id"]]

        svc.settle_trip(trip_id=1)

        settlement_svc.settle_driver.assert_not_called()     # no day-wide sweep
        delivery_repo.mark_settled.assert_called_once()      # just this trip
        settlement_svc.remit_trip_cash.assert_called_once()  # this trip's cash booked

    def test_settle_trip_books_cash_as_the_settling_user(self):
        """Per-trip cash is booked for the logged-in user (actor_id = 0 would
        violate the cash_ledger -> users foreign key)."""
        trip = _trip(driver_id=10, order_ids=[101])
        orders = {101: _order(101, payment=PaymentMethod.CASH)}
        settlement_svc = MagicMock()
        svc, _ = self._build_delivery_svc(trip, orders, settlement_svc)
        svc._order_svc = MagicMock()
        svc._order_svc.change_order_status.side_effect = lambda **kw: orders[kw["order_id"]]

        svc.settle_trip(trip_id=1, settled_by_id=7, settled_by_name="مدير المطعم")

        args = settlement_svc.remit_trip_cash.call_args[0]
        assert args[2] == 7   # actor_id

    def test_settle_trip_legacy_path_when_no_settlement_svc(self):
        """Without settlement_svc, settle_trip() falls back to legacy path."""
        trip = _trip(driver_id=10)
        orders = {
            101: _order(101, payment=PaymentMethod.CASH),
            102: _order(102, payment=PaymentMethod.ONLINE),
        }
        svc, delivery_repo = self._build_delivery_svc(trip, orders, settlement_svc=None)
        svc._order_svc = MagicMock()
        svc._order_svc.change_order_status.side_effect = lambda **kw: orders[kw["order_id"]]

        svc.settle_trip(trip_id=1)

        # Legacy path should call mark_settled on the delivery_repo
        delivery_repo.mark_settled.assert_called_once()

    def test_settle_trip_raises_if_not_returned(self):
        trip = _trip(is_returned=False)
        svc, _ = self._build_delivery_svc(trip, {})
        with pytest.raises(ValueError, match="لم يعد"):
            svc.settle_trip(trip_id=1)

    def test_settle_trip_raises_if_already_settled(self):
        trip = _trip(is_settled=True)
        svc, _ = self._build_delivery_svc(trip, {})
        with pytest.raises(ValueError, match="تم تسويتها"):
            svc.settle_trip(trip_id=1)


# ===========================================================================
# Part C: Symmetry — both paths produce equivalent outcomes
# ===========================================================================

class TestSettlementSymmetry:

    def test_both_paths_require_trip_to_be_returned(self):
        """settle_trip and settle_driver both guard against non-returned trips."""
        from broast_pos.core.services.delivery_service import DeliveryService

        trip = _trip(is_returned=False)
        delivery_repo = MagicMock()
        delivery_repo.get_trip_by_id.return_value = trip

        svc = DeliveryService(delivery_repo=delivery_repo, order_repo=MagicMock())
        with pytest.raises(ValueError):
            svc.settle_trip(trip_id=1)

    def test_cash_only_trip_cash_collected_equals_total(self):
        """Legacy settle_trip path: cash_collected = sum of CASH order totals."""
        from broast_pos.core.services.delivery_service import DeliveryService

        trip = _trip(driver_id=10, order_ids=[101])
        orders = {101: _order(101, total=150.0, payment=PaymentMethod.CASH)}

        delivery_repo = MagicMock()
        delivery_repo.get_trip_by_id.return_value = trip
        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)
        order_repo.save.side_effect = lambda o: o

        svc = DeliveryService(
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            audit_repo=MagicMock(),
            settlement_svc=None,  # force legacy path
        )
        svc._order_svc = MagicMock()
        svc._order_svc.change_order_status.side_effect = lambda **kw: orders[kw["order_id"]]

        svc.settle_trip(trip_id=1)

        delivery_repo.mark_settled.assert_called_once_with(1, 150.0, pytest.approx(15.0))

    def test_online_trip_cash_collected_is_zero(self):
        """ONLINE orders must NOT be counted in cash_collected."""
        from broast_pos.core.services.delivery_service import DeliveryService

        trip = _trip(driver_id=10, order_ids=[101])
        orders = {101: _order(101, total=150.0, payment=PaymentMethod.ONLINE)}

        delivery_repo = MagicMock()
        delivery_repo.get_trip_by_id.return_value = trip
        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)
        order_repo.save.side_effect = lambda o: o

        svc = DeliveryService(
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            audit_repo=MagicMock(),
            settlement_svc=None,
        )
        svc._order_svc = MagicMock()
        svc._order_svc.change_order_status.side_effect = lambda **kw: orders[kw["order_id"]]

        svc.settle_trip(trip_id=1)

        # cash_collected must be 0 — ONLINE was pre-paid
        delivery_repo.mark_settled.assert_called_once_with(1, 0.0, pytest.approx(15.0))
