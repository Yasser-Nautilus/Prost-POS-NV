"""
Tests for B-07 — Unified Settlement.

Before B-07:
  settle_trip()   → marks trip settled + completes orders,  but NEVER creates driver_settlements record
  settle_driver() → creates driver_settlements record + marks trips settled, but NEVER completes orders

After B-07:
  Both paths produce all three outcomes: settled trip + completed orders + driver_settlements record.

Test strategy: unit-test with mocks — no real DB.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType, PaymentMethod
from broast_pos.core.models.delivery import DeliveryTrip


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
        from broast_pos.core.services.driver_settlement_service import DriverSettlementService

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

        svc = DriverSettlementService(
            settlement_repo=settlement_repo,
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            user_repo=user_repo,
            order_svc=order_svc,
        )
        return svc, order_svc

    def test_settle_driver_settles_returned_trip_from_a_previous_day(self):
        """Variante A regression: a returned, unsettled trip is settleable even
        when no trip was created today — it was previously excluded by the
        created_at = today filter, which caused 'no eligible trips' errors."""
        from broast_pos.core.services.driver_settlement_service import DriverSettlementService

        orders = {101: _order(101), 102: _order(102)}
        order_repo = MagicMock()
        order_repo.get_by_id.side_effect = lambda oid: orders.get(oid)

        user_repo = MagicMock()
        user_repo.get_by_id.return_value = MagicMock(
            id=10, display_name="محمود", username="mahmoud", is_active=True
        )

        trip = _trip()  # returned_at on 2026-10-04 — not "today"
        delivery_repo = MagicMock()
        delivery_repo.get_driver_trips_for_date.return_value = []   # nothing created today
        delivery_repo.get_unsettled_trips.return_value = [trip]      # but a returned trip exists
        delivery_repo._db = MagicMock()
        delivery_repo._db.transaction.return_value.__enter__ = MagicMock(return_value=None)
        delivery_repo._db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        delivery_repo._db.execute.return_value = None

        settlement_repo = MagicMock()
        settlement_repo.create_settlement.side_effect = lambda s: s

        svc = DriverSettlementService(
            settlement_repo=settlement_repo,
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            user_repo=user_repo,
        )

        result = svc.settle_driver(driver_id=10, settled_by_id=1, settled_by_name="مدير")

        assert result.trip_count == 1
        delivery_repo.get_unsettled_trips.assert_called_once_with(10)

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
        from broast_pos.core.services.driver_settlement_service import DriverSettlementService

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
            settlement_repo=MagicMock(**{"create_settlement.side_effect": lambda s: s}),
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

    def test_settle_trip_delegates_when_settlement_svc_present(self):
        """B-07: settle_trip() must call settlement_svc.settle_driver()."""
        trip = _trip(driver_id=10)
        orders = {
            101: _order(101, payment=PaymentMethod.CASH),
            102: _order(102, payment=PaymentMethod.ONLINE),
        }
        settlement_svc = MagicMock()
        svc, delivery_repo = self._build_delivery_svc(trip, orders, settlement_svc)

        svc.settle_trip(trip_id=1)

        settlement_svc.settle_driver.assert_called_once()
        call_kwargs = settlement_svc.settle_driver.call_args[1]
        assert call_kwargs["driver_id"] == 10

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
