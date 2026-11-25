# ruff: noqa: F811
"""Sending a driver trip prints a receipt slip per order, read-only.

The slip has no COPY / UNPAID label. Orders stay unpaid until trip settlement,
so the driver's cash is still handed in and counted exactly once."""
from __future__ import annotations

from unittest.mock import MagicMock

from test_batch_workflow_e2e import _delivery_order, _setup
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401

from broast_pos.infrastructure.printing.receipt_templates import print_customer_receipt


def _trip(c, drivers, n):
    ids = [_delivery_order(c)[0]]
    cust = c.call("find_customer_by_phone", {"phone": "01099887766"})["data"]
    addr = cust["addresses"][0]["id"] if cust.get("addresses") else None
    for _ in range(n - 1):
        assert c.call("new_order", {"order_type": "delivery"})["success"]
        assert c.call("set_customer_info", {"customer_id": cust["id"], "name": "عميل", "phone": "01099887766",
                                            "address": "ش 1", "address_id": addr, "payment_method": "cash"})["success"]
        assert c.call("add_item", {"product_id": 1})["success"]
        ids.append(c.call("confirm_order")["data"]["order_id"])
    assert c.call("check_in_driver", {"driver_id": drivers[0]})["success"]
    trip = c.call("create_trip", {"driver_id": drivers[0], "order_ids": ids})["data"]["trip_id"]
    return trip, ids


def _snapshot(db):
    tables = ["order_items", "cash_ledger", "order_payments"]
    snap = {t: [tuple(r) for r in db.fetch_all(f"SELECT * FROM {t}")] for t in tables}
    snap["orders"] = [(r["id"], r["is_paid"], r["total"], r["payment_method"])
                      for r in db.fetch_all("SELECT * FROM orders ORDER BY id")]
    return snap


def test_dispatch_prints_each_order_slip_and_changes_no_money(qapp):
    c, db, _, drivers = _setup(qapp)
    trip, ids = _trip(c, drivers, 2)
    pm = c.bridge._printer
    pm.print_receipt.reset_mock()
    before = _snapshot(db)
    res = c.call("dispatch_trip", {"trip_id": trip})
    assert res["success"] and res["data"] == {"print_failed": []}
    assert pm.print_receipt.call_count == 2
    sent = [a.args[0] for a in pm.print_receipt.call_args_list]
    assert {d["invoice_no"] for d in sent} == {
        r["invoice_no"] for r in db.fetch_all("SELECT invoice_no FROM orders WHERE id IN (?,?)", tuple(ids))}
    assert all(d["order_type"] == "delivery" and not d.get("is_copy") and not d.get("is_paid") for d in sent)
    assert all(d["customer_phone"] and d["customer_address"] and d["delivery_fee"] and d["items"] for d in sent)
    assert before == _snapshot(db)
    assert all(not r["is_paid"] for r in db.fetch_all("SELECT is_paid FROM orders"))
    assert len(db.fetch_all("SELECT * FROM audit_log WHERE event_type='receipt_reprinted'")) == 2


def test_printer_failure_is_reported_but_dispatch_stands(qapp):
    c, db, _, drivers = _setup(qapp)
    trip, ids = _trip(c, drivers, 2)
    c.bridge._printer.print_receipt = MagicMock(side_effect=RuntimeError("offline"))
    res = c.call("dispatch_trip", {"trip_id": trip})
    assert res["success"] and len(res["data"]["print_failed"]) == 2
    status = db.fetch_one("SELECT status FROM orders WHERE id=?", (ids[0],))["status"]
    assert status == "out_for_delivery"
    assert db.fetch_one("SELECT dispatched_at FROM delivery_trips WHERE id=?", (trip,))["dispatched_at"] is not None


def test_failed_or_repeated_dispatch_prints_nothing(qapp):
    c, db, _, drivers = _setup(qapp)
    trip, _ids = _trip(c, drivers, 1)
    assert c.call("dispatch_trip", {"trip_id": trip})["success"]
    pm = c.bridge._printer
    pm.print_receipt.reset_mock()
    assert not c.call("dispatch_trip", {"trip_id": trip})["success"]
    assert not c.call("dispatch_trip", {"trip_id": 99999})["success"]
    pm.print_receipt.assert_not_called()


def test_settlement_cash_still_counted_once_after_slips(qapp):
    c, db, _, drivers = _setup(qapp)
    trip, _ids = _trip(c, drivers, 2)
    expected = sum(r["total"] for r in db.fetch_all("SELECT total FROM orders"))
    assert c.call("dispatch_trip", {"trip_id": trip})["success"]
    assert c.call("return_trip", {"trip_id": trip})["success"]
    prev = c.call("get_driver_settlement_preview", {"driver_id": drivers[0], "trip_id": trip})["data"]
    assert prev["cash_collected"] == expected


class _Recorder:
    """Records receipt lines instead of talking to a printer."""

    def __init__(self):
        self.lines = []

    def print_text(self, text, **_kw):
        self.lines.append(text)
        return True

    def print_line(self, char="-", width=32):
        self.lines.append(char * width)
        return True

    print_double_line = lambda self, width=32: self.print_line("=", width)  # noqa: E731
    cut = lambda self: True  # noqa: E731


def test_driver_slip_reads_like_invoice_without_paid_or_change(qapp):
    c, db, _, drivers = _setup(qapp)
    trip, _ids = _trip(c, drivers, 1)
    pm = c.bridge._printer
    pm.print_receipt.reset_mock()
    assert c.call("dispatch_trip", {"trip_id": trip})["success"]
    sent = pm.print_receipt.call_args_list[0].args[0]
    assert sent["driver_slip"] is True
    rec = _Recorder()
    assert print_customer_receipt(rec, sent)
    text = "\n".join(rec.lines)
    assert "Paid:" not in text and "Change:" not in text
    assert sent["customer_name"] in text
    assert rec.lines.index("Total") < text.count("\n", 0, text.index("Delivery Fee"))
    # A normal paid delivery receipt is unchanged.
    normal = _Recorder()
    print_customer_receipt(normal, {**sent, "driver_slip": False})
    ntext = "\n".join(normal.lines)
    assert "Paid:" in ntext and "Change:" in ntext
    assert ntext.index("Delivery Fee") < ntext.index("\nTotal\n")
    print("\n".join(rec.lines))
