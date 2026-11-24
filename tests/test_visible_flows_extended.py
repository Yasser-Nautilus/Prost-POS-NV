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


def test_visible_single_trip_then_day_expense_and_completed_state(qapp, monkeypatch):
    from test_batch_workflow_e2e import _delivery_order
    from test_e2e_user_flows import POSUserClient

    bridge, db, call = _start(qapp, monkeypatch)
    bridge._settlement._expense_recorder = bridge._financial
    db.execute("UPDATE cashier_sessions SET station='ALL'")
    db.commit()
    driver = call("create_user", {"username": "ali", "display_name": "علي", "role": "cashier",
                                  "pin": "3333", "phone": "01012345678", "cashier_slot": None})["id"]
    zone = next(z for z in call("get_active_zones") if "شارع الانتاج" in z["name"])
    call("update_zone", {"zone_id": zone["id"], "delivery_fee": 65})
    client = POSUserClient(bridge)
    oid, _ = _delivery_order(client)
    call("check_in_driver", {"driver_id": driver})
    trip = call("create_trip", {"driver_id": driver, "order_ids": [oid]})["trip_id"]
    call("dispatch_trip", {"trip_id": trip})
    call("return_trip", {"trip_id": trip})
    call("logout")
    shell, browser = _show(bridge)
    try:
        _login(browser)
        browser.click("تسوية السائقين")
        browser.wait("document.body.innerText.includes('علي')")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('علي')&&b.textContent.includes('حاضر اليوم')).click()")
        browser.click("تسوية هذه الرحلة")
        browser.click("تأكيد تسوية هذه الرحلة فقط")
        browser.wait("document.body.innerText.includes('تمت التسوية بنجاح')")
        assert call("get_expenses") == []
        browser.click("تسوية رحلة أخرى لنفس السائق")
        browser.click("تسوية آخر اليوم")
        browser.wait("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('تأكيد: تسجيل 65.00'))")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('تأكيد: تسجيل')).click()")
        browser.wait("document.body.innerText.includes('تمت تسوية آخر اليوم — المدفوع 65.00')")
        assert not browser.js("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='تسوية آخر اليوم')")
        assert len(call("get_expenses")) == 1
        assert call("get_expenses")[0]["amount"] == 65
        assert db.fetch_one("SELECT count(*) n FROM cash_ledger WHERE entry_type='DRIVER_FEE_PAYOUT'")["n"] == 1
        browser.screenshot("24-driver-day-completed.png")
        # Successful settlement opens the cashier-accessible shift dialog.
        browser.wait("document.body.innerText.includes('تمت تسوية رسوم السائق بنجاح')")
        browser.wait("document.body.innerText.includes('سجل المصروفات بالوردية الحالية:')")
        browser.screenshot("25-driver-expense.png")
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_driver_order_numbers_wrapping_and_day_rollover(qapp, monkeypatch):
    from test_batch_workflow_e2e import _setup
    from test_driver_business_day import _call, _trip

    monkeypatch.setenv("POS_DEV_MODE", "0")
    c, db, day, (driver, _) = _setup(qapp)
    tid = _trip(c, driver, db)
    long_name = "عميل بنفس الاسم طويل جداً للاختبار " * 4
    db.execute("UPDATE orders SET customer_name=?, customer_address=?", (long_name, "عنوان طويل شارع رئيسي " * 6))
    db.commit()
    _call(c, "logout")
    shell, browser = _show(c.bridge)
    try:
        _login(browser, "1234")
        browser.click("تسوية السائقين")
        browser.wait("document.body.innerText.includes('سائق 0')")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('سائق 0')&&b.textContent.includes('حاضر اليوم')).click()")
        browser.click("▼ عرض الطلبات")
        browser.wait("document.body.innerText.includes('أوردر #1')")
        shell.resize(1040, 900)
        browser.screenshot("30-expanded-order-number-narrow.png")
        browser.click("تسوية هذه الرحلة")
        browser.wait("document.body.innerText.includes('أوردر #1')")
        browser.screenshot("31-order-preview-narrow.png")
        # No order-row descendant escapes the right-hand order-list card.
        assert browser.js("""(()=>{const badge=[...document.querySelectorAll('span')].find(e=>e.textContent==='أوردر #1');
          const card=badge.parentElement.parentElement;const r=card.getBoundingClientRect();
          return [...card.querySelectorAll('*')].every(e=>{const b=e.getBoundingClientRect();return b.left>=r.left-1&&b.right<=r.right+1});})()""")
        browser.click("تأكيد تسوية هذه الرحلة فقط")
        browser.click("تسوية رحلة أخرى لنفس السائق")
        browser.click("تسوية آخر اليوم")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('تأكيد: تسجيل')).click()")
        browser.wait("document.body.innerText.includes('إدارة وردية الصندوق')")
        # Close the drawer through the real handler, then close the day through
        # the visible dialog. Its status callback must reset the mounted view.
        _call(c, "session.close", {"session_id": c.session_id, "counted_cash_egp": 500,
                                    "manager_pin": "1234", "variance_reason": "UI rollover"})
        browser.click("طباعة ملخص الوردية")
        browser.click("إغلاق الوردية")
        browser.field("رمز PIN للمدير", "1234")
        browser.click("تأكيد الرمز")
        browser.wait("document.body.innerText.includes('الوردية مغلقة')")
        assert not browser.js("document.body.innerText.includes('أوردر #1')")
        assert not browser.js("document.body.innerText.includes('تمت تسوية آخر اليوم — المدفوع')")
        browser.click("الوردية مغلقة")
        browser.wait("!!document.querySelector('[aria-label=\"محطة الدرج\"]')")
        browser.field("محطة الدرج", "ALL", select=True)
        browser.field("النقد الموجود بالدرج عند الفتح", "100")
        browser.click("فتح يوم العمل ودرج الكاشير")
        browser.wait("document.body.innerText.includes('الوردية مفتوحة')")
        new_day = _call(c, "get_active_shift")["id"]
        assert new_day != day
        # Close dialog with its visible X and return to the same driver.
        browser.js("[...document.querySelectorAll('h3')].find(e=>e.textContent.includes('إدارة وردية الصندوق')).parentElement.querySelector('button').click()")
        browser.wait("document.body.innerText.includes('سائق 0')")
        _call(c, "check_in_driver", {"driver_id": driver})
        browser.js("document.querySelector('button[title=\"تحديث\"]').click()")
        browser.wait("document.body.innerText.includes('حاضر اليوم')")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('سائق 0')&&b.textContent.includes('حاضر اليوم')).click()")
        browser.wait("document.body.innerText.includes('لا توجد رحلات')")
        assert not browser.js("document.body.innerText.includes('أوردر #1')")
        assert _call(c, "get_expenses") == []
        browser.screenshot("32-new-business-day-no-old-trips.png")
        assert db.fetch_one("SELECT is_settled FROM delivery_trips WHERE id=?", (tid,))["is_settled"]
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_overall_cards_navbar_and_input_limits(qapp, monkeypatch):
    from test_batch_workflow_e2e import _setup
    from test_driver_business_day import _call

    monkeypatch.setenv("POS_DEV_MODE", "0")
    c, _, _, _ = _setup(qapp)
    _call(c, "logout"); _call(c, "login", {"pin": "1234"})
    name = "اسم منتج عربي طويل English123 " * 10
    _call(c, "create_product", {"name": name, "price": 50000, "category_id": 1})
    _call(c, "logout")
    shell, browser = _show(c.bridge)
    try:
        _login(browser)
        for width in (1280, 1366, 1600, 1920):
            shell.resize(width, 1000)
            browser.click("شاشة البيع (POS)")
            for tab in ("شاشة البيع (POS)", "إدارة المنتجات"):
                browser.click(tab)
                browser.wait("[...document.querySelectorAll('h4')].some(e=>e.textContent.startsWith('اسم منتج عربي'))")
                assert browser.js("""(()=>{const h=[...document.querySelectorAll('h4')].find(e=>e.textContent.startsWith('اسم منتج عربي'));
                  const card=h.parentElement.parentElement;const r=card.getBoundingClientRect();
                  return [...card.querySelectorAll('*')].every(e=>{const b=e.getBoundingClientRect();return b.left>=r.left-1&&b.right<=r.right+1&&b.top>=r.top-1&&b.bottom<=r.bottom+1});})()""")
            assert browser.js("""(()=>{const header=document.querySelector('header');
              return [...header.querySelectorAll('button')].filter(e=>e.title==='مدير النظام'||e.textContent.includes('الوردية مفتوحة')).every(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth});})()""")
            browser.screenshot(f"60-fixed-products-{width}.png")
        browser.click("منتج جديد")
        assert browser.js("document.querySelector('input[placeholder=\"0.00\"]').max") == "50000"
        browser.js("document.querySelector('button[aria-label=\"إغلاق النموذج\"]').click()")
        browser.click("إدارة المستخدمين"); browser.click("مستخدم جديد")
        assert browser.js("[...document.querySelector('[aria-label=\"رقم الصندوق\"]').options].map(e=>e.value)") == ["", "1", "2"]
        assert browser.js("document.querySelector('input[type=password]').placeholder") == "أرقام 0-9 فقط"
        browser.screenshot("61-fixed-user-slot-and-pin.png")
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_tracking_receipt_reprint_current_and_historical(qapp, monkeypatch):
    from unittest.mock import MagicMock

    from test_batch_workflow_e2e import _setup
    from test_driver_business_day import _call

    monkeypatch.setenv("POS_DEV_MODE", "0")
    c, db, _, _ = _setup(qapp)
    _call(c, "new_order", {"order_type": "takeaway"})
    _call(c, "add_item", {"product_id": 1})
    oid = _call(c, "confirm_order")["order_id"]
    c.bridge._printer.print_receipt = MagicMock(return_value=True)
    _call(c, "logout")
    shell, b = _show(c.bridge)
    try:
        _login(b, "2222")
        for width in (1280, 1920):
            shell.resize(width, 900)
            b.click("متابعة الطلبات")
            b.wait("!!document.querySelector('button[title=\"إعادة طباعة نسخة\"]')")
            b.screenshot(f"70-reprint-active-{width}.png")
        for _ in range(2):
            b.js("document.querySelector('button[title=\"إعادة طباعة نسخة\"]').click()")
            b.wait("document.querySelector('[role=status]')?.textContent.includes('تم إرسال') && !document.querySelector('button[title=\"إعادة طباعة نسخة\"]').disabled")
        assert c.bridge._printer.print_receipt.call_count == 2
        assert db.fetch_one("SELECT count(*) n FROM audit_log WHERE event_type='receipt_reprinted'")["n"] == 2
        assert b.js("document.querySelector('h2').textContent") == "متابعة الطلبات النشطة"
        c.bridge._printer.print_receipt.return_value = False
        b.js("document.querySelector('button[title=\"إعادة طباعة نسخة\"]').click()")
        b.wait("document.querySelector('[role=status]')?.textContent.includes('افحص الطابعة')")
        b.screenshot("71-reprint-printer-failure.png")
        db.execute("UPDATE orders SET status='completed',created_at='2024-01-02 12:00:00' WHERE id=?", (oid,)); db.commit()
        b.click("سجل الأوردرات")
        b.js("(()=>{const e=document.querySelector('input[type=date]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'2024-01-02');e.dispatchEvent(new Event('input',{bubbles:true}));})()")
        b.wait("!!document.querySelector('button[title=\"إعادة طباعة نسخة\"]')")
        c.bridge._printer.print_receipt.return_value = True
        b.js("document.querySelector('button[title=\"إعادة طباعة نسخة\"]').click()")
        b.wait("document.querySelector('[role=status]')?.textContent.includes('تم إرسال')")
        assert c.bridge._printer.print_receipt.call_count == 4
        shell.resize(1280, 900)
        b.screenshot("72-reprint-historical.png")
        assert not b.js("document.body.innerText.includes('PIN المدير')")
    finally:
        shell.close()
