"""
Unit tests covering Critical Phase 1 bug fixes:
- C1: Unpaid takeaway auto-complete protection
- C4: Cancelled orders excluded from delivery trips & settlements
- C3: Settle trip atomicity & loud failures on missing session/actor
- C5: Paid order discount & amendment restrictions
- C6: Paid order cancellation books REVERSAL entry in ledger
"""
from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.cashier_session import CashLedgerEntry, LedgerEntryType
from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.driver_settlement_service import DriverSettlementService
from broast_pos.core.services.order_service import OrderService


def _order(order_id=1, status=OrderStatus.NEW, order_type=OrderType.TAKEAWAY, payment=PaymentMethod.CASH, is_paid=False, total=100.0, shift_id=1):
    return Order(
        id=order_id,
        invoice_no=10,
        order_type=order_type,
        status=status,
        items=[OrderItem(product_id=1, product_name="الوجبة", unit_price=total, quantity=1)],
        subtotal=total,
        total=total,
        payment_method=payment,
        is_paid=is_paid,
        shift_id=shift_id,
    )


class TestPhase1CriticalMoneyBugs:

    def test_c1_unpaid_takeaway_never_auto_completed(self):
        """C1: auto_complete_expired_takeaways must ignore unpaid orders."""
        order_repo = MagicMock()
        unpaid = _order(1, is_paid=False)
        unpaid.created_at = "2020-01-01T00:00:00"
        order_repo.get_active_by_type.return_value = [unpaid]

        svc = OrderService(order_repo=order_repo, audit_service=AuditService(MagicMock()))
        closed = svc.auto_complete_expired_takeaways(minutes=30)

        assert closed == []
        assert unpaid.status == OrderStatus.NEW
        order_repo.save.assert_not_called()

    def test_c5_apply_discount_blocked_on_paid_order(self):
        """C5: Applying discount on an already paid order must raise ValueError."""
        order_repo = MagicMock()
        paid = _order(2, is_paid=True)

        svc = OrderService(order_repo=order_repo, audit_service=AuditService(MagicMock()))
        with pytest.raises(ValueError, match="مدفوع"):
            svc.apply_discount(paid, value=10.0, discount_type="flat", manager_pin="1234")

    def test_c5_amend_order_blocked_when_out_for_delivery_or_delivered(self):
        """C5: amend_order must reject OUT_FOR_DELIVERY and DELIVERED orders."""
        order_repo = MagicMock()
        ofd = _order(3, status=OrderStatus.OUT_FOR_DELIVERY)
        deliv = _order(4, status=OrderStatus.DELIVERED)
        order_repo.get_by_id.side_effect = lambda oid: ofd if oid == 3 else deliv

        svc = OrderService(order_repo=order_repo, audit_service=AuditService(MagicMock()))
        with pytest.raises(ValueError, match="خارج للتوصيل|مكتمل|ملغي"):
            svc.amend_order(order_id=3, added_items=[], removed_items=[])

        with pytest.raises(ValueError, match="خارج للتوصيل|مكتمل|ملغي"):
            svc.amend_order(order_id=4, added_items=[], removed_items=[])

    def test_c6_cancel_paid_order_creates_reversal_entry(self):
        """C6: Cancelling a paid order creates a negative REVERSAL ledger entry."""
        order_repo = MagicMock()
        paid_order = _order(5, status=OrderStatus.READY, is_paid=True, total=150.0)
        order_repo.get_by_id.return_value = paid_order
        order_repo.save.side_effect = lambda o: o

        auth_svc = MagicMock()
        auth_svc.verify_manager_pin.return_value = MagicMock(id=9, display_name="مدير", username="mgr")

        ledger_repo = MagicMock()
        sale_entry = CashLedgerEntry(
            id=1, day_id=1, session_id=2, entry_type=LedgerEntryType.SALE_CASH,
            amount_pt=15000, order_id=5, actor_id=9
        )
        ledger_repo.get_entry_by_order.return_value = sale_entry

        svc = OrderService(
            order_repo=order_repo,
            auth_service=auth_svc,
            ledger_repo=ledger_repo,
            audit_service=AuditService(MagicMock()),
        )

        cancelled = svc.cancel_order(order_id=5, manager_pin="1234", reason="الزبون غير رأيه")
        assert cancelled.status == OrderStatus.CANCELLED

        ledger_repo.append.assert_called_once()
        rev_entry = ledger_repo.append.call_args[0][0]
        assert rev_entry.entry_type == LedgerEntryType.REVERSAL
        assert rev_entry.amount_pt == -15000
        assert rev_entry.order_id == 5

    def test_c3_remit_trip_cash_fails_loudly_without_actor_id(self):
        """C3: remit_trip_cash raises ValueError if actor_id == 0."""
        trip = MagicMock(id=1, order_ids=[1])
        ledger_repo = MagicMock()
        settle_svc = DriverSettlementService(ledger_repo=ledger_repo)

        with pytest.raises(ValueError, match="actor_id|مستخدم"):
            settle_svc.remit_trip_cash(trip=trip, trip_cash=200.0, actor_id=0)

    def test_c4_cancel_order_removes_from_unsettled_trip(self):
        """C4: cancel_order removes order from delivery_trip_orders."""
        order_repo = MagicMock()
        deliv_order = _order(6, order_type=OrderType.DELIVERY, status=OrderStatus.READY)
        order_repo.get_by_id.return_value = deliv_order
        order_repo.save.side_effect = lambda o: o

        auth_svc = MagicMock()
        auth_svc.verify_manager_pin.return_value = MagicMock(id=9, display_name="مدير")

        deliv_repo = MagicMock()
        deliv_trip = MagicMock(id=10, is_settled=False)
        deliv_repo.get_trip_for_order.return_value = deliv_trip

        svc = OrderService(
            order_repo=order_repo,
            auth_service=auth_svc,
            delivery_repo=deliv_repo,
            audit_service=AuditService(MagicMock()),
        )

        svc.cancel_order(order_id=6, manager_pin="1234", reason="الغاء")
        deliv_repo.remove_order_from_trip.assert_called_once_with(10, 6)
