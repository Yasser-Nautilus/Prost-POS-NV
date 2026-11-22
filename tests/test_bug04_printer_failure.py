"""
Regression tests for BUG-04 — printer failures are swallowed silently.

Each print trigger now returns a bool. confirm_order, complete_payment and
save_amendment must surface that bool to the bridge via print_ok/print_failed
so the frontend can inform the cashier without blocking the successful action.

Key invariant: payment is NOT rolled back when receipt printing fails.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
)
from broast_pos.features.order_lifecycle.order_controller import (
    ConfirmResult,
    OrderController,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item() -> OrderItem:
    return OrderItem(product_id=1, product_name="برجر", quantity=1, unit_price=50.0)


def _dine_in_order(*, order_id=None, table_no=3) -> Order:
    return Order(
        id=order_id, invoice_no=None, order_type=OrderType.DINE_IN,
        status=OrderStatus.NEW, items=[_item()], subtotal=50.0,
        total=50.0, shift_id=1, table_no=table_no,
    )


def _ctrl(current_order, *, kitchen_ok=True, receipt_ok=True, amendment_ok=True):
    ctrl = MagicMock(spec=OrderController)
    ctrl._current_order = current_order
    ctrl._cashier_slot = 1
    ctrl._occupied_tables = {}
    ctrl._amendment_tracker = MagicMock()
    ctrl._amendment_tracker.has_changes.return_value = True
    ctrl._amendment_tracker.get_changes.return_value = ([], [])

    order_svc = MagicMock()
    order_svc.create_order.return_value = Order(
        id=10, invoice_no=1, order_type=current_order.order_type,
        status=OrderStatus.NEW, items=current_order.items,
        subtotal=current_order.subtotal, total=current_order.total, shift_id=1,
        table_no=getattr(current_order, "table_no", None),
    )
    order_svc.complete_order.return_value = current_order
    order_svc.amend_order.return_value = None
    ctrl._order_svc = order_svc

    financial = MagicMock()
    financial.ensure_shift_active.return_value = MagicMock(id=1)
    ctrl._financial_svc = financial

    auth = MagicMock()
    auth.verify_pin.return_value = MagicMock(id=99, is_manager_or_above=lambda: True)
    ctrl._auth_svc = auth

    print_triggers = MagicMock()
    print_triggers.on_order_created.return_value = kitchen_ok
    print_triggers.on_order_completed.return_value = receipt_ok
    print_triggers.on_order_amended.return_value = amendment_ok
    ctrl._print = print_triggers

    # Wire real methods onto the mock spec
    ctrl.confirm_order = OrderController.confirm_order.__get__(ctrl, OrderController)
    ctrl.complete_payment = OrderController.complete_payment.__get__(ctrl, OrderController)
    ctrl.save_amendment = OrderController.save_amendment.__get__(ctrl, OrderController)
    ctrl._order_to_dict = lambda o: {"id": o.id, "invoice_no": o.invoice_no,
                                      "total": o.total, "order_type": o.order_type.value}
    ctrl._recalc_totals = MagicMock()
    ctrl._notify_order_changed = MagicMock()
    ctrl._notify_table_changed = MagicMock()

    return ctrl


# ---------------------------------------------------------------------------
# confirm_order: kitchen ticket
# ---------------------------------------------------------------------------

class TestConfirmOrderKitchenPrint:

    def test_print_ok_true_when_kitchen_succeeds(self):
        ctrl = _ctrl(_dine_in_order(), kitchen_ok=True)
        ok, res = ctrl.confirm_order(cashier_id=1, cashier_name="كاشير")
        assert ok is True
        assert isinstance(res, ConfirmResult)
        assert res.print_ok is True

    def test_print_ok_false_when_kitchen_fails(self):
        ctrl = _ctrl(_dine_in_order(), kitchen_ok=False)
        ok, res = ctrl.confirm_order(cashier_id=1, cashier_name="كاشير")
        assert ok is True, "order confirm must succeed even when kitchen print fails"
        assert res.print_ok is False

    def test_order_saved_even_when_kitchen_print_fails(self):
        ctrl = _ctrl(_dine_in_order(), kitchen_ok=False)
        ok, res = ctrl.confirm_order(cashier_id=1, cashier_name="كاشير")
        assert ok is True
        ctrl._order_svc.create_order.assert_called_once()


# ---------------------------------------------------------------------------
# complete_payment: customer receipt
# ---------------------------------------------------------------------------

class TestCompletePaymentReceiptPrint:

    def test_print_ok_true_when_receipt_succeeds(self):
        order = _dine_in_order(order_id=5)
        ctrl = _ctrl(order, receipt_ok=True)
        ok, _msg, print_ok = ctrl.complete_payment(
            order_id=5, payment_method="cash", amount_paid=50.0
        )
        assert ok is True
        assert print_ok is True

    def test_print_ok_false_when_receipt_fails(self):
        order = _dine_in_order(order_id=5)
        ctrl = _ctrl(order, receipt_ok=False)
        ok, _msg, print_ok = ctrl.complete_payment(
            order_id=5, payment_method="cash", amount_paid=50.0
        )
        assert ok is True, "payment must succeed even when receipt printing fails"
        assert print_ok is False

    def test_payment_recorded_even_when_receipt_print_fails(self):
        """Core invariant: receipt failure must NEVER roll back the payment."""
        order = _dine_in_order(order_id=5)
        ctrl = _ctrl(order, receipt_ok=False)
        ok, _msg, _print_ok = ctrl.complete_payment(
            order_id=5, payment_method="cash", amount_paid=50.0
        )
        assert ok is True
        ctrl._order_svc.complete_order.assert_called_once()

    def test_payment_error_returns_three_element_tuple(self):
        """Error path must also return 3 elements so bridge unpacking never fails."""
        order = _dine_in_order(order_id=5)
        ctrl = _ctrl(order)
        ctrl._order_svc.complete_order.side_effect = ValueError("لا توجد وردية")
        result = ctrl.complete_payment(order_id=5, payment_method="cash", amount_paid=50.0)
        assert len(result) == 3
        ok, _msg, print_ok = result
        assert ok is False
        assert print_ok is True


# ---------------------------------------------------------------------------
# save_amendment: amendment kitchen ticket
# ---------------------------------------------------------------------------

class TestSaveAmendmentPrint:

    def test_print_ok_true_when_amendment_ticket_succeeds(self):
        order = _dine_in_order(order_id=7)
        ctrl = _ctrl(order, amendment_ok=True)
        ctrl._amendment_tracker.has_changes.return_value = True
        ctrl._amendment_tracker.get_changes.return_value = ([], [])
        ctrl._auth_svc.verify_pin.return_value = MagicMock(
            id=99, is_manager_or_above=MagicMock(return_value=True)
        )
        ok, _msg, print_ok = ctrl.save_amendment(manager_pin="1234")
        assert ok is True
        assert print_ok is True

    def test_print_ok_false_when_amendment_ticket_fails(self):
        order = _dine_in_order(order_id=7)
        ctrl = _ctrl(order, amendment_ok=False)
        ctrl._amendment_tracker.has_changes.return_value = True
        ctrl._amendment_tracker.get_changes.return_value = ([], [])
        ctrl._auth_svc.verify_pin.return_value = MagicMock(
            id=99, is_manager_or_above=MagicMock(return_value=True)
        )
        ok, _msg, print_ok = ctrl.save_amendment(manager_pin="1234")
        assert ok is True, "amendment must save even when kitchen ticket fails"
        assert print_ok is False
