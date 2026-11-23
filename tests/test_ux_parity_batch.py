"""Tests for the UX/parity batch: phone normaliser, live expected cash, zones,
customer edit/search, category delete, monthly/yearly reports."""
from __future__ import annotations

import pytest

from broast_pos.core.phone import normalize_egyptian_mobile
from test_e2e_user_flows import _build_test_bridge, POSUserClient, qapp, reset_db_singleton  # noqa: F401


@pytest.mark.parametrize("raw,expected", [
    ("01012345678", "01012345678"),
    ("+201012345678", "01012345678"),
    ("+20 101 234 5678", "01012345678"),
    ("0101-234-5678", "01012345678"),
    ("00201112345678", "01112345678"),
    ("201212345678", "01212345678"),
    ("(0101) 234 5678", "01012345678"),
    ("01512345678", "01512345678"),
])
def test_phone_accepts_whatsapp_formats(raw, expected):
    assert normalize_egyptian_mobile(raw) == expected


@pytest.mark.parametrize("raw", [
    "", None, "0123", "01312345678", "01412345678", "0101234567", "010123456789",
    "٠١٠١٢٣٤٥٦٧٨", "+441012345678", "abc01012345678", "+2001012345678x",
])
def test_phone_rejects_bad_numbers(raw):
    assert normalize_egyptian_mobile(raw) is None


def _login_admin(qapp):
    bridge, db = _build_test_bridge(qapp)
    c = POSUserClient(bridge)
    assert c.call("login", {"pin": "1234"})["success"]
    return bridge, c


def test_customer_phone_is_normalised_and_deduplicated(qapp):
    _, c = _login_admin(qapp)
    r = c.call("create_customer", {"name": "علي", "phone": "+20 101 234 5678"})
    assert r["success"] and r["data"]["phone"] == "01012345678"
    dup = c.call("create_customer", {"name": "علي 2", "phone": "01012345678"})
    assert not dup["success"]
    found = c.call("find_customer_by_phone", {"phone": "0101-234-5678"})
    assert found["success"] and found["data"]["name"] == "علي"
    bad = c.call("create_customer", {"name": "س", "phone": "01312345678"})
    assert not bad["success"]


def test_driver_phone_normalised_and_validated(qapp):
    _, c = _login_admin(qapp)
    ok = c.call("create_user", {"username": "d1", "display_name": "سائق", "role": "cashier",
                                "pin": "3333", "cashier_slot": None, "phone": "+20 111 234 5678"})
    assert ok["success"] and ok["data"]["phone"] == "01112345678"
    bad = c.call("create_user", {"username": "d2", "display_name": "سائق 2", "role": "cashier",
                                 "pin": "4444", "cashier_slot": None, "phone": "12345"})
    assert not bad["success"]


def test_edit_and_search_customer(qapp):
    _, c = _login_admin(qapp)
    a = c.call("create_customer", {"name": "أحمد حسن", "phone": "01011111111"})["data"]
    c.call("create_customer", {"name": "منى", "phone": "01022222222"})
    assert [x["name"] for x in c.call("search_customers", {"query": "أحمد"})["data"]] == ["أحمد حسن"]
    assert len(c.call("search_customers", {"query": "0102"})["data"]) == 1
    assert c.call("search_customers", {"query": "ا"})["data"] == []  # too short
    r = c.call("update_customer", {"customer_id": a["id"], "name": "أحمد علي", "phone": "+20 100 000 0000"})
    assert r["success"] and r["data"]["phone"] == "01000000000" and r["data"]["name"] == "أحمد علي"
    clash = c.call("update_customer", {"customer_id": a["id"], "phone": "01022222222"})
    assert not clash["success"]
    assert not c.call("update_customer", {"customer_id": a["id"], "name": "  "})["success"]
    logs = c.call("get_audit_logs", {})
    assert logs["success"]


def test_zone_management_manager_only_and_audited(qapp):
    bridge, c = _login_admin(qapp)
    created = c.call("create_zone", {"name": "حي الورد", "delivery_fee": 35})
    assert created["success"] and created["data"]["delivery_fee"] == 35
    zid = created["data"]["id"]
    assert any(z["id"] == zid for z in c.call("get_active_zones")["data"])
    assert not c.call("create_zone", {"name": "", "delivery_fee": 5})["success"]
    assert not c.call("create_zone", {"name": "س", "delivery_fee": -1})["success"]
    up = c.call("update_zone", {"zone_id": zid, "delivery_fee": 40, "name": "حي الورد 2"})
    assert up["success"] and up["data"]["delivery_fee"] == 40
    off = c.call("update_zone", {"zone_id": zid, "is_active": False})
    assert off["success"] and not off["data"]["is_active"]
    assert not any(z["id"] == zid for z in c.call("get_active_zones")["data"])
    assert any(z["id"] == zid and not z["is_active"] for z in c.call("get_all_zones")["data"])
    types = [l["event_type"] for l in c.call("get_audit_logs", {})["data"]]
    assert "zone_created" in types and "zone_updated" in types
    # a cashier cannot manage zones
    c.call("create_user", {"username": "k", "display_name": "ك", "role": "cashier", "pin": "2222", "cashier_slot": 1})
    c.call("logout")
    assert c.call("login", {"pin": "2222"})["success"]
    assert not c.call("create_zone", {"name": "x", "delivery_fee": 1})["success"]
    assert not c.call("get_all_zones")["success"]
    assert not c.call("update_customer", {"customer_id": 1, "name": "x"})["success"]


def test_category_delete_rules(qapp):
    _, c = _login_admin(qapp)
    empty = c.call("create_category", {"name": "فئة فارغة"})["data"]["id"]
    assert c.call("delete_category", {"category_id": empty})["success"]
    cats = c.call("get_all_categories")["data"]
    assert not next(x for x in cats if x["id"] == empty)["is_active"]
    used = c.call("get_active_categories")["data"][0]["id"]
    blocked = c.call("delete_category", {"category_id": used})
    assert not blocked["success"]


def test_monthly_and_yearly_reports(qapp):
    _, c = _login_admin(qapp)
    from datetime import date
    today = date.today()
    m = c.call("get_report_monthly", {"year": today.year, "month": today.month})
    assert m["success"] and set(m["data"]) == {"summary", "bestsellers", "expenses"}
    y = c.call("get_report_yearly", {"year": today.year})
    assert y["success"] and "summary" in y["data"]
    assert not c.call("get_report_monthly", {"year": today.year, "month": 13})["success"]
    assert not c.call("get_report_yearly", {"year": 1})["success"]
    assert not c.call("get_report_monthly", {})["success"]


def test_open_session_reports_live_expected_cash(qapp):
    bridge, c = _login_admin(qapp)
    uid = c.call("get_current_user")["data"]["id"]
    day = c.call("open_shift")["data"]["id"]
    s = c.call("session.open", {"day_id": day, "user_id": uid, "station": "ALL", "opening_float_egp": 500.0})["data"]
    products = c.call("get_all_products")["data"]
    prod = products[0]
    assert c.call("new_order", {"order_type": "takeaway"})["success"]
    c.call("add_item", {"product_id": prod["id"], "product_name": prod["name"],
                        "unit_price": prod["price"], "quantity": 1})
    oid = c.call("confirm_order")["data"]["order_id"]
    paid = c.call("complete_payment", {"order_id": oid, "payment_method": "cash",
                                       "amount_paid": prod["price"], "keep_open": False})
    assert paid["success"], paid
    active = c.call("session.get_active", {"day_id": day})["data"]
    assert active[0]["expected_cash_egp"] == pytest.approx(500.0 + prod["price"])


def test_settlements_filter_by_driver_and_date():
    from types import SimpleNamespace
    from broast_pos.features.delivery_system.delivery_controller import DeliveryController

    def rec(i, d):
        return SimpleNamespace(
            id=i, driver_id=7, driver_name="x", settlement_date=d, trip_count=1,
            order_count=1, total_order_value=1.0, cash_collected=1.0, online_paid=0.0,
            total_delivery_fees=0.0, settled_by_name="m", notes=None, settled_at=None,
        )

    svc = SimpleNamespace(get_settlements_for_driver=lambda d: [rec(1, "2026-11-22"), rec(2, "2026-11-23")])
    ctrl = DeliveryController.__new__(DeliveryController)
    ctrl._settlement_svc = svc
    out = ctrl.get_driver_settlements(driver_id=7, date_str="2026-11-23")
    assert [r["id"] for r in out] == [2]
