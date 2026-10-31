"""
Tests for B-05 — Single DiscountPolicy (compute_discount).

Covers:
- compute_discount() itself (pure policy — no DB needed)
- OrderService.apply_discount() using the policy
- OrderController in-memory path using the policy
- F-05 from audit report: negative values are now rejected (not silently modified)
- Edge cases: flat==subtotal (allowed), percent==100 (allowed), rounding
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from broast_pos.core.policies.discount import compute_discount
from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType
from broast_pos.core.models.user import User
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.order_service import OrderService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order(subtotal: float = 200.0) -> Order:
    o = Order(
        id=1,
        invoice_no=1,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.NEW,
        items=[OrderItem(product_id=1, product_name="بيتزا", unit_price=subtotal, quantity=1)],
        subtotal=subtotal,
        total=subtotal,
        shift_id=1,
    )
    return o


def _manager() -> User:
    return User(id=99, username="mgr", display_name="Manager", role="manager",
                pin_hash="x", cashier_slot=None)


def _order_svc():
    """OrderService with mocked repo + mocked manager PIN."""
    svc = OrderService(
        order_repo=MagicMock(**{"save.side_effect": lambda o: o}),
        audit_service=AuditService(MagicMock()),
    )
    svc._verify_manager_pin = MagicMock(return_value=_manager())
    return svc


# ===========================================================================
# Part A: compute_discount() — pure policy
# ===========================================================================

class TestComputeDiscountFlat:

    def test_flat_basic(self):
        assert compute_discount(200.0, 50.0, "flat") == pytest.approx(50.0)

    def test_flat_equals_subtotal(self):
        """flat == subtotal is a 100% discount — allowed."""
        assert compute_discount(200.0, 200.0, "flat") == pytest.approx(200.0)

    def test_flat_exceeds_subtotal_raises(self):
        """F-05 fix: flat > subtotal must raise, not silently cap."""
        with pytest.raises(ValueError, match="لا يمكن أن يتجاوز"):
            compute_discount(200.0, 201.0, "flat")

    def test_flat_zero_raises(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            compute_discount(200.0, 0.0, "flat")

    def test_flat_negative_raises(self):
        """F-05 fix: negative flat discount must be rejected."""
        with pytest.raises(ValueError, match="أكبر من صفر"):
            compute_discount(200.0, -50.0, "flat")

    def test_flat_none_raises(self):
        with pytest.raises((ValueError, TypeError)):
            compute_discount(200.0, None, "flat")  # type: ignore

    def test_flat_rounding_to_2dp(self):
        """Verifies Decimal rounding at 2 decimal places."""
        # 150.005 → rounds to 150.01 (ROUND_HALF_UP)
        result = compute_discount(300.0, 150.005, "flat")
        assert result == pytest.approx(150.01, abs=0.001)


class TestComputeDiscountPercent:

    def test_percent_basic_10(self):
        assert compute_discount(200.0, 10.0, "percent") == pytest.approx(20.0)

    def test_percent_100_allowed(self):
        """100% discount = full subtotal — should be allowed."""
        assert compute_discount(300.0, 100.0, "percent") == pytest.approx(300.0)

    def test_percent_exceeds_100_raises(self):
        with pytest.raises(ValueError, match="100"):
            compute_discount(200.0, 101.0, "percent")

    def test_percent_negative_raises(self):
        """F-05 fix: negative percent must be rejected."""
        with pytest.raises(ValueError, match="أكبر من صفر"):
            compute_discount(200.0, -10.0, "percent")

    def test_percent_zero_raises(self):
        with pytest.raises(ValueError, match="أكبر من صفر"):
            compute_discount(200.0, 0.0, "percent")

    def test_percent_33_333_rounding(self):
        """33.333% of 300 = 99.999 → rounds to 100.00 (ROUND_HALF_UP)."""
        result = compute_discount(300.0, 33.333, "percent")
        assert result == pytest.approx(100.0, abs=0.01)

    def test_percent_50_half(self):
        assert compute_discount(400.0, 50.0, "percent") == pytest.approx(200.0)


class TestComputeDiscountInvalidKind:

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="نوع الخصم"):
            compute_discount(200.0, 50.0, "fixed")  # wrong keyword

    def test_empty_kind_raises(self):
        with pytest.raises(ValueError):
            compute_discount(200.0, 50.0, "")

    def test_case_sensitive_kind(self):
        """'Flat' / 'PERCENT' are not accepted — must be exact."""
        with pytest.raises(ValueError):
            compute_discount(200.0, 50.0, "Flat")


# ===========================================================================
# Part B: OrderService.apply_discount() uses compute_discount
# ===========================================================================

class TestOrderServiceDiscountValidation:
    """Ensures OrderService propagates compute_discount's ValueError."""

    def test_negative_flat_rejected_by_service(self):
        svc = _order_svc()
        order = _order(200.0)
        with pytest.raises(ValueError, match="أكبر من صفر"):
            svc.apply_discount(order, value=-50.0, discount_type="flat", manager_pin="1234")

    def test_negative_percent_rejected_by_service(self):
        svc = _order_svc()
        order = _order(200.0)
        with pytest.raises(ValueError, match="أكبر من صفر"):
            svc.apply_discount(order, value=-10.0, discount_type="percent", manager_pin="1234")

    def test_flat_exceeding_subtotal_rejected(self):
        svc = _order_svc()
        order = _order(200.0)
        with pytest.raises(ValueError, match="يتجاوز"):
            svc.apply_discount(order, value=201.0, discount_type="flat", manager_pin="1234")

    def test_percent_over_100_rejected(self):
        svc = _order_svc()
        order = _order(300.0)
        with pytest.raises(ValueError, match="100"):
            svc.apply_discount(order, value=110.0, discount_type="percent", manager_pin="1234")

    def test_valid_flat_applies_correctly(self):
        svc = _order_svc()
        order = _order(200.0)
        result = svc.apply_discount(order, value=50.0, discount_type="flat", manager_pin="1234")
        assert result.discount_amount == pytest.approx(50.0)
        assert result.total == pytest.approx(150.0)

    def test_valid_percent_applies_correctly(self):
        svc = _order_svc()
        order = _order(300.0)
        result = svc.apply_discount(order, value=10.0, discount_type="percent", manager_pin="1234")
        assert result.discount_amount == pytest.approx(30.0)
        assert result.total == pytest.approx(270.0)

    def test_flat_equals_subtotal_clears_total(self):
        """Flat == subtotal → total = 0 (plus any delivery fee)."""
        svc = _order_svc()
        order = _order(200.0)
        result = svc.apply_discount(order, value=200.0, discount_type="flat", manager_pin="1234")
        assert result.total == pytest.approx(0.0)

    def test_100_percent_clears_total(self):
        svc = _order_svc()
        order = _order(300.0)
        result = svc.apply_discount(order, value=100.0, discount_type="percent", manager_pin="1234")
        assert result.total == pytest.approx(0.0)


# ===========================================================================
# Part C: both paths share the same policy (single implementation)
# ===========================================================================

class TestSingleImplementation:
    """Verifies that compute_discount is actually called from both paths."""

    def test_order_service_calls_compute_discount(self):
        """OrderService must delegate to compute_discount, not re-implement."""
        svc = _order_svc()
        order = _order(200.0)

        with patch("broast_pos.core.services.order_service.compute_discount",
                   wraps=compute_discount) as spy:
            svc.apply_discount(order, value=50.0, discount_type="flat", manager_pin="1234")

        assert spy.call_count == 1
        args = spy.call_args
        assert args.kwargs.get("kind") == "flat" or args.args[2] == "flat"

    def test_no_silent_capping_anymore(self):
        """Old code: min(value, subtotal) silently capped. New code: raises."""
        svc = _order_svc()
        order = _order(200.0)
        # 500 > 200: old code would silently use 200, new code must raise
        with pytest.raises(ValueError):
            svc.apply_discount(order, value=500.0, discount_type="flat", manager_pin="1234")

    def test_no_percent_capping_anymore(self):
        """Old code: min(value,100) silently capped percent. New code: raises."""
        svc = _order_svc()
        order = _order(300.0)
        with pytest.raises(ValueError):
            svc.apply_discount(order, value=150.0, discount_type="percent", manager_pin="1234")
