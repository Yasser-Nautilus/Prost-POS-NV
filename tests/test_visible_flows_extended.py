# ruff: noqa: F811
"""Rendered App -> QWebChannel -> POSBridge -> SQLite: split payment, repeat
customer and park/resume (with a table). Same harness and switches as
tests/test_visible_cash_workflow.py (POS_RUN_RENDERED_TESTS=1, built frontend)."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import Qt
from test_e2e_user_flows import _build_test_bridge
from test_visible_cash_workflow import ROOT, Browser, qapp  # noqa: F401

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.ui.web_shell import WebShell

PRODUCT = "تشيكن فرايز حار"  # seeded, 70 EGP


def _start(qapp, monkeypatch):
    """Open day + cashier drawer through the bridge, then log in through the UI."""
    if not (ROOT / "frontend/dist/index.html").exists():
        pytest.skip("Build the frontend first")
    monkeypatch.setenv("POS_DEV_MODE", "0")
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(qapp)

    def call(action, payload=None):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"], result
        return result.get("data")

    call("login", {"pin": "1234"})
    day = call("open_shift")
    me = call("get_active_shift")["opened_by"]
    call("session.open", {"day_id": day["id"], "user_id": me, "station": "COUNTER",
                          "opening_float_egp": 100.0})
    return bridge, db, call


def _show(bridge):
    shell = WebShell(bridge)
    shell.setWindowState(Qt.WindowState.WindowNoState)
    shell.resize(1440, 1000)
    shell.show()
    browser = Browser(shell)
    browser.wait("document.querySelectorAll('button').length > 0")
    browser.js("window.__alerts=[];window.alert=(s)=>window.__alerts.push(s)")
    return shell, browser


def _login(browser, pin="1234"):
    for digit in pin:
        browser.click(digit)
    browser.click("تأكيد PIN")
    # Drawer is already open: wait for the product grid mode buttons.
    browser.wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='تيك أواي')")


def _add_product(browser):
    browser.wait(f"[...document.querySelectorAll('h4')].some(b=>b.textContent==={json.dumps(PRODUCT)})")
    browser.js(f"[...document.querySelectorAll('h4')].find(b=>b.textContent==={json.dumps(PRODUCT)}).parentElement.click()")


def test_visible_split_payment_cash_and_visa(qapp, monkeypatch):
    bridge, db, call = _start(qapp, monkeypatch)
    call("logout")
    shell, browser = _show(bridge)
    try:
        _login(browser)
        browser.click("تيك أواي")
        _add_product(browser)
        browser.click("تأكيد ودفع الفاتورة")
        browser.wait("document.body.innerText.includes('تأكيد الدفع') || document.body.innerText.includes('تسوية وإغلاق الفاتورة')")
        browser.click("تقسيم الفاتورة / دفع مختلط (كاش + فيزا)")
        browser.wait("!!document.querySelector('[data-testid=\"split-payment\"]')")
        assert browser.js("document.querySelector('[aria-label=\"مبلغ الدفعة 1\"]').value") == "35.00"
        # Unbalanced parts keep the confirm button disabled and nothing is paid.
        browser.field("مبلغ الدفعة 2", "30")
        browser.wait("[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('إنهاء وتأكيد الدفع')).disabled")
        assert db.fetch_one("SELECT is_paid FROM orders")["is_paid"] == 0
        browser.field("مبلغ الدفعة 2", "35")
        browser.field("النقد المستلم", "50")
        browser.wait("![...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('إنهاء وتأكيد الدفع')).disabled")
        browser.screenshot("20-split-payment.png")
        browser.js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('إنهاء وتأكيد الدفع')); b.click(); b.click();})()")
        browser.wait("window.__alerts.some(s=>s.includes('تم تسجيل الدفع'))")
        assert db.fetch_one("SELECT is_paid FROM orders")["is_paid"] == 1
        assert browser.js("window.__alerts.filter(s=>s.includes('تم تسجيل الدفع')).length") == 1
        parts = db.fetch_all("SELECT method, amount FROM order_payments ORDER BY id")
        assert [(p["method"], p["amount"]) for p in parts] == [("cash", 35.0), ("visa", 35.0)]
        # Only the cash share reaches the drawer.
        sale = db.fetch_all("SELECT amount_pt FROM cash_ledger WHERE entry_type='SALE_CASH'")
        assert [s["amount_pt"] for s in sale] == [3500]
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_park_resume_dine_in_with_table(qapp, monkeypatch):
    bridge, db, call = _start(qapp, monkeypatch)
    call("logout")
    shell, browser = _show(bridge)
    try:
        _login(browser)
        browser.click("صالة")
        browser.wait("document.body.innerText.includes('اختيار رقم الطاولة')")
        table = "[...document.querySelectorAll('button')].find(b=>b.querySelector('span')?.textContent==='طاولة'&&b.querySelectorAll('span')[1]?.textContent==='6')"
        browser.js(f"{table}.click()")
        browser.click("تأكيد الطاولة")
        _add_product(browser)
        browser.click("تعليق")
        browser.wait("document.body.innerText.includes('استرجاع طلب معلّق (1)')")
        draft = db.fetch_one("SELECT payload FROM parked_order_drafts")
        assert draft is not None
        assert PRODUCT in draft["payload"] or "product_id" in draft["payload"]
        assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 0
        browser.screenshot("21-parked-dine-in.png")
        browser.click("استرجاع طلب معلّق (1)")
        browser.wait("document.body.innerText.includes('1 عناصر')")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('1 عناصر')).click()")
        browser.wait(f"document.body.innerText.includes({json.dumps(PRODUCT)}) && document.body.innerText.includes('70')")
        # Resuming retains table choice; confirming must not ask for it again.
        browser.click("تأكيد الطلب")
        browser.wait("window.__alerts.some(s=>s.includes('بنجاح'))")
        assert db.fetch_one("SELECT table_no FROM orders")["table_no"] == 6
        # Confirmed exactly once.
        assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
        browser.screenshot("22-resumed-dine-in.png")
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_repeat_customer_reused_on_second_order(qapp, monkeypatch):
    bridge, db, call = _start(qapp, monkeypatch)
    customer = call("create_customer", {"name": "عميل متكرر", "phone": "01012345678"})
    call("new_order", {"order_type": "pickup"})
    call("add_item", {"product_id": 1})
    call("set_customer_info", {"customer_id": customer["id"], "phone": customer["phone"], "name": customer["name"]})
    call("confirm_order")
    call("logout")
    shell, browser = _show(bridge)
    try:
        _login(browser)
        browser.click("استلام محل")
        _add_product(browser)
        browser.click("اختيار عميل")
        browser.wait("!!document.querySelector('input[placeholder=\"أدخل رقم الموبايل...\"]')")
        browser.js("""(()=>{const e=document.querySelector('input[placeholder="أدخل رقم الموبايل..."]');
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'01012345678');
          e.dispatchEvent(new Event('input',{bubbles:true}));})()""")
        browser.click("بحث")
        browser.wait("document.body.innerText.includes('عميل متكرر') && document.body.innerText.includes('آخر الطلبات')")
        assert "هذا الرقم غير مسجل" not in browser.js("document.body.innerText")
        browser.screenshot("23-repeat-customer.png")
        browser.click("اختيار لاستلام المحل")
        # Pickup confirms now and is paid on handover.
        browser.click("تأكيد الطلب")
        browser.wait("window.__alerts.some(s=>s.includes('بنجاح'))")
        assert db.fetch_one("SELECT count(*) n FROM customers")["n"] == 1
        rows = db.fetch_all("SELECT customer_id FROM orders ORDER BY id")
        assert [r["customer_id"] for r in rows] == [customer["id"], customer["id"]]
    finally:
        shell.close()
        DatabaseConnection.reset()
