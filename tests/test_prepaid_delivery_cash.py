"""Prepaid cash must not become driver cash a second time, via either API."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection


@pytest.fixture
def api():
    app = QCoreApplication.instance() or QCoreApplication(["delivery-cash-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)

    def call(action, payload=None):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"], (action, result)
        return result.get("data")

    call("login", {"pin": "1234"})
    call("open_shift")
    call("session.open", {"station": "ALL", "opening_float_egp": 0})
    driver = bridge._auth.create_user("driver", "Driver", UserRole.CASHIER, "3579")
    customer = bridge._customer.create_customer("Cash test", "01012345678")
    zone = bridge._customer.get_active_zones()[0]
    address = bridge._customer.add_address(customer.id, "Test street", zone.id)
    call("check_in_driver", {"driver_id": driver.id})

    def order(payment="cash", prepaid=False):
        call("new_order", {"order_type": "delivery"})
        call("add_item", {"product_id": 1})
        call("set_customer_info", {
            "customer_id": customer.id, "name": customer.name, "phone": customer.phone,
            "address": "Test street", "address_id": address.id, "payment_method": payment,
        })
        oid = call("confirm_order")["order_id"]
        total = db.fetch_one("SELECT total FROM orders WHERE id=?", (oid,))["total"]
        if prepaid:
            call("complete_payment", {"order_id": oid, "payment_method": "cash",
                                      "amount_paid": total, "keep_open": True})
        return oid, total

    def rejected(action, payload):
        result = json.loads(bridge.dispatch(action, json.dumps(payload)))
        assert result["success"] is False, result
    call.rejected = rejected
    yield call, order, driver.id, db
    DatabaseConnection.reset()


@pytest.mark.parametrize("route", ["settle_trip", "settle_driver_trip", "settle_driver_day"])
@pytest.mark.parametrize("mixed", [False, True])
def test_prepaid_delivery_is_not_remitted_twice(api, route, mixed):
    call, order, driver_id, db = api
    prepaid_id, prepaid_total = order(prepaid=True)
    ids = [prepaid_id]
    due = 0
    if mixed:
        cod_id, due = order()
        online_id, _ = order(payment="online")
        ids += [cod_id, online_id]
    trip_id = call("create_trip", {"driver_id": driver_id, "order_ids": ids})["trip_id"]
    call("dispatch_trip", {"trip_id": trip_id})
    call("return_trip", {"trip_id": trip_id})
    assert call("get_trip_details", {"trip_id": trip_id})["amount_to_hand_over"] == due
    preview = call("get_driver_settlement_preview", {"driver_id": driver_id})
    assert preview["cash_collected"] == due
    assert preview["trips"][0]["cash"] == due
    expected_fees = db.fetch_one("SELECT SUM(delivery_fee) n FROM orders")["n"]
    assert preview["total_delivery_fees"] == expected_fees
    if mixed:
        assert preview["online_paid"] == db.fetch_one("SELECT total FROM orders WHERE payment_method='online'")["total"]

    if route == "settle_trip":
        call(route, {"trip_id": trip_id})
    else:
        payload = {"driver_id": driver_id}
        if route == "settle_driver_trip":
            payload["trip_id"] = trip_id
        call("settle_driver", payload)

    entries = db.fetch_all("SELECT * FROM cash_ledger")
    assert sum(e["amount_pt"] for e in entries) == round((prepaid_total + due) * 100)
    sales = [e for e in entries if e["entry_type"] == "SALE_CASH"]
    remits = [e for e in entries if e["entry_type"] == "DRIVER_REMITTANCE"]
    assert len(sales) == 1 and sales[0]["order_id"] == prepaid_id
    assert len(remits) == (1 if mixed else 0)
    if mixed:
        assert remits[0]["amount_pt"] == round(due * 100)
    assert db.fetch_one("SELECT cash_collected FROM delivery_trips WHERE id=?", (trip_id,))["cash_collected"] == due
    assert all(r["is_paid"] and r["status"] == "completed" for r in db.fetch_all("SELECT is_paid,status FROM orders"))
    # Completion paid the COD order, but historical summaries must retain the handover.
    historical = call("get_driver_settlement_preview", {"driver_id": driver_id})
    assert historical["cash_collected"] == due
    assert historical["total_delivery_fees"] == expected_fees
    assert call("get_trip_details", {"trip_id": trip_id})["cash_collected"] == due
    before = sum(e["amount_pt"] for e in entries)
    call.rejected("settle_trip", {"trip_id": trip_id})
    call.rejected("complete_payment", {"order_id": prepaid_id, "payment_method": "cash",
                                       "amount_paid": prepaid_total, "keep_open": True})
    if route == "settle_trip":
        # Day close summarizes the already handed-over trip without adding cash again.
        call("settle_driver", {"driver_id": driver_id})
        assert db.fetch_one("SELECT cash_collected FROM driver_settlements")["cash_collected"] == due
    assert db.fetch_one("SELECT SUM(amount_pt) n FROM cash_ledger")["n"] == before


@pytest.mark.parametrize("paid,cancelled,method,expected", [
    (False, False, "cash", 150),
    (True, False, "cash", 0),
    (False, True, "cash", 0),
    (True, False, "online", 0),
    (False, False, "visa", 0),
])
def test_cash_due_policy(paid, cancelled, method, expected):
    from broast_pos.core.models.order import Order, OrderStatus, PaymentMethod

    order = Order(total=150, is_paid=paid, payment_method=PaymentMethod(method),
                  status=OrderStatus.CANCELLED if cancelled else OrderStatus.DELIVERED)
    assert order.cash_due_on_delivery == expected
