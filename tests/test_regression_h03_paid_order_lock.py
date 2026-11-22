"""
Regression tests — H03: paid active orders remained financially editable.

Root cause:
  complete_order() blocked COMPLETED/CANCELLED orders but not an
  already-paid order that stays ACTIVE (e.g. a takeaway paid with
  finalize=False) — so it could be paid a second time, silently
  overwriting payment_method/amount_paid. amend_order() had no paid-order
  guard at all (apply_discount() already had one), so items could still be
  added/removed after payment, changing the order's total while
  amount_paid stayed frozen at the original paid amount.

  At the controller layer, add_item/change_quantity/remove_item/
  set_customer_info all mutated the in-memory order directly — so even
  reloading a paid order and touching these would change the DISPLAYED
  total (e.g. showing EGP 80 instead of the EGP 95 actually paid) before
  any save was even attempted.

Fix verified here:
  - complete_order() rejects a second payment on an already-paid order.
  - amend_order() rejects adding/removing items on a paid order.
  - OrderController.add_item/change_quantity/remove_item/set_customer_info
    all no-op (or return a clear failure) once the current order is paid.
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
from broast_pos.core.services.order_service import OrderService
from broast_pos.features.order_lifecycle.order_controller import OrderController
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers


def _paid_active_order(order_id: int = 5, total: float = 95.0) -> Order:
    return Order(
        id=order_id, invoice_no=1, order_type=OrderType.TAKEAWAY,
        status=OrderStatus.NEW,  # still active — takeaway paid with finalize=False
        items=[OrderItem(product_id=1, product_name="برجر", quantity=1, unit_price=total)],
        subtotal=total, total=total,
        payment_method=PaymentMethod.CASH, amount_paid=total, is_paid=True,
        shift_id=1,
    )


class TestH03ServiceLayerRejectsPaidOrderChanges:

    def test_complete_order_rejects_second_payment(self):
        order = _paid_active_order()
        order_repo = MagicMock()
        order_repo.get_by_id.return_value = order
        svc = OrderService(order_repo=order_repo)

        with pytest.raises(ValueError, match="مدفوع بالفعل"):
            svc.complete_order(order_id=5, payment_method=PaymentMethod.VISA, amount_received=95.0)

        order_repo.save.assert_not_called()

    def test_amend_order_rejects_item_changes_on_paid_order(self):
        order = _paid_active_order()
        order_repo = MagicMock()
        order_repo.get_by_id.return_value = order
        svc = OrderService(order_repo=order_repo)

        new_item = OrderItem(product_id=2, product_name="بيبسي", quantity=1, unit_price=25.0)
        with pytest.raises(ValueError, match="مدفوع بالفعل"):
            svc.amend_order(order_id=5, added_items=[new_item], removed_items=[])

        order_repo.save.assert_not_called()
        assert order.total == 95.0, "Total must stay exactly what was paid"


def _build_ctrl_with_paid_order() -> OrderController:
    order_repo = MagicMock(**{"save.side_effect": lambda o: o})
    svc = OrderService(order_repo=order_repo)
    ctrl = OrderController(
        order_service=svc,
        financial_service=MagicMock(),
        auth_service=MagicMock(),
        print_triggers=MagicMock(spec=PrintTriggers),
    )
    ctrl._current_order = _paid_active_order()
    return ctrl


class TestH03ControllerNeverShowsChangedTotalForPaidOrder:
    """H03: a paid order's displayed total (EGP 95) must never change to
    something else (e.g. EGP 80) just by touching these mutators."""

    def test_add_item_does_not_change_paid_order_total(self):
        ctrl = _build_ctrl_with_paid_order()
        ctrl.add_item(product_id=9, product_name="اضافي", unit_price=50.0, quantity=1)
        assert ctrl._current_order.total == 95.0
        assert len(ctrl._current_order.items) == 1

    def test_change_quantity_does_not_change_paid_order_total(self):
        ctrl = _build_ctrl_with_paid_order()
        ctrl.change_quantity(index=0, delta=5)
        assert ctrl._current_order.total == 95.0
        assert ctrl._current_order.items[0].quantity == 1

    def test_remove_item_rejected_on_paid_order(self):
        ctrl = _build_ctrl_with_paid_order()
        ok, msg = ctrl.remove_item(index=0, manager_pin="1234")
        assert ok is False
        assert ctrl._current_order.total == 95.0
        assert len(ctrl._current_order.items) == 1

    def test_set_customer_info_does_not_change_paid_order_fee(self):
        ctrl = _build_ctrl_with_paid_order()
        ctrl._current_order.order_type = OrderType.DELIVERY
        ctrl._current_order.delivery_fee = 15.0
        ctrl._current_order.total = 95.0  # 80 items + 15 delivery, already paid as 95

        ctrl.set_customer_info(
            customer_id=1, name="عميل آخر", phone="010", address="شارع آخر",
            zone="منطقة أخرى", delivery_fee=0.0,  # manipulated/incorrect re-entry
        )

        assert ctrl._current_order.delivery_fee == 15.0, (
            "H03 regression: delivery fee changed on an already-paid order"
        )
        assert ctrl._current_order.total == 95.0
