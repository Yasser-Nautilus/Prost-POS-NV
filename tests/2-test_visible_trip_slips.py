# ruff: noqa: F811
"""Rendered App -> QWebChannel -> POSBridge -> SQLite: sending a driver trip
prints a slip for each order and leaves the orders unpaid until settlement."""
from __future__ import annotations

from unittest.mock import MagicMock

from test_batch_workflow_e2e import _delivery_order
from test_e2e_user_flows import POSUserClient
from test_visible_cash_workflow import qapp  # noqa: F401
from test_visible_flows_extended import _login, _show, _start

from broast_pos.data.database.connection import DatabaseConnection


def _two_orders_and_driver(bridge, db, call):
    db.execute("UPDATE cashier_sessions SET station='ALL'")
    db.commit()
    driver = call("create_user", {"username": "ali", "display_name": "علي", "role": "cashier",
                                  "pin": "3333", "phone": "01012345678", "cashier_slot": None})["id"]
    client = POSUserClient(bridge)
    first, _ = _delivery_order(client)
    cust = call("find_customer_by_phone", {"phone": "01099887766"})
    call("new_order", {"order_type": "delivery"})
    call("set_customer_info", {"customer_id": cust["id"], "name": "عميل", "phone": "01099887766",
                               "address": "ش 1", "address_id": cust["addresses"][0]["id"],
                               "payment_method": "cash"})
    call("add_item", {"product_id": 1})
    second = call("confirm_order")["order_id"]
    call("check_in_driver", {"driver_id": driver})
    return driver, [first, second]


def test_visible_trip_send_prints_slip_per_order_and_stays_unpaid(qapp, monkeypatch):
    bridge, db, call = _start(qapp, monkeypatch)
    _driver, order_ids = _two_orders_and_driver(bridge, db, call)
    call("logout")
    shell, browser = _show(bridge)
    try:
        _login(browser)
        browser.click("توصيل الطلبات")
        browser.wait("document.body.innerText.includes('طلبات تنتظر إرسال')")
        browser.js("document.querySelectorAll('tbody tr').forEach(r=>r.click())")
        browser.js("""(()=>{const s=document.querySelector('select');
          Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,s.options[1].value);
          s.dispatchEvent(new Event('change',{bubbles:true}));})()""")
        browser.wait("document.body.innerText.includes('إرسال الطيار (2 طلب)')")
        browser.screenshot("30-trip-before-send.png")
        pm = bridge._printer
        pm.print_receipt.reset_mock()
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('إرسال الطيار')).click()")
        browser.wait("document.body.innerText.includes('لا توجد طلبات تنتظر إرسال')")
        assert pm.print_receipt.call_count == 2
        sent = [a.args[0] for a in pm.print_receipt.call_args_list]
        assert all(not d.get("is_copy") and d["customer_phone"] and d["customer_address"] for d in sent)
        rows = db.fetch_all("SELECT is_paid, status FROM orders WHERE id IN (?,?)", tuple(order_ids))
        assert [(r["is_paid"], r["status"]) for r in rows] == [(0, "out_for_delivery")] * 2
        assert browser.js("window.__alerts.length") == 0
        browser.screenshot("31-trip-sent-printed.png")
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_trip_send_printer_failure_warns_but_dispatches(qapp, monkeypatch):
    bridge, db, call = _start(qapp, monkeypatch)
    _driver, order_ids = _two_orders_and_driver(bridge, db, call)
    call("logout")
    shell, browser = _show(bridge)
    try:
        _login(browser)
        browser.click("توصيل الطلبات")
        browser.wait("document.body.innerText.includes('طلبات تنتظر إرسال')")
        browser.js("document.querySelectorAll('tbody tr').forEach(r=>r.click())")
        browser.js("""(()=>{const s=document.querySelector('select');
          Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(s,s.options[1].value);
          s.dispatchEvent(new Event('change',{bubbles:true}));})()""")
        bridge._printer.print_receipt = MagicMock(return_value=False)
        browser.wait("document.body.innerText.includes('إرسال الطيار (2 طلب)')")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('إرسال الطيار')).click()")
        browser.wait("window.__alerts.some(s=>s.includes('تعذرت طباعة ورقة السائق'))")
        rows = db.fetch_all("SELECT status FROM orders WHERE id IN (?,?)", tuple(order_ids))
        assert [r["status"] for r in rows] == ["out_for_delivery"] * 2
        browser.screenshot("32-trip-print-failed-warning.png")
    finally:
        shell.close()
        DatabaseConnection.reset()
