"""
Tests for B-14 — unpaid-completion guard (Checkup-Fix).

change_order_status() must NOT silently fabricate payment when an order
reaches COMPLETED while unpaid. It is fail-closed: only callers that have
booked the cash elsewhere (delivery settlement) may authorize it via
allow_unpaid_complete=True, and even then no ledger entry is written here.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType
from broast_pos.core.services.order_service import OrderService


def _make_delivery_order(oid: int = 1) -> Order:
    return Order(
        id=oid,
        invoice_no=oid,
        order_type=OrderType.DELIVERY,
        status=OrderStatus.DELIVERED,
        items=[OrderItem(product_id=1, product_name="x", unit_price=100.0, quantity=1)],
        subtotal=100.0,
        total=100.0,
        shift_id=1,
        is_paid=False,
    )


def _svc(order: Order) -> tuple[OrderService, MagicMock]:
    order_repo = MagicMock()
    order_repo.get_by_id.side_effect = lambda oid: order if oid == order.id else None
    order_repo.save.side_effect = lambda o: o
    ledger = MagicMock()
    svc = OrderService(
        order_repo=order_repo,
        status_history_repo=MagicMock(**{"record_transition.return_value": None}),
        ledger_repo=ledger,
    )
    return svc, ledger


def test_unpaid_complete_without_authorization_is_refused():
    order = _make_delivery_order()
    svc, ledger = _svc(order)

    with pytest.raises(ValueError):
        svc.change_order_status(order.id, OrderStatus.COMPLETED)

    # Order must stay unpaid and no ledger entry may be written.
    assert order.is_paid is False
    ledger.append.assert_not_called()


def test_authorized_unpaid_complete_marks_paid_without_ledger():
    order = _make_delivery_order()
    svc, ledger = _svc(order)

    saved = svc.change_order_status(
        order.id, OrderStatus.COMPLETED, allow_unpaid_complete=True
    )

    assert saved.is_paid is True
    assert saved.amount_paid == order.total
    assert saved.paid_at  # timestamp backfilled
    # Cash for settlement is booked at trip level, never here.
    ledger.append.assert_not_called()
