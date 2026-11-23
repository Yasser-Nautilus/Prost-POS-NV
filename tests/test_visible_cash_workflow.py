"""Rendered App -> QWebChannel -> POSBridge -> SQLite cash workflow.

Run after `cd frontend && npm ci && npm run build`, with PyQt6-WebEngine
installed: POS_RUN_RENDERED_TESTS=1 QT_QPA_PLATFORM=offscreen
 QTWEBENGINE_DISABLE_SANDBOX=1 pytest -q
 tests/test_visible_cash_workflow.py. Uses an in-memory DB, never real hardware.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
if os.environ.get("POS_RUN_RENDERED_TESTS") != "1":
    pytest.skip("Run separately with POS_RUN_RENDERED_TESTS=1 after building frontend", allow_module_level=True)
pytest.importorskip("PyQt6.QtWebEngineWidgets")
from PyQt6.QtCore import QEventLoop, Qt, QTimer
from PyQt6.QtWidgets import QApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.ui.web_shell import WebShell

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication(["cash-workflow-test"])


class Browser:
    def __init__(self, shell):
        self.shell = shell
        self.page = shell.web_view.page()

    def js(self, script):
        result = []
        loop = QEventLoop()
        self.page.runJavaScript(script, lambda value: (result.append(value), loop.quit()))
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        assert result, "JavaScript timed out"
        return result[0]

    def wait(self, expression):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.js(expression):
                return
            loop = QEventLoop()
            QTimer.singleShot(25, loop.quit)
            loop.exec()
        pytest.fail(f"UI condition timed out: {expression}; text={self.js('document.body.innerText')}")

    def click(self, text):
        literal = json.dumps(text)
        self.wait(f"[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==={literal}&&!b.disabled)")
        self.js(f"[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==={literal}).click()")

    def field(self, label, value, select=False):
        # Use the native setter so React receives an ordinary DOM input event.
        selector = json.dumps(f'[aria-label="{label}"]')
        proto = "HTMLSelectElement" if select else "HTMLInputElement"
        self.js(f"""(()=>{{const e=document.querySelector({selector});
          Object.getOwnPropertyDescriptor({proto}.prototype,'value').set.call(e,{json.dumps(value)});
          e.dispatchEvent(new Event('{'change' if select else 'input'}',{{bubbles:true}}));}})()""")

    def screenshot(self, name):
        directory = os.environ.get("POS_UI_EVIDENCE_DIR")
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            loop = QEventLoop()
            QTimer.singleShot(600, loop.quit)
            loop.exec()
            assert self.shell.grab().save(str(Path(directory) / name))


@pytest.mark.parametrize("existing_day,conflict", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("cashier", [False, True])
def test_visible_open_shift_to_cash_payment(qapp, monkeypatch, existing_day, conflict, cashier):
    if not (ROOT / "frontend/dist/index.html").exists():
        pytest.skip("Build the frontend first")
    monkeypatch.setenv("POS_DEV_MODE", "0")
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(qapp)
    if cashier:
        from broast_pos.core.models.user import UserRole
        bridge._auth.create_user("ui_cashier", "UI cashier", UserRole.CASHIER, "5678", cashier_slot=1)
    if existing_day:
        assert json.loads(bridge.dispatch("login", json.dumps({"pin": "1234"})))["success"]
        assert json.loads(bridge.dispatch("open_shift", "{}"))["success"]
        if conflict:
            from broast_pos.core.models.user import UserRole
            other = bridge._auth.create_user("other_drawer", "Other drawer", UserRole.CASHIER, "6789", cashier_slot=2)
            assert json.loads(bridge.dispatch("session.open", json.dumps({
                "station": "COUNTER", "opening_float_egp": 50, "user_id": other.id,
            })))["success"]
        bridge.dispatch("logout", "{}")
    shell = WebShell(bridge)
    shell.setWindowState(Qt.WindowState.WindowNoState)
    shell.resize(1440, 1000)
    shell.show()
    browser = Browser(shell)
    try:
        # Suppress only native informational alerts, not bridge or application code.
        browser.wait("document.querySelectorAll('button').length > 0")
        browser.js("window.__alerts=[]; window.alert=(s)=>window.__alerts.push(s)")
        for digit in ("5678" if cashier else "1234"):
            browser.click(digit)
        browser.click("تأكيد PIN")
        browser.click("الوردية مفتوحة" if existing_day else "الوردية مغلقة")
        browser.wait("!!document.querySelector('[aria-label=\"محطة الدرج\"]')")
        # No guessed station or float: opening is disabled until both are supplied.
        opening_label = "فتح درج الكاشير" if existing_day else "فتح يوم العمل ودرج الكاشير"
        browser.wait(f"[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==={json.dumps(opening_label)})")
        assert browser.js(f"[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==={json.dumps(opening_label)}).disabled")
        browser.field("محطة الدرج", "COUNTER", select=True)
        browser.field("النقد الموجود بالدرج عند الفتح", "125.50")
        browser.wait("document.querySelector('[aria-label=\"النقد الموجود بالدرج عند الفتح\"]').value==='125.50'")
        browser.screenshot("01-opening.png")
        browser.click(opening_label)
        if conflict:
            browser.wait("!!document.querySelector('[role=alert]')")
            assert "لم يتم فتح درجك" in browser.js("document.querySelector('[role=alert]').textContent")
            assert db.fetch_one("SELECT count(*) c FROM shifts")["c"] == 1
            assert db.fetch_one("SELECT count(*) c FROM cashier_sessions")["c"] == 1
            assert db.fetch_one("SELECT opening_float_pt FROM cashier_sessions")["opening_float_pt"] == 5000
            browser.screenshot("04-conflict.png")
            return
        browser.wait("document.body.innerText.includes('درجك مفتوح')")
        session = db.fetch_one("SELECT * FROM cashier_sessions WHERE is_open=1")
        assert session["station"] == "COUNTER"
        assert session["opening_float_pt"] == 12550
        browser.screenshot("02-open.png")
        # Exercise visible expense form through the same production channel.
        browser.js("""(()=>{for(const [selector,value] of [["input[type=number]","10.25"],
          ["form input[type=text]","UI expense"]]){const e=document.querySelector(selector);
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,value);
          e.dispatchEvent(new Event('input',{bubbles:true}));}})()""")
        browser.click("تسجيل وحفظ المصروف")
        browser.wait("document.body.innerText.includes('UI expense')")
        outflow = db.fetch_one("SELECT * FROM cash_ledger WHERE entry_type='EXPENSE'")
        assert outflow["amount_pt"] == -1025 and outflow["session_id"] == session["id"]
        assert outflow["actor_id"] == session["user_id"]
        assert not browser.js("!!document.querySelector('[aria-label=\"محطة الدرج\"]')")
        assert db.fetch_one("SELECT count(*) c FROM shifts")["c"] == 1
        # Close the shift dialog through its header control, then use normal POS.
        browser.js("[...document.querySelectorAll('h3')].find(e=>e.textContent.includes('إدارة وردية الصندوق')).parentElement.querySelector('button').click()")
        browser.click("تيك أواي")
        browser.wait("[...document.querySelectorAll('h4')].some(b=>b.textContent==='تشيكن فرايز حار')")
        browser.js("[...document.querySelectorAll('h4')].find(b=>b.textContent==='تشيكن فرايز حار').parentElement.click()")
        # Park via the visible button, log out, log in, then restore via the modal.
        browser.click("تعليق")
        browser.wait("document.body.innerText.includes('استرجاع طلب معلّق (1)')")
        assert db.fetch_one("SELECT count(*) n FROM parked_order_drafts")["n"] == 1
        assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 0
        browser.js("document.querySelector('[title=\"تسجيل الخروج\"]').click()")
        browser.click("تأكيد")
        browser.wait("document.body.innerText.includes('تأكيد PIN')")
        for digit in ("5678" if cashier else "1234"):
            browser.click(digit)
        browser.click("تأكيد PIN")
        browser.click("استرجاع طلب معلّق (1)")
        browser.wait("document.body.innerText.includes('1 عناصر')")
        browser.screenshot("06-recovered-parking.png")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('1 عناصر')).click()")
        browser.wait("document.body.innerText.includes('تأكيد ودفع الفاتورة')")
        assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 0
        browser.click("تأكيد ودفع الفاتورة")
        browser.wait("document.body.innerText.includes('تأكيد الدفع')")
        # Empty and explicit zero must not silently pay the full amount.
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('إنهاء وتأكيد الدفع')).click()")
        browser.wait("window.__alerts.some(s=>s.includes('أدخل المبلغ النقدي'))")
        browser.click("0")
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('إنهاء وتأكيد الدفع')).click()")
        browser.wait("window.__alerts.some(s=>s.includes('أقل من إجمالي'))")
        assert db.fetch_one("SELECT is_paid FROM orders")["is_paid"] == 0
        assert db.fetch_one("SELECT count(*) n FROM cash_ledger WHERE entry_type='SALE_CASH'")["n"] == 0
        browser.screenshot("09-zero-not-paid.png")
        browser.click("مسح")
        # Explicit cash amount, no reliance on the empty/zero fallback.
        for digit in "100":
            browser.click(digit)
        browser.js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('إنهاء وتأكيد الدفع')).click()")
        browser.wait("window.__alerts.some(s=>s.includes('تم تسجيل الدفع'))")
        sale = db.fetch_one("SELECT * FROM cash_ledger WHERE entry_type='SALE_CASH'")
        assert sale["session_id"] == session["id"]
        assert sale["amount_pt"] == 7000
        assert db.fetch_one("SELECT is_paid FROM orders")["is_paid"] == 1
        assert db.fetch_one("SELECT count(*) c FROM cashier_sessions")["c"] == 1
        browser.screenshot("03-paid.png")
        if not cashier:
            browser.click("التقارير المالية")
            browser.wait("document.body.innerText.includes('المدفوعات والمبالغ غير المدفوعة')")
            browser.screenshot("05-reports.png")
    finally:
        shell.close()
        DatabaseConnection.reset()


def test_visible_occupied_table_opens_existing_order_for_append(qapp, monkeypatch):
    monkeypatch.setenv("POS_DEV_MODE", "0")
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(qapp)
    shell = WebShell(bridge)
    shell.setWindowState(Qt.WindowState.WindowNoState)
    shell.resize(1440, 1000)
    shell.show()
    browser = Browser(shell)
    try:
        browser.wait("document.querySelectorAll('button').length > 0")
        browser.js("window.__alerts=[];window.alert=(s)=>window.__alerts.push(s)")
        for digit in "1234":
            browser.click(digit)
        browser.click("تأكيد PIN")
        browser.click("الوردية مغلقة")
        browser.wait("!!document.querySelector('[aria-label=\"محطة الدرج\"]')")
        browser.field("محطة الدرج", "COUNTER", select=True)
        browser.field("النقد الموجود بالدرج عند الفتح", "0")
        browser.click("فتح يوم العمل ودرج الكاشير")
        browser.wait("document.body.innerText.includes('درجك مفتوح')")
        browser.js("[...document.querySelectorAll('h3')].find(e=>e.textContent.includes('إدارة وردية الصندوق')).parentElement.querySelector('button').click()")
        browser.click("صالة")
        browser.wait("document.body.innerText.includes('اختيار رقم الطاولة')")
        table_button = "[...document.querySelectorAll('button')].find(b=>b.querySelector('span')?.textContent==='طاولة'&&b.querySelectorAll('span')[1]?.textContent==='4')"
        browser.js(f"{table_button}.click()")
        browser.click("تأكيد الطاولة")
        browser.wait("[...document.querySelectorAll('h4')].some(e=>e.textContent==='تشيكن فرايز حار')")
        browser.js("[...document.querySelectorAll('h4')].find(e=>e.textContent==='تشيكن فرايز حار').parentElement.click()")
        browser.click("تأكيد الطلب")
        browser.wait("window.__alerts.some(s=>s.includes('بنجاح'))")
        browser.click("صالة")
        browser.wait("document.body.innerText.includes('اختيار رقم الطاولة')")
        browser.wait(f"{table_button}.textContent.includes('#')")
        browser.screenshot("07-occupied-table.png")
        browser.js(f"{table_button}.click()")
        browser.wait("document.body.innerText.includes('حفظ التعديلات')")
        browser.js("[...document.querySelectorAll('h4')].find(e=>e.textContent==='تشيكن فرايز حار').parentElement.click()")
        browser.click("حفظ التعديلات")
        browser.wait("window.__alerts.some(s=>s.includes('تم حفظ تعديلات'))")
        assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
        assert db.fetch_one("SELECT sum(quantity) n FROM order_items")["n"] == 2
        assert db.fetch_one("SELECT table_no,total FROM orders")["table_no"] == 4
    finally:
        shell.close()
        DatabaseConnection.reset()


@pytest.fixture(scope="module")
def history_page(tmp_path_factory):
    import subprocess
    output = tmp_path_factory.mktemp("history-ui")
    subprocess.run(["npm", "exec", "vite", "build", "--", "--config", "vite.history-test.config.ts",
                    "--outDir", str(output), "--emptyOutDir"], cwd=ROOT / "frontend", check=True,
                   capture_output=True, text=True)
    pages = list(output.rglob("index.html"))
    assert len(pages) == 1
    return pages[0]


@pytest.mark.parametrize("lookup", ["phone", "id", "missing", "invalid"])
def test_rendered_customer_history_real_lookup(qapp, monkeypatch, history_page, lookup):
    from PyQt6.QtCore import QUrl
    monkeypatch.setenv("POS_DEV_MODE", "0")
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(qapp)
    def call(action, payload=None):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"], result
        return result.get("data")
    call("login", {"pin": "1234"})
    customer = call("create_customer", {"name": "عميل الاختبار", "phone": "01012345678"})
    zone = call("get_active_zones")[0]
    address = call("add_customer_address", {"customer_id": customer["id"], "street_name": "شارع محفوظ", "zone_id": zone["id"]})
    call("open_shift")
    call("new_order", {"order_type": "delivery"})
    call("add_item", {"product_id": 1})
    call("set_customer_info", {"customer_id": customer["id"], "phone": customer["phone"],
          "name": customer["name"], "address_id": address["id"], "address": address["street_name"]})
    call("confirm_order")
    # Address removal must not remove the historical address shown by this modal.
    call("delete_customer_address", {"customer_id": customer["id"], "address_id": address["id"]})
    shell = WebShell(bridge)
    shell.setWindowState(Qt.WindowState.WindowNoState)
    shell.resize(1440, 1000)
    fragment = {"phone": "phone=01012345678", "id": f"customerId={customer['id']}",
                "missing": "phone=01099999999", "invalid": "phone=123"}[lookup]
    url = QUrl.fromLocalFile(str(history_page))
    url.setFragment(fragment)
    shell.web_view.load(url)
    shell.show()
    browser = Browser(shell)
    try:
        if lookup in ("phone", "id"):
            browser.wait("document.body.innerText.includes('طلب #1')")
            text = browser.js("document.body.innerText")
            assert "عميل الاختبار" in text and "شارع محفوظ" in text
            browser.screenshot("08-customer-history.png")
            browser.click("الإحصائيات")
            browser.wait("document.body.innerText.includes('إجمالي الطلبات')")
            assert "إجراء غير معروف" not in browser.js("document.body.innerText")
        elif lookup == "missing":
            browser.wait("document.body.innerText.includes('لم يتم العثور على العميل')")
        else:
            browser.wait("document.body.innerText.includes('11 رقم')")
        assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
    finally:
        shell.close()
        DatabaseConnection.reset()


@pytest.mark.parametrize("pin", ["9876543210987654", "legacyPass9"])
def test_visible_long_and_legacy_text_pin_login_and_override(qapp, monkeypatch, history_page, pin):
    from PyQt6.QtCore import QUrl

    from broast_pos.core.models.user import UserRole
    monkeypatch.setenv("POS_DEV_MODE", "0")
    DatabaseConnection.reset()
    bridge, _ = _build_test_bridge(qapp)
    bridge._auth.create_user("long_ui", "Long UI", UserRole.MANAGER, pin)
    shell = WebShell(bridge)
    shell.setWindowState(Qt.WindowState.WindowNoState)
    shell.resize(1440, 1000)
    shell.show()
    browser = Browser(shell)
    try:
        browser.wait("!!document.querySelector('[aria-label=\"رمز PIN\"]')")
        if pin.isdigit():
            for digit in pin:
                browser.click(digit)
        else:
            browser.field("رمز PIN", pin)
        assert browser.js("document.querySelector('[aria-label=\"رمز PIN\"]').value.length") == len(pin)
        browser.screenshot("10-long-pin.png")
        browser.click("تأكيد PIN")
        browser.wait("document.body.innerText.includes('Long UI')")
        url = QUrl.fromLocalFile(str(history_page))
        url.setFragment("manager=1")
        shell.web_view.load(url)
        browser.wait("!!document.querySelector('[aria-label=\"رمز PIN للمدير\"]')")
        if pin.isdigit():
            for digit in pin:
                browser.click(digit)
        else:
            browser.field("رمز PIN للمدير", pin)
        browser.click("تأكيد الرمز")
        browser.wait("document.title==='manager-approved'")
    finally:
        shell.close()
        DatabaseConnection.reset()
