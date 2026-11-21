"""
Regression tests for BUG-02 — inactive products must be rejected when
adding order items (create_order and amend_order), but existing open orders
that contain a product disabled afterwards must still be payable.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.core.models.user import User
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.order_service import OrderService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _product(*, is_active: bool, name: str = "برجر", product_id: int = 1):
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.is_active = is_active
    return p


def _shift():
    s = MagicMock()
    s.id = 1
    return s


def _manager() -> User:
    return User(id=99, username="mgr", display_name="مدير", role="manager",
                pin_hash="x", cashier_slot=None)


def _make_item(product_id: int = 1) -> OrderItem:
    return OrderItem(product_id=product_id, product_name="برجر",
                     unit_price=50.0, quantity=2)


def _make_order(items=None) -> Order:
    items = items or [_make_item()]
    o = Order(
        order_type=OrderType.TAKEAWAY,
        items=items,
        shift_id=1,
    )
    o.subtotal = sum(i.total_price for i in items)
    o.total = o.subtotal
    return o


def _svc(product_is_active: bool | None = True, product_exists: bool = True):
    """
    Build an OrderService with mocked dependencies.
    product_is_active=None means product_repo is not wired in (legacy).
    """
    fin = MagicMock()
    fin.ensure_shift_active.return_value = _shift()
    fin.get_next_invoice_number.return_value = 42

    saved_order = MagicMock()
    saved_order.id = 10
    saved_order.shift_id = 1
    saved_order.order_type = OrderType.TAKEAWAY
    saved_order.total = 100.0

    order_repo = MagicMock()
    order_repo.save.side_effect = lambda o: o

    product_repo = None
    if product_is_active is not None:
        product_repo = MagicMock()
        if product_exists:
            product_repo.get_by_id.return_value = _product(is_active=product_is_active)
        else:
            product_repo.get_by_id.return_value = None

    return OrderService(
        order_repo=order_repo,
        audit_repo=MagicMock(),
        auth_service=MagicMock(),
        financial_service=fin,
        status_history_repo=MagicMock(),
        audit_service=AuditService(MagicMock()),
        product_repo=product_repo,
    )


# ---------------------------------------------------------------------------
# create_order — inactive product rejected
# ---------------------------------------------------------------------------

class TestCreateOrderInactiveProduct:
    def test_inactive_product_raises(self):
        svc = _svc(product_is_active=False)
        order = _make_order()
        with pytest.raises(ValueError, match="غير متاح"):
            svc.create_order(order, cashier_id=1, cashier_name="كاشير")

    def test_missing_product_raises(self):
        _svc(product_is_active=None, product_exists=False)
        # product_repo not wired — check skipped (no error)
        # wiring it but product missing:
        svc2 = _svc(product_is_active=True, product_exists=False)
        svc2._products.get_by_id.return_value = None
        order = _make_order()
        with pytest.raises(ValueError, match="غير موجود"):
            svc2.create_order(order, cashier_id=1, cashier_name="كاشير")

    def test_active_product_succeeds(self):
        svc = _svc(product_is_active=True)
        order = _make_order()
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result is order

    def test_no_product_repo_skips_check(self):
        """Legacy: OrderService without product_repo should not raise."""
        svc = _svc(product_is_active=None)
        order = _make_order()
        result = svc.create_order(order, cashier_id=1, cashier_name="كاشير")
        assert result is order


# ---------------------------------------------------------------------------
# amend_order — inactive added_items rejected
# ---------------------------------------------------------------------------

class TestAmendOrderInactiveProduct:
    def _existing_order(self, order_id: int = 5) -> Order:
        o = _make_order()
        o.id = order_id
        o.status = OrderStatus.NEW
        return o

    def _amend_svc(self, product_is_active: bool):
        svc = _svc(product_is_active=product_is_active)
        existing = self._existing_order()
        svc._orders.get_by_id.return_value = existing
        svc._verify_manager_pin = MagicMock(return_value=_manager())
        return svc

    def test_adding_inactive_item_raises(self):
        svc = self._amend_svc(product_is_active=False)
        with pytest.raises(ValueError, match="غير متاح"):
            svc.amend_order(5, added_items=[_make_item()], removed_items=[])

    def test_adding_active_item_succeeds(self):
        svc = self._amend_svc(product_is_active=True)
        result = svc.amend_order(5, added_items=[_make_item()], removed_items=[])
        assert result is not None

    def test_removing_items_bypasses_product_check(self):
        """Removing items (not adding) must not trigger product availability check."""
        svc = self._amend_svc(product_is_active=False)
        existing = self._existing_order()
        existing.items = [_make_item(product_id=1)]
        svc._orders.get_by_id.return_value = existing
        # Remove the item — product is inactive but that's irrelevant for removal
        # Removal requires manager PIN (by design), so pass one
        result = svc.amend_order(
            5, added_items=[], removed_items=[_make_item(product_id=1)],
            manager_pin="1234"
        )
        assert result is not None


# ---------------------------------------------------------------------------
# complete_order — paying an order whose product was later disabled still works
# ---------------------------------------------------------------------------

class TestCompleteOrderIgnoresProductStatus:
    def test_paying_order_with_disabled_product_succeeds(self):
        """complete_order must NOT check product availability — payment must go through."""
        fin = MagicMock()

        order = _make_order()
        order.id = 7
        order.status = OrderStatus.NEW
        order.is_paid = False
        order.total = 100.0
        order.order_type = OrderType.TAKEAWAY

        order_repo = MagicMock()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o

        payment_result = MagicMock()
        payment_result.is_valid = True
        payment_result.method = PaymentMethod.CASH
        payment_result.amount_paid = 100.0
        payment_result.change_given = 0.0

        payment_coordinator = MagicMock()
        payment_coordinator.calculate.return_value = payment_result

        # Product repo says product is inactive — must NOT affect payment
        product_repo = MagicMock()
        product_repo.get_by_id.return_value = _product(is_active=False)

        svc = OrderService(
            order_repo=order_repo,
            audit_repo=MagicMock(),
            auth_service=MagicMock(),
            financial_service=fin,
            status_history_repo=MagicMock(),
            audit_service=AuditService(MagicMock()),
            payment_coordinator=payment_coordinator,
            product_repo=product_repo,
        )

        result = svc.complete_order(
            7, PaymentMethod.CASH, amount_received=100.0,
            actor_id=1, actor_name="كاشير"
        )
        assert result.is_paid is True
