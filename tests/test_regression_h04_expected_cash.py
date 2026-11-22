"""
Regression tests — H04: expected_cash formula.

Root cause:
  ShiftSummary.expected_cash subtracted pending_delivery + pending_dinein +
  pending_kitchen from cash_sales even though those amounts were never in
  cash_sales to begin with (all pending orders have is_paid=0).

  This caused the drawer balance shown to managers to be LOWER than reality
  whenever there were outstanding orders, making reconciliation impossible.

Fix verified:
  expected_cash = cash_sales - total_expenses
  Pending amounts are shown as "unpaid receivables" separately — not deducted.
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.financial import ShiftSummary


class TestH04ExpectedCash:

    def test_expected_cash_does_not_deduct_pending_delivery(self):
        """Unsettled delivery orders are receivables, not drawer deductions."""
        s = ShiftSummary(
            cash_sales=500.0,
            total_expenses=50.0,
            pending_delivery=100.0,   # driver cash in transit
            pending_dinein=0.0,
            pending_kitchen=0.0,
        )
        # Drawer should be 500 - 50 = 450, NOT 500 - 50 - 100 = 350
        assert s.expected_cash == pytest.approx(450.0), (
            f"expected_cash {s.expected_cash} deducts pending_delivery — it must not"
        )

    def test_expected_cash_does_not_deduct_pending_dinein(self):
        """Unpaid dine-in orders are receivables, not drawer deductions."""
        s = ShiftSummary(
            cash_sales=200.0,
            total_expenses=20.0,
            pending_delivery=0.0,
            pending_dinein=80.0,    # customers at tables haven't paid yet
            pending_kitchen=0.0,
        )
        assert s.expected_cash == pytest.approx(180.0), (
            f"expected_cash {s.expected_cash} deducts pending_dinein — it must not"
        )

    def test_expected_cash_does_not_deduct_pending_kitchen(self):
        """Orders being prepared are receivables, not drawer deductions."""
        s = ShiftSummary(
            cash_sales=300.0,
            total_expenses=30.0,
            pending_delivery=0.0,
            pending_dinein=0.0,
            pending_kitchen=60.0,   # food still being prepared
        )
        assert s.expected_cash == pytest.approx(270.0), (
            f"expected_cash {s.expected_cash} deducts pending_kitchen — it must not"
        )

    def test_expected_cash_formula_cash_minus_expenses(self):
        """expected_cash = cash_sales - total_expenses regardless of pending amounts."""
        s = ShiftSummary(
            cash_sales=1000.0,
            total_expenses=150.0,
            pending_delivery=200.0,
            pending_dinein=100.0,
            pending_kitchen=50.0,
        )
        assert s.expected_cash == pytest.approx(850.0), (
            f"expected_cash should be 850 (1000 - 150), got {s.expected_cash}"
        )

    def test_total_pending_still_accessible_separately(self):
        """Pending amounts remain available for display as unpaid receivables."""
        s = ShiftSummary(
            cash_sales=500.0,
            total_expenses=0.0,
            pending_delivery=100.0,
            pending_dinein=50.0,
            pending_kitchen=25.0,
        )
        assert s.total_pending == pytest.approx(175.0), (
            f"total_pending {s.total_pending} should still sum all pending fields"
        )
        assert s.expected_cash == pytest.approx(500.0), (
            f"expected_cash {s.expected_cash} should equal cash_sales when no expenses"
        )
