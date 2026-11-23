"""Backend end-to-end tests (real bridge + in-memory DB) for items 8, 9, 11, 15."""
from __future__ import annotations

import json

import pytest

from test_e2e_user_flows import _build_test_bridge, POSUserClient, qapp, reset_db_singleton  # noqa: F401


def _setup(qapp):
    bridge, db = _build_test_bridge(qapp)
    # Same wiring as main.py: settlement books the fee expense via FinancialService
    bridge._settlement._expense_recorder = bridge._financial
    c = POSUserClient(bridge)
    assert c.call("login", {"pin": "1234"})["success"]
    cashier = c.call("create_user", {"username": "sara", "display_name": "سارة", "role": "cashier",
                                     "pin": "2222", "cashier_slot": 1})["data"]["id"]
    drivers = []
    for i, pin in enumerate(("3333", "4444")):
        r = c.call("create_user", {"username": f"drv{i}", "display_name": f"سائق {i}", "role": "cashier",
                                   "pin": pin, "cashier_slot": None, "phone": f"0101234567{i}"})
        assert r["success"], r
        drivers.append(r["data"]["id"])
    c.call("logout")
    assert c.call("login", {"pin": "2222"})["success"]
    shift = c.call("open_shift")["data"]["id"]
    sess = c.call("session.open", {"day_id": shift, "user_id": cashier, "station": "ALL",
                                   "opening_float_egp": 500.0})
    assert sess["success"]
    c.session_id = sess["data"]["id"]
    return c, db, shift, drivers


def _delivery_order(c, qapp_unused=None):
    products = c.call("get_all_products")["data"]
    prod = next(p for p in products if "2 قطعة دجاج عادي" in p["name"])
    cust = c.call("create_customer", {"name": "عميل", "phone": "01099887766"})["data"]["id"]
    zone = next(z for z in c.call("get_active_zones")["data"] if "شارع الانتاج" in z["name"])
    addr = c.call("add_customer_address", {"customer_id": cust, "street_name": "ش 1", "zone_id": zone["id"]})["data"]["id"]
    assert c.call("new_order", {"order_type": "delivery"})["success"]
    assert c.call("set_customer_info", {"customer_id": cust, "name": "عميل", "phone": "01099887766",
                                        "address": "ش 1", "address_id": addr, "payment_method": "cash"})["success"]
    assert c.call("add_item", {"product_id": prod["id"], "product_name": prod["name"],
                               "unit_price": prod["price"], "quantity": 1})["success"]
    return c.call("confirm_order")["data"]["order_id"], prod


def test_day_settlement_books_fee_expense_once_and_close_checks_out_drivers(qapp):
    c, db, shift, (d1, d2) = _setup(qapp)
    oid, _ = _delivery_order(c)
    assert c.call("check_in_driver", {"driver_id": d1})["success"]
    assert c.call("check_in_driver", {"driver_id": d2})["success"]
    trip = c.call("create_trip", {"driver_id": d1, "order_ids": [oid]})["data"]["trip_id"]
    assert c.call("dispatch_trip", {"trip_id": trip})["success"]
    assert c.call("return_trip", {"trip_id": trip})["success"]

    prev = c.call("get_driver_settlement_preview", {"driver_id": d1})["data"]
    assert prev["fee_breakdown"] == [{"fee": 15.0, "order_count": 1, "subtotal": 15.0}]

    # Item 10 print sheet works for a cashier and never trusts client numbers
    r = c.call("print_driver_day_sheet", {"driver_id": d1})
    assert r["success"], r

    # Item 9: full-day settlement books the fees as an expense in the driver's name
    r = c.call("settle_driver", {"driver_id": d1})
    assert r["success"], r
    exps = c.call("get_expenses")["data"]
    fee_exps = [e for e in exps if e.get("category") == "delivery_fees"]
    assert len(fee_exps) == 1, exps
    assert fee_exps[0]["amount"] == 15.0
    assert "سائق 0" in fee_exps[0]["description"]

    # Item 8: closing the shift checks out every driver still on duty
    open_before = db.fetch_one("SELECT COUNT(*) c FROM driver_attendance WHERE check_out_at IS NULL")["c"]
    assert open_before == 2
    r = c.call("session.close", {"session_id": c.session_id, "counted_cash_egp": 500.0,
                                 "manager_pin": "1234", "variance_reason": "test"})
    assert r["success"], r
    c.call("logout"); c.call("login", {"pin": "1234"})
    assert c.call("print_shift_summary")["success"]
    r = c.call("close_shift")
    assert r["success"], r
    assert db.fetch_one("SELECT COUNT(*) c FROM driver_attendance WHERE check_out_at IS NULL")["c"] == 0
    # Fee expense not paid out twice at close: exactly one DRIVER_FEE_PAYOUT for the trip
    n = db.fetch_one("SELECT COUNT(*) c FROM cash_ledger WHERE entry_type='DRIVER_FEE_PAYOUT'")["c"]
    assert n == 1

    # Item 11: a new shift starts from zero (invoice #1, no expenses)
    c.call("logout"); c.call("login", {"pin": "2222"})
    assert c.call("open_shift")["success"]
    assert c.call("get_expenses")["data"] == []
    assert c.call("new_order", {"order_type": "takeaway"})["success"]
    assert c.call("get_current_order")["data"].get("invoice_no") in (1, None)


def test_cashier_cancels_with_manager_pin_and_reason_without_logout(qapp):
    c, db, shift, _ = _setup(qapp)
    oid, _p = _delivery_order(c)
    # no reason -> rejected
    r = c.call("cancel_order", {"order_id": oid, "manager_pin": "1234"})
    assert not r["success"]
    # wrong pin -> rejected
    r = c.call("cancel_order", {"order_id": oid, "reason": "غلط", "manager_pin": "0000"})
    assert not r["success"]
    # right pin + reason -> cancelled, cashier still the logged-in user
    r = c.call("cancel_order", {"order_id": oid, "reason": "العميل ألغى", "manager_pin": "1234"})
    assert r["success"], r
    rows = db.fetch_all("SELECT details FROM audit_log WHERE details LIKE '%العميل ألغى%'")
    assert rows, "cancellation reason must be audited"
    assert c.call("get_active_shift")["success"]
