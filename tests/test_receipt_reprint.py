# ruff: noqa: F811
"""Receipt copies are repeatable, audited, and financially read-only."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from test_batch_workflow_e2e import _setup
from test_driver_business_day import _call
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401
from test_regression_h15_print_success_accuracy import _FakePrinter, _order

from broast_pos.infrastructure.printing import receipt_templates as tpl


def _saved(c):
    _call(c, "new_order", {"order_type": "takeaway"})
    _call(c, "add_item", {"product_id": 1})
    return _call(c, "confirm_order")["order_id"]


@pytest.mark.parametrize("status,paid", [("new", 0), ("preparing", 0), ("ready", 0), ("delivered", 1), ("out_for_delivery", 0), ("completed", 1), ("cancelled", 0)])
def test_reprint_any_state_repeated_and_no_financial_mutation(qapp, status, paid):
    c, db, _, _ = _setup(qapp)
    oid = _saved(c)
    db.execute("UPDATE orders SET status=?,is_paid=?,created_at='2024-01-02 12:00:00' WHERE id=?", (status, paid, oid))
    db.commit()
    tables = ["orders", "order_items", "cash_ledger", "order_payments", "order_status_history"]
    before = {t: [tuple(r) for r in db.fetch_all(f"SELECT * FROM {t}")] for t in tables}
    pm = c.bridge._printer
    pm.print_receipt.reset_mock()
    for _ in range(3):
        assert _call(c, "reprint_receipt", {"order_id": oid}) == {"printed": True}
    assert pm.print_receipt.call_count == 3
    data, slot = pm.print_receipt.call_args.args
    assert data["is_copy"] and data["is_paid"] == bool(paid)
    assert data["status"] == status and data["created_at"].startswith("2024-01-02")
    assert slot == 1
    assert before == {t: [tuple(r) for r in db.fetch_all(f"SELECT * FROM {t}")] for t in tables}
    logs = db.fetch_all("SELECT * FROM audit_log WHERE event_type='receipt_reprinted'")
    assert len(logs) == 3
    assert all(r["order_id"] == oid and r["user_name"] == "سارة" for r in logs)
    assert all(json.loads(r["details"])["printed"] for r in logs)


@pytest.mark.parametrize("raises", [False, True])
def test_failure_is_visible_audited_and_retryable(qapp, raises):
    c, db, _, _ = _setup(qapp)
    oid = _saved(c)
    c.bridge._printer.print_receipt = MagicMock(side_effect=RuntimeError("offline")) if raises else MagicMock(return_value=False)
    result = c.call("reprint_receipt", {"order_id": oid})
    assert not result["success"] and "الطابعة" in result["error"]
    row = db.fetch_one("SELECT * FROM audit_log WHERE event_type='receipt_reprinted'")
    assert not json.loads(row["details"])["printed"]
    c.bridge._printer.print_receipt = MagicMock(return_value=True)
    assert _call(c, "reprint_receipt", {"order_id": oid})["printed"]


@pytest.mark.parametrize("oid", [None, 0, -1, True, "1", 999999])
def test_bad_or_missing_order_never_prints(qapp, oid):
    c, db, _, _ = _setup(qapp)
    c.bridge._printer.print_receipt.reset_mock()
    r = c.call("reprint_receipt", {"order_id": oid})
    assert not r["success"] and "الطلب" in r["error"]
    c.bridge._printer.print_receipt.assert_not_called()


def test_signed_out_cannot_print_and_historical_date_is_available(qapp):
    c, db, _, _ = _setup(qapp)
    oid = _saved(c)
    db.execute("UPDATE orders SET status='completed',created_at='2024-01-02 12:00:00' WHERE id=?", (oid,)); db.commit()
    assert any(o["id"] == oid for o in _call(c, "get_order_history", {"date": "2024-01-02"}))
    assert not c.call("get_order_history", {"date": "bad"})["success"]
    _call(c, "logout")
    assert not c.call("reprint_receipt", {"order_id": oid})["success"]


@pytest.mark.parametrize("kind", ["dine_in", "delivery", "takeaway", "pickup"])
@pytest.mark.parametrize("copy", [False, True])
def test_copy_label_in_every_receipt_variant(kind, copy):
    p = _FakePrinter(); order = {**_order(), "order_type": kind, "is_copy": copy, "is_paid": False, "status": "cancelled"}
    assert tpl.print_customer_receipt(p, order)
    assert any("نسخة / COPY" in x for x in p.calls) == copy
    assert any("UNPAID" in x for x in p.calls) == copy
    assert any("CANCELLED" in x for x in p.calls) == copy


def test_copy_label_failure_is_not_reported_as_success():
    p = _FakePrinter(fail_at={4})
    assert not tpl.print_customer_receipt(p, {**_order(), "is_copy": True})
