"""
Tests for B-02 — Delivery Payment Method.

Verifies:
1. set_customer_info() records payment_method on the order
2. set_customer_info() defaults to CASH when payment_method is omitted
3. create_order() defaults delivery to CASH when payment_method is None
4. create_order() marks ONLINE delivery as is_paid=True + amount_paid atomically
5. ONLINE delivery does NOT need a secondary complete_order() call
6. Non-delivery orders are unaffected
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from typing import Optional

from broast_pos.core.models.order import (
    Order, OrderItem, OrderStatus, OrderType, PaymentMethod
)
from broast_pos.core.models.user import User
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.audit_service import AuditService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(price: float = 100.0) -> OrderItem:
    return OrderItem(product_id=1, product_name="بيتزا", unit_price=price, quantity=1)


def _delivery_order(payment_method: Optional[PaymentMethod] = None) -> Order:
    return Order(
        id=None,
        invoice_no=None,
        order_type=OrderType.DELIVERY,
        status=OrderStatus.NEW,
        items=[_item(120.0)],
        subtotal=120.0,
        total=140.0,  # includes 20 delivery fee
        delivery_fee=20.0,
        customer_phone="01012345678",
        customer_address="شارع التحرير",
        shift_id=None,
        payment_method=payment_method,
    )


def _order_svc():
    """OrderService with all dependencies mocked for unit testing."""
    order_repo = MagicMock()
    order_repo.save.side_effect = lambda o: o  # return saved order as-is
    financial_svc = MagicMock()
    financial_svc.ensure_shift_active.return_value = MagicMock(id=1)
    financial_svc.get_next_invoice_number.return_value = 42
    status_repo = MagicMock()
    audit_svc = AuditService(MagicMock())

    svc = OrderService(
        order_repo=order_repo,
        financial_service=financial_svc,
        status_history_repo=status_repo,
        audit_service=audit_svc,
    )
    return svc


# ===========================================================================
# Part A: create_order() delivery payment defaults
# ===========================================================================

class TestCreateOrderDeliveryPayment:

    def test_cash_delivery_is_not_marked_paid(self):
        """Cash delivery: is_paid must be False after create_order."""
        svc = _order_svc()
        order = _delivery_order(payment_method=PaymentMethod.CASH)
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result.is_paid is False or result.is_paid is None
        assert result.payment_method == PaymentMethod.CASH

    def test_online_delivery_marked_paid_atomically(self):
        """ONLINE delivery: is_paid=True, amount_paid=total at creation."""
        svc = _order_svc()
        order = _delivery_order(payment_method=PaymentMethod.ONLINE)
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result.is_paid is True, "ONLINE delivery must be marked paid"
        assert result.amount_paid == pytest.approx(result.total), \
            "amount_paid must equal total for ONLINE delivery"
        assert result.paid_at is not None, "paid_at must be set for ONLINE delivery"

    def test_null_payment_method_defaults_to_cash(self):
        """B-02: delivery order with no payment_method must default to CASH."""
        svc = _order_svc()
        order = _delivery_order(payment_method=None)
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result.payment_method == PaymentMethod.CASH, \
            "B-02 violation: delivery order saved with NULL payment_method"

    def test_null_payment_delivery_is_not_marked_paid(self):
        """After defaulting to CASH, is_paid stays False."""
        svc = _order_svc()
        order = _delivery_order(payment_method=None)
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result.is_paid is False or result.is_paid is None

    def test_online_delivery_paid_at_is_set(self):
        """paid_at must be an ISO timestamp for ONLINE delivery."""
        import re
        svc = _order_svc()
        order = _delivery_order(payment_method=PaymentMethod.ONLINE)
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result.paid_at is not None
        # Rough ISO timestamp check
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", result.paid_at)

    def test_takeaway_unaffected_by_delivery_logic(self):
        """Non-delivery orders must not be touched by the delivery payment block."""
        svc = _order_svc()
        order = Order(
            id=None, invoice_no=None,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.NEW,
            items=[_item(100.0)],
            subtotal=100.0, total=100.0, shift_id=None,
            payment_method=None,
        )
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        # Takeaway: payment_method stays None (user picks at checkout)
        assert result.is_paid is False or result.is_paid is None


# ===========================================================================
# Part B: OrderController.set_customer_info() payment_method handling
# ===========================================================================

class TestSetCustomerInfoPaymentMethod:

    def _ctrl_with_order(self, order: Order):
        """Build a minimal OrderController stub with the given in-memory order."""
        from broast_pos.features.order_lifecycle.order_controller import OrderController
        ctrl = OrderController.__new__(OrderController)
        ctrl._current_order = order
        ctrl._listeners = {}
        ctrl._notify_order_changed = MagicMock()
        ctrl._recalc_totals = MagicMock()
        return ctrl

    def test_set_customer_info_records_cash(self):
        """payment_method='cash' must set PaymentMethod.CASH on the order."""
        order = _delivery_order()
        ctrl = self._ctrl_with_order(order)
        ctrl.set_customer_info(
            phone="01012345678", name="أحمد", address="شارع النيل",
            delivery_fee=20.0, payment_method="cash",
        )
        assert ctrl._current_order.payment_method == PaymentMethod.CASH

    def test_set_customer_info_records_online(self):
        """payment_method='online' must set PaymentMethod.ONLINE on the order."""
        order = _delivery_order()
        ctrl = self._ctrl_with_order(order)
        ctrl.set_customer_info(
            phone="01012345678", name="أحمد", address="شارع النيل",
            delivery_fee=20.0, payment_method="online",
        )
        assert ctrl._current_order.payment_method == PaymentMethod.ONLINE

    def test_set_customer_info_defaults_delivery_to_cash(self):
        """Omitting payment_method for delivery must default to CASH."""
        order = _delivery_order(payment_method=None)
        ctrl = self._ctrl_with_order(order)
        ctrl.set_customer_info(
            phone="01012345678", name="أحمد", address="شارع النيل",
            delivery_fee=20.0,
            # no payment_method arg
        )
        assert ctrl._current_order.payment_method == PaymentMethod.CASH, \
            "B-02: delivery order payment_method must default to CASH"

    def test_set_customer_info_invalid_method_falls_back_to_cash(self):
        """Unknown payment_method string must fall back to CASH, not crash."""
        order = _delivery_order()
        ctrl = self._ctrl_with_order(order)
        ctrl.set_customer_info(
            phone="01012345678", name="أحمد", address="شارع النيل",
            delivery_fee=20.0, payment_method="bitcoin",  # invalid
        )
        assert ctrl._current_order.payment_method == PaymentMethod.CASH


# ===========================================================================
# Part C: settle_trip cash calculation after B-02
# ===========================================================================

class TestSettleTripCashAfterB02:
    """After B-02, cash_collected must correctly include cash delivery orders."""

    def test_cash_delivery_payment_method_is_not_null(self):
        """The root cause of F-02: payment_method=NULL caused cash_collected=0.
        After B-02, payment_method is CASH, so settle_trip can count it."""
        svc = _order_svc()
        order = _delivery_order(payment_method=None)  # simulate old bad state
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        # After B-02 fix, payment_method must be CASH, never NULL
        assert result.payment_method is not None, \
            "F-02 regression: payment_method is still NULL after create_order"
        assert result.payment_method == PaymentMethod.CASH
