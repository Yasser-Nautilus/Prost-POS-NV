"""Distinct trip fees and paid/unpaid order-value reporting."""
from __future__ import annotations

from datetime import date

import pytest
from test_h16_report_scope import env as scope_env
from test_h16_report_scope import reset_db_singleton  # noqa: F401


@pytest.fixture
def env():
    return scope_env.__wrapped__()


def test_daily_fees_are_counted_once_per_trip_not_distinct_amount(env):
    ctrl, _, _ = env
    db = ctrl._report_svc._orders._db
    # Existing trip 1 has two orders and fee20; trip2 fee10. Add another
    # fee20 trip to rule out the incorrect SUM(DISTINCT fee) shortcut.
    db.execute("INSERT INTO delivery_trips (id,driver_id,driver_name,created_at,total_delivery_fees) VALUES (3,1,'سائق','2026-03-11 21:00:00',20)")
    db.commit()
    row = ctrl._report_svc.generate_driver_summary(date(2026, 3, 11))[0]
    assert row["fees_earned"] == 50  # 20+10+20, not 70 or 30
    assert row["trip_count"] == 3
    assert row["order_count"] == 3
    assert ctrl._report_svc.generate_driver_summary_for_shift(1)[0]["fees_earned"] == 20


def test_original_daily_fee_regression_50_becomes_30(env):
    ctrl, _, _ = env
    row = ctrl._report_svc.generate_driver_summary(date(2026, 3, 11))[0]
    assert row["fees_earned"] == 30
    assert row["trip_count"] == 2 and row["order_count"] == 3


def test_unpaid_cash_is_separate_in_day_and_shift_without_changing_booked_sales(env):
    ctrl, _, _ = env
    db = ctrl._report_svc._orders._db
    db.execute("UPDATE orders SET is_paid=0 WHERE id=5")  # cash delivery90
    db.commit()
    for report in [ctrl.generate_daily_summary(date(2026, 3, 11)), ctrl.generate_daily_summary(shift_id=2)]:
        payment = report["payment_breakdown"]
        by_method = {r["method"]: r["revenue"] for r in payment["payments"]}
        assert by_method["cash"] == 60
        assert by_method["unpaid"] == 90
        assert payment["unpaid_total"] == 90
        assert payment["total"] == sum(r["revenue"] for r in payment["payments"] if r["method"] != "unpaid")
        assert payment["basis"] == "order_created"
        assert report["gross_revenue"] == payment["total"] + payment["unpaid_total"]
    # Calendar day includes previous shift's post-midnight paid VISA150;
    # shift2 does not. Cancellation40 remains excluded in both.
    assert ctrl.get_payment_breakdown(date(2026, 3, 11))["total"] == 210
    assert ctrl.get_payment_breakdown(shift_id=2)["total"] == 60
