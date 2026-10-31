"""
Tests for B-10 — Time + Shift-Based Reports.

Core problem (before B-10):
  Date-based reports use DATE(created_at).
  A restaurant that works past midnight places orders on two different
  calendar dates, yet they belong to the SAME shift. Reports were wrong.

Fix:
  Shift-based variants (generate_*_for_shift) filter by shift_id.
  Business date = DATE(shifts.opened_at).

Tests verify:
  - Shift-based methods exist on ReportService
  - They call the shift-keyed repository methods (shift_id, NOT created_at)
  - Business date is derived from shift opened_at, not wall clock
  - Orders at 23:55 and 00:05 in the SAME shift are both included
  - Orders from a DIFFERENT shift are excluded even if same calendar date
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call
from datetime import date

from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType, PaymentMethod
from broast_pos.core.services.report_service import ReportService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order(
    order_id: int,
    order_type: OrderType = OrderType.TAKEAWAY,
    status: OrderStatus = OrderStatus.COMPLETED,
    payment: PaymentMethod = PaymentMethod.CASH,
    total: float = 100.0,
    shift_id: int = 1,
    created_at: str = "2026-10-04T22:00:00",
) -> Order:
    return Order(
        id=order_id,
        invoice_no=order_id,
        order_type=order_type,
        status=status,
        items=[OrderItem(product_id=1, product_name="بروست", unit_price=total, quantity=1)],
        subtotal=total,
        total=total,
        payment_method=payment,
        shift_id=shift_id,
        created_at=created_at,
    )


def _report_svc(orders_by_shift=None, cancelled_by_shift=None, product_sales_by_shift=None,
                business_dates=None):
    """Build ReportService with mocked repos."""
    order_repo = MagicMock()
    order_repo.get_completed_for_shift.side_effect = lambda sid: (orders_by_shift or {}).get(sid, [])
    order_repo.get_cancelled_for_shift.side_effect = lambda sid: (cancelled_by_shift or {}).get(sid, [])
    order_repo.get_product_sales_for_shift.side_effect = lambda sid: (product_sales_by_shift or {}).get(sid, [])
    order_repo.get_daily_revenue_for_shift.side_effect = lambda sid: sum(
        o.total for o in (orders_by_shift or {}).get(sid, []) if o.status != OrderStatus.CANCELLED
    )
    order_repo.get_shift_business_date.side_effect = lambda sid: (business_dates or {}).get(sid, "2026-10-04")

    fin_repo = MagicMock()
    delivery_repo = MagicMock()
    delivery_repo.get_daily_summary.return_value = []

    svc = ReportService(
        order_repo=order_repo,
        financial_repo=fin_repo,
        delivery_repo=delivery_repo,
    )
    return svc, order_repo


# ===========================================================================
# Part A: Shift-based methods exist
# ===========================================================================

class TestShiftBasedMethodsExist:

    def test_generate_daily_sales_for_shift_exists(self):
        svc, _ = _report_svc()
        assert hasattr(svc, "generate_daily_sales_for_shift")

    def test_generate_payment_breakdown_for_shift_exists(self):
        svc, _ = _report_svc()
        assert hasattr(svc, "generate_payment_breakdown_for_shift")

    def test_generate_cancellations_for_shift_exists(self):
        svc, _ = _report_svc()
        assert hasattr(svc, "generate_cancellations_for_shift")

    def test_generate_product_sales_for_shift_exists(self):
        svc, _ = _report_svc()
        assert hasattr(svc, "generate_product_sales_for_shift")

    def test_generate_shift_revenue_exists(self):
        svc, _ = _report_svc()
        assert hasattr(svc, "generate_shift_revenue")


# ===========================================================================
# Part B: Methods use shift_id, not DATE(created_at)
# ===========================================================================

class TestShiftIdUsed:

    def test_sales_calls_get_completed_for_shift(self):
        """generate_daily_sales_for_shift must use get_completed_for_shift(shift_id)."""
        svc, order_repo = _report_svc()
        svc.generate_daily_sales_for_shift(shift_id=42)
        order_repo.get_completed_for_shift.assert_called_once_with(42)

    def test_cancellations_calls_get_cancelled_for_shift(self):
        svc, order_repo = _report_svc()
        svc.generate_cancellations_for_shift(shift_id=7)
        order_repo.get_cancelled_for_shift.assert_called_once_with(7)

    def test_product_sales_calls_get_product_sales_for_shift(self):
        svc, order_repo = _report_svc()
        svc.generate_product_sales_for_shift(shift_id=3)
        order_repo.get_product_sales_for_shift.assert_called_once_with(3)

    def test_business_date_derived_from_shift_opened_at(self):
        """Business date must come from get_shift_business_date(), not date.today()."""
        svc, order_repo = _report_svc(business_dates={5: "2026-10-03"})
        result = svc.generate_daily_sales_for_shift(shift_id=5)
        assert result["date"] == "2026-10-03"
        order_repo.get_shift_business_date.assert_called_once_with(5)


# ===========================================================================
# Part C: Midnight-spanning shift correctness
# ===========================================================================

class TestMidnightSpanning:

    def test_orders_before_and_after_midnight_both_in_same_shift(self):
        """An order at 23:55 and one at 00:05 same shift must both appear."""
        late_order = _order(1, created_at="2026-10-04T23:55:00", shift_id=1, total=120.0)
        early_order = _order(2, created_at="2026-10-05T00:05:00", shift_id=1, total=80.0)

        svc, _ = _report_svc(
            orders_by_shift={1: [late_order, early_order]},
            business_dates={1: "2026-10-04"},
        )
        result = svc.generate_daily_sales_for_shift(shift_id=1)

        # Both orders must be in the total regardless of their created_at date
        assert result["grand_total"]["count"] == 2
        assert result["grand_total"]["revenue"] == pytest.approx(200.0)
        assert result["date"] == "2026-10-04"  # business date = shift opened_at date

    def test_orders_from_different_shifts_excluded(self):
        """Orders from shift 2 must NOT appear in shift 1's report."""
        shift1_order = _order(1, shift_id=1, total=100.0)
        shift2_order = _order(2, shift_id=2, total=200.0)

        # Shift 1 repo returns only shift1_order
        svc, _ = _report_svc(orders_by_shift={1: [shift1_order], 2: [shift2_order]})
        result = svc.generate_daily_sales_for_shift(shift_id=1)

        # Only shift 1 order appears
        assert result["grand_total"]["count"] == 1
        assert result["grand_total"]["revenue"] == pytest.approx(100.0)

    def test_two_shifts_same_calendar_date_independent(self):
        """Two shifts on the same day must produce independent reports."""
        shift1_orders = [_order(1, shift_id=1, total=500.0)]
        shift2_orders = [_order(2, shift_id=2, total=300.0)]

        svc, _ = _report_svc(
            orders_by_shift={1: shift1_orders, 2: shift2_orders},
            business_dates={1: "2026-10-04", 2: "2026-10-04"},
        )
        r1 = svc.generate_daily_sales_for_shift(shift_id=1)
        r2 = svc.generate_daily_sales_for_shift(shift_id=2)

        assert r1["grand_total"]["revenue"] == pytest.approx(500.0)
        assert r2["grand_total"]["revenue"] == pytest.approx(300.0)


# ===========================================================================
# Part D: Output structure
# ===========================================================================

class TestOutputStructure:

    def test_daily_sales_includes_shift_id(self):
        svc, _ = _report_svc()
        result = svc.generate_daily_sales_for_shift(shift_id=99)
        assert "shift_id" in result
        assert result["shift_id"] == 99

    def test_daily_sales_empty_shift(self):
        svc, _ = _report_svc(orders_by_shift={1: []})
        result = svc.generate_daily_sales_for_shift(shift_id=1)
        assert result["grand_total"]["count"] == 0
        assert result["grand_total"]["revenue"] == 0.0
        assert result["breakdown"] == []

    def test_payment_breakdown_groups_by_method(self):
        orders = [
            _order(1, payment=PaymentMethod.CASH, total=100.0),
            _order(2, payment=PaymentMethod.CASH, total=50.0),
            _order(3, payment=PaymentMethod.ONLINE, total=200.0),
        ]
        svc, _ = _report_svc(orders_by_shift={1: orders})
        result = svc.generate_payment_breakdown_for_shift(shift_id=1)

        assert result["total"] == pytest.approx(350.0)
        methods = {p["method"]: p["revenue"] for p in result["payments"]}
        assert methods.get("cash") == pytest.approx(150.0)
        assert methods.get("online") == pytest.approx(200.0)

    def test_cancellations_structure(self):
        cancelled = _order(5, status=OrderStatus.CANCELLED, total=75.0)
        cancelled.cancel_reason = "طلب العميل"
        cancelled.cancelled_by_name = "أمين"
        svc, _ = _report_svc(cancelled_by_shift={1: [cancelled]})
        result = svc.generate_cancellations_for_shift(shift_id=1)

        assert result["count"] == 1
        assert result["orders"][0]["total"] == pytest.approx(75.0)
        assert result["orders"][0]["reason"] == "طلب العميل"

    def test_shift_revenue_returns_float(self):
        orders = [_order(1, total=120.0), _order(2, total=80.0)]
        svc, _ = _report_svc(orders_by_shift={1: orders})
        revenue = svc.generate_shift_revenue(shift_id=1)
        assert revenue == pytest.approx(200.0)


# ===========================================================================
# Part E: Repository SQL query correctness (B-10)
# ===========================================================================

class TestRepositoryShiftQueries:

    def test_get_completed_for_shift_uses_shift_id_not_date(self):
        """get_completed_for_shift SQL must filter by shift_id."""
        from broast_pos.data.repositories.order_repository import OrderRepository
        repo = OrderRepository.__new__(OrderRepository)
        captured = []

        class CapDB:
            def fetch_all(self, sql, params=()):
                captured.append((sql, params))
                return []
            def fetch_one(self, sql, params=()):
                return None

        repo._db = CapDB()
        repo.get_completed_for_shift(shift_id=7)

        assert captured, "must query the DB"
        sql, params = captured[0]
        assert "shift_id" in sql, f"Expected shift_id filter. Got: {sql!r}"
        assert "DATE(created_at)" not in sql, f"Must NOT use DATE(created_at). Got: {sql!r}"
        assert 7 in params

    def test_get_product_sales_for_shift_uses_shift_id(self):
        from broast_pos.data.repositories.order_repository import OrderRepository
        repo = OrderRepository.__new__(OrderRepository)
        captured = []

        class CapDB:
            def fetch_all(self, sql, params=()):
                captured.append((sql, params))
                return []

        repo._db = CapDB()
        repo.get_product_sales_for_shift(shift_id=3)

        assert captured
        sql, params = captured[0]
        assert "shift_id" in sql
        assert "DATE(created_at)" not in sql
        assert 3 in params

    def test_get_shift_business_date_uses_opened_at(self):
        from broast_pos.data.repositories.order_repository import OrderRepository
        repo = OrderRepository.__new__(OrderRepository)
        captured = []

        class CapDB:
            def fetch_one(self, sql, params=()):
                captured.append(sql)
                return {"business_date": "2026-10-04"}

        repo._db = CapDB()
        result = repo.get_shift_business_date(shift_id=1)

        assert result == "2026-10-04"
        assert captured
        sql = captured[0]
        assert "opened_at" in sql, f"Must use opened_at for business date. Got: {sql!r}"

    def test_get_daily_revenue_for_shift_uses_is_paid(self):
        """Revenue query must only count is_paid=1 orders."""
        from broast_pos.data.repositories.order_repository import OrderRepository
        repo = OrderRepository.__new__(OrderRepository)
        captured = []

        class CapDB:
            def fetch_one(self, sql, params=()):
                captured.append(sql)
                return {"revenue": 0.0}

        repo._db = CapDB()
        repo.get_daily_revenue_for_shift(shift_id=1)

        assert captured
        sql = captured[0]
        assert "is_paid = 1" in sql, f"Must filter is_paid=1. Got: {sql!r}"
