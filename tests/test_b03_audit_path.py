"""
Tests for B-03 — Single Audit Path in OrderService.

Verifies:
1. _audit_svc is ALWAYS an AuditService — never None.
2. cancel_order() routes through AuditService (not AuditRepository directly).
3. apply_discount() routes through AuditService.
4. amend_order() item removal routes through AuditService.log_from_user().
5. Audit records contain correct before/after state.

Were RED before B-03 fix. Must remain GREEN after. All 16 baseline tests stay GREEN.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType, PaymentMethod
from broast_pos.core.models.user import User
from broast_pos.core.models.audit import AuditEventType
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.order_service import OrderService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_manager() -> User:
    return User(
        id=99,
        username="manager_test",
        display_name="Test Manager",
        role="manager",
        pin_hash="anything",
        cashier_slot=None,
    )


def _make_order(order_id: int = 1, status: OrderStatus = OrderStatus.NEW, total: float = 250.0) -> Order:
    o = Order(
        id=order_id,
        invoice_no=order_id,
        order_type=OrderType.TAKEAWAY,
        status=status,
        items=[OrderItem(product_id=10, product_name="تشيكن فرايز", unit_price=50.0, quantity=5)],
        subtotal=total,
        total=total,
        shift_id=1,
    )
    return o


def _build_service(audit_svc=None):
    order_repo = MagicMock()
    audit_repo = MagicMock()
    svc = OrderService(
        order_repo=order_repo,
        audit_repo=audit_repo,
        audit_service=audit_svc or AuditService(audit_repo),
    )
    return svc, order_repo, audit_repo


# ---------------------------------------------------------------------------
# B-03-a: _audit_svc always AuditService
# ---------------------------------------------------------------------------

class TestB03AuditSvcAlwaysInitialized:

    def test_audit_svc_initialized_without_injection(self):
        svc = OrderService()
        assert isinstance(svc._audit_svc, AuditService), \
            "B-03 violation: _audit_svc is None or wrong type when not injected"

    def test_audit_svc_uses_injected_instance(self):
        custom = AuditService()
        svc = OrderService(audit_service=custom)
        assert svc._audit_svc is custom

    def test_audit_svc_wraps_provided_repo(self):
        audit_repo = MagicMock()
        svc = OrderService(audit_repo=audit_repo)
        assert isinstance(svc._audit_svc, AuditService)
        assert svc._audit_svc._audit is audit_repo


# ---------------------------------------------------------------------------
# B-03-b: cancel_order audit path
# ---------------------------------------------------------------------------

class TestB03CancelOrderAuditPath:

    def test_cancel_uses_audit_svc_not_repo(self):
        """Verify OrderService routes through _audit_svc (not repo directly).

        We confirm this by checking AuditService.log is called. We cannot assert
        repo.log is *never* called because AuditService legitimately calls it.
        The key invariant: cancel_order must call _audit_svc.log, not _audit.log.
        """
        order = _make_order(status=OrderStatus.NEW)
        svc, order_repo, audit_repo = _build_service()
        manager = _make_manager()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=manager)

        # Replace _audit.log with a MagicMock that does NOT delegate to the real repo
        # This lets us detect if OrderService calls it DIRECTLY (bypassing the service)
        direct_audit_spy = MagicMock()
        svc._audit = direct_audit_spy  # Replace the underlying repo reference

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as svc_spy:
            svc.cancel_order(order.id, manager_pin="1234", reason="test")

        assert svc_spy.call_count == 1, "AuditService.log not called"
        # _audit.log must NOT have been called directly by OrderService
        # (AuditService._audit.log would not be svc._audit because we replaced it)
        assert direct_audit_spy.log.call_count == 0, \
            "OrderService called AuditRepository.log directly — bypassing AuditService"

    def test_cancel_event_type(self):
        order = _make_order(status=OrderStatus.PREPARING)
        svc, order_repo, _ = _build_service()
        manager = _make_manager()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=manager)

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.cancel_order(order.id, manager_pin="1234", reason="r")

        assert spy.call_args.kwargs["event_type"] == AuditEventType.ORDER_CANCELLED

    def test_cancel_before_has_original_status(self):
        order = _make_order(status=OrderStatus.PREPARING)
        svc, order_repo, _ = _build_service()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=_make_manager())

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.cancel_order(order.id, manager_pin="1234", reason="r")

        before = spy.call_args.kwargs.get("before", {})
        assert before.get("status") == OrderStatus.PREPARING.value

    def test_cancel_after_shows_cancelled(self):
        order = _make_order(status=OrderStatus.NEW)
        svc, order_repo, _ = _build_service()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=_make_manager())

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.cancel_order(order.id, manager_pin="1234", reason="r")

        after = spy.call_args.kwargs.get("after", {})
        assert after.get("status") == OrderStatus.CANCELLED.value

    def test_cancel_reason_stored_in_audit(self):
        order = _make_order()
        svc, order_repo, _ = _build_service()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=_make_manager())
        reason = "نسي العميل التأكيد"

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.cancel_order(order.id, manager_pin="1234", reason=reason)

        kw = spy.call_args.kwargs
        stored_reason = kw.get("reason") or (kw.get("details") or {}).get("reason")
        assert stored_reason == reason

    def test_cancel_actor_is_manager(self):
        order = _make_order()
        svc, order_repo, _ = _build_service()
        manager = _make_manager()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=manager)

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.cancel_order(order.id, manager_pin="1234", reason="r")

        kw = spy.call_args.kwargs
        assert kw["user_id"] == 99
        assert kw["user_name"] == "Test Manager"


# ---------------------------------------------------------------------------
# B-03-c: apply_discount audit path
# ---------------------------------------------------------------------------

class TestB03DiscountAuditPath:

    def _setup_discount(self, total=200.0):
        order = _make_order(total=total)
        svc, order_repo, audit_repo = _build_service()
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=_make_manager())
        return order, svc, audit_repo

    def test_discount_uses_audit_svc_not_repo(self):
        """Verify apply_discount routes through _audit_svc, not the repo directly."""
        order, svc, _audit_repo = self._setup_discount()

        # Replace the raw _audit repo reference on the service to detect direct calls
        direct_audit_spy = MagicMock()
        svc._audit = direct_audit_spy

        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as svc_spy:
            svc.apply_discount(order, value=50.0, discount_type="flat", manager_pin="1234")

        assert svc_spy.call_count == 1, "AuditService.log not called for discount"
        assert direct_audit_spy.log.call_count == 0, \
            "OrderService called AuditRepository.log directly — bypassing AuditService"

    def test_discount_event_type(self):
        order, svc, _ = self._setup_discount()
        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.apply_discount(order, value=30.0, discount_type="flat", manager_pin="1234")
        assert spy.call_args.kwargs["event_type"] == AuditEventType.DISCOUNT_APPLIED

    def test_discount_before_has_original_total(self):
        order, svc, _ = self._setup_discount(total=200.0)
        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.apply_discount(order, value=30.0, discount_type="flat", manager_pin="1234")
        before = spy.call_args.kwargs.get("before", {})
        assert before.get("total") == pytest.approx(200.0)

    def test_discount_after_reflects_new_total(self):
        order, svc, _ = self._setup_discount(total=200.0)
        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.apply_discount(order, value=50.0, discount_type="flat", manager_pin="1234")
        after = spy.call_args.kwargs.get("after", {})
        assert after.get("total") == pytest.approx(150.0)

    def test_percent_discount_after_has_amount(self):
        order, svc, _ = self._setup_discount(total=300.0)
        with patch.object(svc._audit_svc, "log", wraps=svc._audit_svc.log) as spy:
            svc.apply_discount(order, value=10.0, discount_type="percent", manager_pin="1234")
        after = spy.call_args.kwargs.get("after", {})
        assert after.get("discount_amount") == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# B-03-d: item removal audit path
# ---------------------------------------------------------------------------

class TestB03ItemRemovalAuditPath:

    def test_item_removal_uses_audit_svc(self):
        """Verify item removal routes through _audit_svc.log_from_user."""
        order = _make_order()
        removed = order.items[0]
        svc, order_repo, _audit_repo = _build_service()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=_make_manager())

        # Replace raw _audit repo to detect direct calls from OrderService
        direct_audit_spy = MagicMock()
        svc._audit = direct_audit_spy

        with patch.object(svc._audit_svc, "log_from_user", wraps=svc._audit_svc.log_from_user) as svc_spy:
            svc.amend_order(order.id, added_items=[], removed_items=[removed], manager_pin="1234")

        assert svc_spy.call_count == 1, "AuditService.log_from_user not called for item removal"
        assert direct_audit_spy.log.call_count == 0, \
            "OrderService called AuditRepository.log directly — bypassing AuditService"

    def test_item_removal_event_type(self):
        order = _make_order()
        removed = order.items[0]
        svc, order_repo, _ = _build_service()
        order_repo.get_by_id.return_value = order
        order_repo.save.side_effect = lambda o: o
        svc._verify_manager_pin = MagicMock(return_value=_make_manager())

        with patch.object(svc._audit_svc, "log_from_user", wraps=svc._audit_svc.log_from_user) as spy:
            svc.amend_order(order.id, [], [removed], "1234")

        assert spy.call_args.kwargs["event_type"] == AuditEventType.ITEM_REMOVED
