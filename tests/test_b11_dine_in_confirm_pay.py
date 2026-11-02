"""
Tests for the dine-in confirm/pay split and table move.

Verifies:
1. Dine-in confirm does NOT request immediate payment (table settled later).
2. Takeaway/pickup still request immediate payment at confirm time.
3. OrderService.change_table moves a saved dine-in order to a free table.
4. change_table rejects a table already held by another open order.
5. change_table rejects non-dine-in orders and closed orders.
6. OrderController.change_table assigns in memory for an unsaved order and
   persists via the service for a saved order.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from broast_pos.core.models.order import (
    Order, OrderItem, OrderStatus, OrderType,
)
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.audit_service import AuditService
from broast_pos.features.order_lifecycle.order_controller import OrderController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(price: float = 100.0) -> OrderItem:
    return OrderItem(product_id=1, product_name="بروست", unit_price=price, quantity=1)


def _dine_in_order(order_id=7, table_no=2, status=OrderStatus.NEW) -> Order:
    return Order(
        id=order_id,
        invoice_no=55 if order_id else None,
        order_type=OrderType.DINE_IN,
        status=status,
        items=[_item(120.0)],
        subtotal=120.0,
        total=120.0,
        table_no=table_no,
        shift_id=1,
    )


def _order_svc():
    """OrderService with all dependencies mocked for unit testing."""
    order_repo = MagicMock()
    order_repo.save.side_effect = lambda o: o
    financial_svc = MagicMock()
    financial_svc.ensure_shift_active.return_value = MagicMock(id=1)
    financial_svc.get_next_invoice_number.return_value = 55
    status_repo = MagicMock()
    audit_svc = AuditService(MagicMock())
    svc = OrderService(
        order_repo=order_repo,
        financial_service=financial_svc,
        status_history_repo=status_repo,
        audit_service=audit_svc,
    )
    return svc, order_repo


def _ctrl_stub(current_order, order_svc=None):
    ctrl = OrderController.__new__(OrderController)
    ctrl._current_order = current_order
    ctrl._order_svc = order_svc or MagicMock()
    ctrl._occupied_tables = {}
    ctrl._listeners = {}
    ctrl._print = MagicMock()
    ctrl._notify_order_changed = MagicMock()
    ctrl._notify_table_changed = MagicMock()
    ctrl._recalc_totals = MagicMock()
    ctrl._order_to_dict = MagicMock(return_value={})
    return ctrl


# ===========================================================================
# Part A: confirm_order — dine-in no longer needs immediate payment
# ===========================================================================

class TestConfirmNeedsImmediatePayment:

    def test_dine_in_does_not_need_immediate_payment(self):
        order = _dine_in_order(order_id=None, table_no=4)
        ctrl = _ctrl_stub(order)
        ctrl._order_svc.create_order.return_value = _dine_in_order(order_id=7, table_no=4)
        ok, res = ctrl.confirm_order(cashier_id=1, cashier_name="كاشير")
        assert ok is True
        assert res.needs_immediate_payment is False, \
            "Dine-in must NOT prompt payment at confirm — it is settled later"

    def test_takeaway_needs_immediate_payment(self):
        order = Order(
            id=None, invoice_no=None, order_type=OrderType.TAKEAWAY,
            status=OrderStatus.NEW, items=[_item()], subtotal=100.0,
            total=100.0, shift_id=1,
        )
        ctrl = _ctrl_stub(order)
        saved = Order(
            id=9, invoice_no=56, order_type=OrderType.TAKEAWAY,
            status=OrderStatus.NEW, items=[_item()], subtotal=100.0,
            total=100.0, shift_id=1,
        )
        ctrl._order_svc.create_order.return_value = saved
        ok, res = ctrl.confirm_order(cashier_id=1, cashier_name="كاشير")
        assert ok is True
        assert res.needs_immediate_payment is True


# ===========================================================================
# Part B: OrderService.change_table
# ===========================================================================

class TestServiceChangeTable:

    def test_moves_to_free_table(self):
        svc, repo = _order_svc()
        repo.get_by_id.return_value = _dine_in_order(order_id=7, table_no=2)
        repo.get_by_table.return_value = None  # target free
        result = svc.change_table(order_id=7, new_table_number=8)
        assert result.table_no == 8
        repo.save.assert_called_once()

    def test_rejects_occupied_table(self):
        svc, repo = _order_svc()
        repo.get_by_id.return_value = _dine_in_order(order_id=7, table_no=2)
        repo.get_by_table.return_value = _dine_in_order(order_id=99, table_no=8)
        with pytest.raises(ValueError):
            svc.change_table(order_id=7, new_table_number=8)
        repo.save.assert_not_called()

    def test_same_table_is_noop(self):
        svc, repo = _order_svc()
        repo.get_by_id.return_value = _dine_in_order(order_id=7, table_no=2)
        result = svc.change_table(order_id=7, new_table_number=2)
        assert result.table_no == 2
        repo.save.assert_not_called()

    def test_rejects_non_dine_in(self):
        svc, repo = _order_svc()
        takeaway = Order(
            id=7, invoice_no=55, order_type=OrderType.TAKEAWAY,
            status=OrderStatus.NEW, items=[_item()], subtotal=100.0,
            total=100.0, shift_id=1,
        )
        repo.get_by_id.return_value = takeaway
        with pytest.raises(ValueError):
            svc.change_table(order_id=7, new_table_number=8)

    def test_rejects_closed_order(self):
        svc, repo = _order_svc()
        repo.get_by_id.return_value = _dine_in_order(
            order_id=7, table_no=2, status=OrderStatus.COMPLETED
        )
        with pytest.raises(ValueError):
            svc.change_table(order_id=7, new_table_number=8)


# ===========================================================================
# Part C: OrderController.change_table
# ===========================================================================

class TestControllerChangeTable:

    def test_unsaved_order_assigns_in_memory(self):
        order = _dine_in_order(order_id=None, table_no=None)
        ctrl = _ctrl_stub(order)
        ok, _ = ctrl.change_table(5)
        assert ok is True
        assert ctrl._current_order.table_no == 5
        # Unsaved → nothing persisted
        ctrl._order_svc.change_table.assert_not_called()

    def test_saved_order_persists_and_frees_old_table(self):
        order = _dine_in_order(order_id=7, table_no=2)
        svc = MagicMock()
        svc.change_table.return_value = _dine_in_order(order_id=7, table_no=8)
        ctrl = _ctrl_stub(order, order_svc=svc)
        ctrl._occupied_tables = {2: "#55"}
        ok, _ = ctrl.change_table(8)
        assert ok is True
        svc.change_table.assert_called_once_with(7, 8)
        assert 2 not in ctrl._occupied_tables, "old table must be freed"
        assert ctrl._occupied_tables.get(8) == "#55"

    def test_saved_order_rejection_bubbles_up(self):
        order = _dine_in_order(order_id=7, table_no=2)
        svc = MagicMock()
        svc.change_table.side_effect = ValueError("الطاولة مشغولة بطلب آخر")
        ctrl = _ctrl_stub(order, order_svc=svc)
        ok, msg = ctrl.change_table(8)
        assert ok is False
        assert "مشغولة" in msg
