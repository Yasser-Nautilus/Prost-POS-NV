"""
Tests for FIN-001 — cash_sales separated from total_sales in ShiftSummary.

These tests verify that expected_cash uses cash_sales (not total_sales) so
Visa/online orders do not inflate the drawer reconciliation figure.
"""
import pytest
from broast_pos.core.models.financial import ShiftSummary


class TestShiftSummaryExpectedCash:

    def test_expected_cash_uses_cash_sales_not_total_sales(self):
        """Core invariant: expected_cash must be derived from cash_sales."""
        s = ShiftSummary(
            total_sales=1000.0,   # includes 400 Visa
            cash_sales=600.0,     # cash only
            total_expenses=50.0,
            pending_delivery=0.0,
            pending_dinein=0.0,
            pending_kitchen=0.0,
        )
        # correct: 600 - 50 = 550
        assert s.expected_cash == pytest.approx(550.0)
        # must NOT equal the old wrong formula: 1000 - 50 = 950
        assert s.expected_cash != pytest.approx(950.0)

    def test_all_visa_shift_produces_zero_expected_cash(self):
        """All Visa orders → cash_sales=0 → expected_cash reflects only expenses."""
        s = ShiftSummary(
            total_sales=500.0,
            cash_sales=0.0,
            total_expenses=30.0,
            pending_delivery=0.0,
            pending_dinein=0.0,
            pending_kitchen=0.0,
        )
        assert s.expected_cash == pytest.approx(-30.0)

    def test_all_cash_shift_matches_legacy_formula(self):
        """When all orders are cash, cash_sales == total_sales → same result."""
        s = ShiftSummary(
            total_sales=800.0,
            cash_sales=800.0,
            total_expenses=100.0,
            pending_delivery=50.0,
            pending_dinein=0.0,
            pending_kitchen=0.0,
        )
        assert s.expected_cash == pytest.approx(650.0)

    def test_mixed_payment_shift(self):
        """Realistic mixed shift: some cash, some Visa, some pending."""
        s = ShiftSummary(
            total_sales=2000.0,
            cash_sales=1400.0,   # 600 was Visa
            total_expenses=200.0,
            pending_delivery=100.0,
            pending_dinein=50.0,
            pending_kitchen=0.0,
        )
        # 1400 - 200 - (100 + 50) = 1050
        assert s.expected_cash == pytest.approx(1050.0)

    def test_total_sales_preserved_for_reporting(self):
        """total_sales must remain unchanged — it's used for revenue reporting."""
        s = ShiftSummary(total_sales=999.0, cash_sales=500.0)
        assert s.total_sales == pytest.approx(999.0)
