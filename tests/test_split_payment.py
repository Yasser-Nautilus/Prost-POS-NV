# ruff: noqa: F811
"""Mixed payment / split bill: money must land in the right buckets."""
from __future__ import annotations

import pytest
from test_regression_h01_cash_posting import (  # noqa: F401
    _fresh_db,
    _make_svc,
    _open_session,
    _reset_singleton,
    _saved_order,
)

from broast_pos.core.models.cashier_session import LedgerEntryType
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository


def _setup(total=100.0):
    db = _fresh_db()
    sid = _open_session(db, user_id=1, float_egp=0.0)
    svc = _make_svc(db)
    order = _saved_order(db, total=total)
    return db, sid, svc, order


def test_cash_plus_visa_posts_only_the_cash_share_to_the_drawer():
    db, sid, svc, order = _setup(100.0)
    done = svc.complete_order_split(
        order.id, [{"method": "cash", "amount": 40}, {"method": "visa", "amount": 60}],
        actor_id=1)
    assert done.is_paid and done.status.value == "completed"
    assert CashLedgerRepository(db=db).get_session_balance_pt(sid) == 4000
    rows = db.fetch_all("SELECT amount_pt FROM cash_ledger WHERE entry_type=?",
                        (LedgerEntryType.SALE_CASH.value,))
    assert [r["amount_pt"] for r in rows] == [4000]
    assert svc.get_payment_parts(order.id) == [
        {"method": "cash", "amount": 40.0}, {"method": "visa", "amount": 60.0}]


def test_change_is_computed_on_the_cash_share_only():
    db, sid, svc, order = _setup(100.0)
    done = svc.complete_order_split(
        order.id, [{"method": "cash", "amount": 30}, {"method": "online", "amount": 70}],
        cash_received=50, actor_id=1)
    assert done.change_given == 20.0
    assert CashLedgerRepository(db=db).get_session_balance_pt(sid) == 3000


def test_shift_cash_sales_counts_only_cash_share():
    db, sid, svc, order = _setup(100.0)
    svc.complete_order_split(
        order.id, [{"method": "cash", "amount": 25}, {"method": "visa", "amount": 75}],
        actor_id=1)
    summary = FinancialRepository(db=db).get_shift_summary(1)
    assert summary.cash_sales == 25.0


@pytest.mark.parametrize("parts", [
    [{"method": "cash", "amount": 40}, {"method": "visa", "amount": 50}],    # short
    [{"method": "cash", "amount": 60}, {"method": "visa", "amount": 50}],    # over
    [{"method": "cash", "amount": 0}, {"method": "visa", "amount": 100}],    # zero part
    [{"method": "bitcoin", "amount": 100}],                                  # bad method
    [],
])
def test_bad_splits_are_rejected_and_nothing_is_written(parts):
    db, sid, svc, order = _setup(100.0)
    with pytest.raises(ValueError):
        svc.complete_order_split(order.id, parts, actor_id=1)
    assert svc.get_payment_parts(order.id) == []
    assert db.fetch_one("SELECT is_paid FROM orders WHERE id=?", (order.id,))["is_paid"] == 0
    assert CashLedgerRepository(db=db).get_session_balance_pt(sid) == 0


def test_cannot_pay_twice_or_underpay_cash():
    db, sid, svc, order = _setup(100.0)
    with pytest.raises(ValueError):
        svc.complete_order_split(
            order.id, [{"method": "cash", "amount": 50}, {"method": "visa", "amount": 50}],
            cash_received=40, actor_id=1)
    svc.complete_order_split(
        order.id, [{"method": "cash", "amount": 50}, {"method": "visa", "amount": 50}],
        actor_id=1)
    with pytest.raises(ValueError):
        svc.complete_order_split(order.id, [{"method": "visa", "amount": 100}], actor_id=1)
    assert len(svc.get_payment_parts(order.id)) == 2


def test_sale_ledger_entry_is_the_cash_share_so_a_refund_reverses_only_that():
    db, sid, svc, order = _setup(100.0)
    svc.complete_order_split(
        order.id, [{"method": "cash", "amount": 40}, {"method": "visa", "amount": 60}],
        actor_id=1)
    sale = CashLedgerRepository(db=db).get_entry_by_order(order.id, LedgerEntryType.SALE_CASH)
    assert sale.amount_pt == 4000


def test_payment_breakdown_report_splits_a_mixed_order_by_method():
    from broast_pos.core.services.report_service import ReportService
    db, sid, svc, order = _setup(100.0)
    svc.complete_order_split(
        order.id, [{"method": "cash", "amount": 40}, {"method": "visa", "amount": 60}],
        actor_id=1)
    from broast_pos.data.repositories.order_repository import OrderRepository
    rep = ReportService(order_repo=OrderRepository(db=db)).generate_payment_breakdown()
    got = {p["method"]: p["revenue"] for p in rep["payments"]}
    assert got == {"cash": 40.0, "visa": 60.0}
    assert rep["total"] == 100.0
