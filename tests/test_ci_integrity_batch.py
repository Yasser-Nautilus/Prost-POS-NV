# ruff: noqa: F811
"""Report errors, discount after item removal, paid-only period reports,
driver check-out while on a trip."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from test_batch_workflow_e2e import _delivery_order, _setup
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401

from broast_pos.core.models.order import Order, OrderItem
from broast_pos.core.policies.discount import rescale_discount
from broast_pos.features.reports.reports_controller import ReportsController

# ---- B: report errors must surface, not turn into zeros -------------------

REPORT_CALLS = [
    ("get_sales_by_type", ()),
    ("get_payment_breakdown", ()),
    ("get_bestsellers", ()),
    ("get_cancelled_orders", ()),
    ("get_monthly_summary", (2026, 11)),
    ("get_monthly_bestsellers", (2026, 11)),
    ("get_monthly_expenses", (2026, 11)),
    ("get_yearly_summary", (2026,)),
    ("get_yearly_bestsellers", (2026,)),
    ("get_active_shift_id", ()),
]


@pytest.mark.parametrize("name,args", REPORT_CALLS)
def test_report_db_error_raises_instead_of_returning_zero(name, args):
    svc = MagicMock()
    boom = RuntimeError("database is locked")
    svc.configure_mock(**{
        "generate_daily_sales.side_effect": boom,
        "generate_payment_breakdown.side_effect": boom,
        "generate_product_sales.side_effect": boom,
        "generate_cancelled_orders.side_effect": boom,
        "generate_monthly_summary.side_effect": boom,
        "generate_monthly_bestsellers.side_effect": boom,
        "generate_monthly_expenses.side_effect": boom,
        "generate_yearly_summary.side_effect": boom,
        "generate_yearly_bestsellers.side_effect": boom,
    })
    fin = MagicMock()
    fin._financial.get_active_shift.side_effect = boom
    ctrl = ReportsController(svc, fin)
    with pytest.raises(ValueError, match="database is locked"):
        getattr(ctrl, name)(*args)


def test_daily_summary_driver_failure_is_an_error_not_an_empty_list():
    svc = MagicMock()
    svc.generate_daily_sales.return_value = {
        "date": date.today().isoformat(), "breakdown": [],
        "grand_total": {"count": 0, "revenue": 0.0},
    }
    svc.generate_payment_breakdown.return_value = {"payments": [], "total": 0.0}
    svc.generate_cancelled_orders.return_value = {"count": 0, "orders": []}
    svc.generate_product_sales.return_value = []
    svc.generate_driver_summary.side_effect = RuntimeError("driver query failed")
    svc._orders.get_completed_for_date.return_value = []
    ctrl = ReportsController(svc, MagicMock())
    with pytest.raises(ValueError, match="driver query failed"):
        ctrl.generate_daily_summary()


# ---- C: discount follows the order when items are removed -----------------

def test_rescale_discount_policy():
    assert rescale_discount(100, "flat", 140, 70) == 70.0       # capped at subtotal
    assert rescale_discount(20, "flat", 140, 70) == 20.0        # still fits
    assert rescale_discount(70, "percent", 140, 70) == 35.0     # keeps 50%
    assert rescale_discount(70, "percent", 140, 0) == 0.0       # empty order
    assert rescale_discount(0, "flat", 140, 70) == 0.0


def test_order_model_recalculate_never_goes_negative():
    order = Order(items=[OrderItem(1, "a", 1, 70), OrderItem(1, "a", 1, 70)])
    order.recalculate()
    order.discount_amount, order.discount_type = 100.0, "flat"
    order.recalculate()
    order.items.pop()
    order.recalculate()
    assert order.subtotal == 70.0
    assert order.discount_amount == 70.0
    assert order.total == 0.0


def _saved_order_with_discount(c, kind, value):
    products = c.call("get_all_products")["data"]
    prod = products[0]
    assert c.call("new_order", {"order_type": "takeaway"})["success"]
    for _ in range(2):
        assert c.call("add_item", {"product_id": prod["id"], "product_name": prod["name"],
                                   "unit_price": prod["price"], "quantity": 1})["success"]
    oid = c.call("confirm_order")["data"]["order_id"]
    assert c.call("load_order", {"order_id": oid})["success"]
    r = c.call("apply_discount", {"value": value, "discount_type": kind, "manager_pin": "1234"})
    assert r["success"], r
    return oid, prod


@pytest.mark.parametrize("kind,value", [("flat", 100), ("percent", 50)])
def test_saved_order_discount_follows_item_removal(qapp, kind, value):
    c, db, shift, _ = _setup(qapp)
    oid, prod = _saved_order_with_discount(c, kind, value)
    before = db.fetch_one("SELECT subtotal, discount_amount FROM orders WHERE id=?", (oid,))
    assert before["discount_amount"] > 0
    assert c.call("load_order", {"order_id": oid})["success"]
    assert c.call("remove_item", {"index": 0, "manager_pin": "1234"})["success"]
    r = c.call("save_amendment", {"manager_pin": "1234", "reason": "test"})
    assert r["success"], r
    after = db.fetch_one("SELECT subtotal, discount_amount, total FROM orders WHERE id=?", (oid,))
    assert after["total"] >= 0
    assert after["discount_amount"] <= after["subtotal"]
    if kind == "percent":
        assert after["discount_amount"] == pytest.approx(after["subtotal"] * 0.5)


# ---- D: monthly / yearly reports count paid orders only -------------------

def test_monthly_and_yearly_reports_count_paid_orders_only(qapp):
    c, db, shift, _ = _setup(qapp)
    products = c.call("get_all_products")["data"]
    prod = products[0]

    def make():
        assert c.call("new_order", {"order_type": "takeaway"})["success"]
        assert c.call("add_item", {"product_id": prod["id"], "product_name": prod["name"],
                                   "unit_price": prod["price"], "quantity": 1})["success"]
        return c.call("confirm_order")["data"]["order_id"]

    paid_id = make()
    unpaid_id = make()
    total = db.fetch_one("SELECT total FROM orders WHERE id=?", (paid_id,))["total"]
    r = c.call("complete_payment", {"order_id": paid_id, "payment_method": "cash",
                                    "amount_paid": total})
    assert r["success"], r
    assert db.fetch_one("SELECT is_paid FROM orders WHERE id=?", (unpaid_id,))["is_paid"] == 0

    today = date.today()
    c.call("logout")
    assert c.call("login", {"pin": "1234"})["success"]
    m = c.call("get_report_monthly", {"year": today.year, "month": today.month})
    assert m["success"], m
    assert m["data"]["summary"]["total_sales"] == pytest.approx(total)
    qty = sum(b["quantity"] for b in m["data"]["bestsellers"])
    assert qty == 1
    y = c.call("get_report_yearly", {"year": today.year})
    assert y["success"], y
    assert y["data"]["summary"]["total_sales"] == pytest.approx(total)
    assert sum(b["quantity"] for b in y["data"]["bestsellers"]) == 1


def test_report_failure_reaches_the_screen_as_an_error(qapp, monkeypatch):
    c, db, shift, _ = _setup(qapp)
    c.call("logout")
    assert c.call("login", {"pin": "1234"})["success"]

    def boom(*a, **k):
        raise RuntimeError("disk I/O error")

    monkeypatch.setattr(c.bridge._reports_ctrl._report_svc, "generate_monthly_summary", boom, raising=True)
    r = c.call("get_report_monthly", {"year": 2026, "month": 11})
    assert r["success"] is False
    assert "disk I/O error" in r["error"]


# ---- E: driver cannot be checked out while on a trip ----------------------

def test_driver_cannot_check_out_while_trip_not_returned(qapp):
    c, db, shift, (d1, d2) = _setup(qapp)
    oid, _ = _delivery_order(c)
    assert c.call("check_in_driver", {"driver_id": d1})["success"]
    trip = c.call("create_trip", {"driver_id": d1, "order_ids": [oid]})["data"]["trip_id"]
    assert c.call("dispatch_trip", {"trip_id": trip})["success"]

    r = c.call("check_out_driver", {"driver_id": d1})
    assert r["success"] is False
    assert "رحلة" in r["error"]
    assert db.fetch_one(
        "SELECT COUNT(*) c FROM driver_attendance WHERE driver_id=? AND check_out_at IS NULL", (d1,)
    )["c"] == 1

    assert c.call("return_trip", {"trip_id": trip})["success"]
    # returned but not yet settled: still blocked by the existing unsettled-trip guard
    assert c.call("check_out_driver", {"driver_id": d1})["success"] is False
    assert c.call("settle_driver", {"driver_id": d1})["success"]
    assert c.call("check_out_driver", {"driver_id": d1})["success"]
