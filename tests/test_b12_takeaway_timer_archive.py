"""
Tests for the takeaway pickup-window auto-archive and the order history feed.

Verifies:
1. complete_order(finalize=False) records payment but keeps the order active.
2. complete_order default (finalize=True) still closes the order.
3. auto_complete_expired_takeaways closes paid takeaways past the window.
4. ...and leaves recent takeaways untouched.
5. ...and ignores non-takeaway active orders.
6. get_order_history returns the finished-orders feed for today.
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from broast_pos.core.models.order import (
    Order, OrderItem, OrderStatus, OrderType, PaymentMethod,
)
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.audit_service import AuditService


def _item(price: float = 100.0) -> OrderItem:
    return OrderItem(product_id=1, product_name="بروست", unit_price=price, quantity=1)


def _takeaway(order_id=7, status=OrderStatus.NEW, paid_at=None, created_at=None) -> Order:
    return Order(
        id=order_id,
        invoice_no=55,
        order_type=OrderType.TAKEAWAY,
        status=status,
        items=[_item(100.0)],
        subtotal=100.0,
        total=100.0,
        shift_id=1,
        paid_at=paid_at,
        created_at=created_at,
    )


def _svc():
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


def _ago(minutes: int) -> str:
    return (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).isoformat()


# ===========================================================================
# complete_order finalize flag
# ===========================================================================

class TestCompleteOrderFinalize:

    def test_keep_open_records_payment_but_stays_active(self):
        svc, repo = _svc()
        repo.get_by_id.return_value = _takeaway(status=OrderStatus.NEW)
        result = svc.complete_order(7, PaymentMethod.CASH, 100.0, finalize=False)
        assert result.is_paid is True
        assert result.status == OrderStatus.NEW, "keep-open must not close the order"

    def test_default_finalize_closes_order(self):
        svc, repo = _svc()
        repo.get_by_id.return_value = _takeaway(status=OrderStatus.NEW)
        result = svc.complete_order(7, PaymentMethod.CASH, 100.0)
        assert result.is_paid is True
        assert result.status == OrderStatus.COMPLETED


# ===========================================================================
# auto_complete_expired_takeaways
# ===========================================================================

class TestAutoCompleteTakeaways:

    def test_closes_expired_paid_takeaway(self):
        svc, repo = _svc()
        expired = _takeaway(order_id=7, paid_at=_ago(31))
        repo.get_active_by_type.return_value = [expired]
        closed = svc.auto_complete_expired_takeaways(minutes=30)
        assert closed == [7]
        assert expired.status == OrderStatus.COMPLETED
        repo.save.assert_called_once()

    def test_keeps_recent_takeaway(self):
        svc, repo = _svc()
        recent = _takeaway(order_id=8, paid_at=_ago(5))
        repo.get_active_by_type.return_value = [recent]
        closed = svc.auto_complete_expired_takeaways(minutes=30)
        assert closed == []
        assert recent.status == OrderStatus.NEW
        repo.save.assert_not_called()

    def test_falls_back_to_created_at_when_unpaid(self):
        svc, repo = _svc()
        old_unpaid = _takeaway(order_id=9, paid_at=None, created_at=_ago(45))
        repo.get_active_by_type.return_value = [old_unpaid]
        closed = svc.auto_complete_expired_takeaways(minutes=30)
        assert closed == [9]

    def test_only_queries_takeaway_type(self):
        svc, repo = _svc()
        repo.get_active_by_type.return_value = []
        svc.auto_complete_expired_takeaways(minutes=30)
        repo.get_active_by_type.assert_called_once_with(OrderType.TAKEAWAY)


# ===========================================================================
# get_order_history
# ===========================================================================

class TestOrderHistory:

    def test_returns_finished_feed_for_today(self):
        svc, repo = _svc()
        finished = [
            _takeaway(order_id=1, status=OrderStatus.COMPLETED),
            _takeaway(order_id=2, status=OrderStatus.CANCELLED),
        ]
        repo.get_finished_for_date.return_value = finished
        result = svc.get_order_history()
        assert result == finished
        # Defaults to today's date
        called_date = repo.get_finished_for_date.call_args[0][0]
        assert called_date == datetime.date.today().isoformat()
