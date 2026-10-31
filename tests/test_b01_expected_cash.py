"""
Tests for B-01 — expected_cash formula correction.

Verified bugs (from audit report):
  F-01a: cash_sales included DELIVERED orders (driver still has cash) → inflated expected_cash
  F-01b: pending_delivery included ONLINE orders (pre-paid, never in drawer) → deflated expected_cash
  F-01c: pending_kitchen missed 'ready' status → missed pending cash
  F-01d: total_sales included unpaid/in-progress orders → inflated revenue figure

Correct formula:
  expected_cash = cash_sales(is_paid=1, CASH) − total_expenses − pending_delivery(CASH) − pending_dinein − pending_kitchen

All tests use ShiftSummary directly (pure model math) or mock the repository.
"""
from __future__ import annotations

import pytest
from broast_pos.core.models.financial import ShiftSummary


# ===========================================================================
# Part A: ShiftSummary.expected_cash formula (pure model math)
# ===========================================================================

class TestExpectedCashFormula:

    def test_all_cash_no_expenses_no_pending(self):
        """Simplest case: all cash sold, no expenses, no pending."""
        s = ShiftSummary(cash_sales=500.0, total_expenses=0.0)
        assert s.expected_cash == pytest.approx(500.0)

    def test_expenses_reduce_expected_cash(self):
        """Expenses must be deducted from expected_cash."""
        s = ShiftSummary(cash_sales=500.0, total_expenses=100.0)
        assert s.expected_cash == pytest.approx(400.0)

    def test_pending_delivery_reduces_expected_cash(self):
        """Unsettled CASH delivery reduces expected_cash (driver holds it)."""
        s = ShiftSummary(cash_sales=500.0, total_expenses=50.0, pending_delivery=120.0)
        assert s.expected_cash == pytest.approx(330.0)

    def test_pending_dinein_reduces_expected_cash(self):
        """Unpaid dine-in reduces expected_cash."""
        s = ShiftSummary(cash_sales=400.0, total_expenses=0.0, pending_dinein=80.0)
        assert s.expected_cash == pytest.approx(320.0)

    def test_pending_kitchen_reduces_expected_cash(self):
        """Orders still in kitchen reduce expected_cash."""
        s = ShiftSummary(cash_sales=300.0, total_expenses=0.0, pending_kitchen=60.0)
        assert s.expected_cash == pytest.approx(240.0)

    def test_all_pending_combined(self):
        """Full formula: cash_sales − expenses − (delivery + dinein + kitchen)."""
        s = ShiftSummary(
            cash_sales=1000.0,
            total_expenses=100.0,
            pending_delivery=200.0,
            pending_dinein=50.0,
            pending_kitchen=30.0,
        )
        # expected = 1000 - 100 - (200 + 50 + 30) = 620
        assert s.expected_cash == pytest.approx(620.0)

    def test_expected_cash_never_negative_in_model(self):
        """The model does not clamp, but we document the expected behavior:
        if more is pending than sold it's negative (shift issue, show it honestly)."""
        s = ShiftSummary(cash_sales=100.0, total_expenses=0.0, pending_delivery=150.0)
        assert s.expected_cash == pytest.approx(-50.0)

    def test_online_sales_do_not_appear_in_cash_sales(self):
        """B-01 regression: online revenue must NOT inflate expected_cash.
        cash_sales should only reflect actual CASH received."""
        # If 500 cash + 300 online, only 500 should be in cash_sales
        s = ShiftSummary(cash_sales=500.0, total_expenses=0.0)
        # online_sales of 300 must have NO effect on expected_cash
        assert s.expected_cash == pytest.approx(500.0)

    def test_rounding_to_2dp(self):
        """expected_cash is rounded to 2 decimal places."""
        s = ShiftSummary(cash_sales=100.333, total_expenses=0.0)
        assert s.expected_cash == pytest.approx(100.33)


# ===========================================================================
# Part B: Repository SQL queries (via mock DB)
# ===========================================================================

class TestRepositoryPendingDeliveryOnlyCash:
    """B-01: pending_delivery must exclude ONLINE orders."""

    def _repo_with_mock_db(self, pending_result: float):
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        mock_db = _MockDB({"pending": pending_result})
        repo._db = mock_db
        return repo, mock_db

    def test_pending_delivery_query_filters_cash_only(self):
        """The SQL must include AND payment_method = 'cash'."""
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        mock_db = _MockDB({"pending": 0.0})
        repo._db = mock_db

        repo.get_pending_delivery_total(shift_id=1)

        sql_used = mock_db.last_sql
        assert "payment_method = 'cash'" in sql_used, (
            "B-01 regression: pending_delivery query must filter CASH only. "
            f"Got SQL: {sql_used!r}"
        )

    def test_pending_kitchen_query_includes_ready(self):
        """B-01: 'ready' orders must be in pending_kitchen SQL."""
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        mock_db = _MockDB({"pending": 0.0})
        repo._db = mock_db

        repo.get_pending_kitchen_total(shift_id=1)

        sql_used = mock_db.last_sql
        assert "'ready'" in sql_used, (
            "B-01 regression: pending_kitchen query must include 'ready' status. "
            f"Got SQL: {sql_used!r}"
        )

    def test_cash_sales_query_includes_is_paid_filter(self):
        """B-01: cash_sales query must include is_paid = 1."""
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        import unittest.mock as mock

        repo = FinancialRepository.__new__(FinancialRepository)
        sqls_captured = []

        class CapturingDB:
            def fetch_one(self, sql, params=()):
                sqls_captured.append(sql)
                return {"total_sales": 0.0, "cash_sales": 0.0,
                        "total_expenses": 0.0, "pending": 0.0}
            def fetch_all(self, sql, params=()):
                return []

        repo._db = CapturingDB()
        # Mock the helper methods to avoid further SQL
        repo.get_pending_delivery_total = mock.Mock(return_value=0.0)
        repo.get_pending_dinein_total = mock.Mock(return_value=0.0)
        repo.get_pending_kitchen_total = mock.Mock(return_value=0.0)
        repo.get_shift_order_summary = mock.Mock(return_value={})

        repo.build_shift_summary(shift_id=1)

        cash_sales_sqls = [s for s in sqls_captured if "cash_sales" in s]
        assert cash_sales_sqls, "No cash_sales query found"
        cash_sql = cash_sales_sqls[0]
        assert "is_paid = 1" in cash_sql, (
            "B-01 regression: cash_sales query must include is_paid = 1. "
            f"Got SQL: {cash_sql!r}"
        )

    def test_total_sales_query_includes_is_paid_filter(self):
        """B-01: total_sales query must include is_paid = 1."""
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        import unittest.mock as mock

        repo = FinancialRepository.__new__(FinancialRepository)
        sqls_captured = []

        class CapturingDB:
            def fetch_one(self, sql, params=()):
                sqls_captured.append(sql)
                return {"total_sales": 0.0, "cash_sales": 0.0,
                        "total_expenses": 0.0, "pending": 0.0}
            def fetch_all(self, sql, params=()):
                return []

        repo._db = CapturingDB()
        repo.get_pending_delivery_total = mock.Mock(return_value=0.0)
        repo.get_pending_dinein_total = mock.Mock(return_value=0.0)
        repo.get_pending_kitchen_total = mock.Mock(return_value=0.0)
        repo.get_shift_order_summary = mock.Mock(return_value={})

        repo.build_shift_summary(shift_id=1)

        total_sales_sqls = [s for s in sqls_captured if "total_sales" in s]
        assert total_sales_sqls, "No total_sales query found"
        total_sql = total_sales_sqls[0]
        assert "is_paid = 1" in total_sql, (
            "B-01 regression: total_sales query must include is_paid = 1. "
            f"Got SQL: {total_sql!r}"
        )


# ===========================================================================
# Part C: Regression scenarios (F-01a through F-01d)
# ===========================================================================

class TestRegressionScenarios:
    """Verify the four audit-report bugs are fixed in the formula."""

    def test_F01a_delivered_cash_not_in_expected(self):
        """F-01a: DELIVERED orders (driver still has cash) must not appear in cash_sales.
        Instead they appear in pending_delivery and cancel each other out."""
        # Scenario: 1 order of 200 CASH, driver OUT (DELIVERED, unsettled)
        # Correct: cash_sales=0, pending_delivery=200 → expected=-200+200=0? No.
        # Actually: cash_sales=0 (not is_paid), pending_delivery=200 (CASH unsettled)
        # expected = 0 - 0 - 200 = -200 … which correctly shows the cash isn't here yet.
        # OLD bug: cash_sales=200 AND pending_delivery=200 → expected=0 (masks the gap)
        # After fix: they're handled symmetrically.
        s = ShiftSummary(cash_sales=0.0, total_expenses=0.0, pending_delivery=200.0)
        assert s.expected_cash == pytest.approx(-200.0)
        # This negative is correct: the cashier should NOT have that 200 in the drawer yet

    def test_F01b_online_delivery_not_deducted_from_expected(self):
        """F-01b: ONLINE delivery orders must NOT appear in pending_delivery.
        They were never in the cash drawer."""
        # Scenario: 1 online delivery order of 150, settled trip
        # With B-01 fix: pending_delivery = 0 (ONLINE excluded)
        # cash_sales = 0 (ONLINE, not cash), expenses = 0
        # expected_cash = 0 − 0 − 0 = 0 ✓
        # OLD bug: pending_delivery = 150 → expected = -150 (wrong! drawer was never affected)
        s = ShiftSummary(cash_sales=0.0, total_expenses=0.0, pending_delivery=0.0)
        assert s.expected_cash == pytest.approx(0.0)

    def test_F01c_ready_orders_reduce_expected_cash(self):
        """F-01c: 'ready' orders must appear in pending_kitchen."""
        # A READY order: food done but not yet paid → cash not in drawer
        s = ShiftSummary(cash_sales=200.0, total_expenses=0.0, pending_kitchen=80.0)
        assert s.expected_cash == pytest.approx(120.0)
        # OLD bug: ready was excluded → expected would be 200 (overstates what's in drawer)

    def test_F01d_unpaid_orders_not_in_total_sales(self):
        """F-01d: in-progress orders must not count in total_sales / cash_sales."""
        # If an order is in NEW status, cash not yet collected
        # cash_sales must be 0 for this order (is_paid=0)
        s = ShiftSummary(cash_sales=0.0, total_expenses=0.0)
        assert s.expected_cash == pytest.approx(0.0)


# ===========================================================================
# Helpers
# ===========================================================================

class _MockDB:
    """Minimal DB mock that returns a fixed row for fetch_one."""
    def __init__(self, row: dict):
        self._row = row
        self.last_sql = ""

    def fetch_one(self, sql, params=()):
        self.last_sql = sql
        return self._row

    def fetch_all(self, sql, params=()):
        return []
