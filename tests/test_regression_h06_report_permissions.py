"""
Regression tests — H06: financial report permissions enforced inconsistently.

Root cause:
  The "التقارير المالية" (Financial Reports) tab is hidden from cashiers in
  the frontend (App.tsx: visible=isManagerOrAbove), but the backend actions
  it calls — get_report_daily_sales and get_report_product_sales — had no
  role check at all. A cashier could call either action directly through
  the bridge and receive full gross revenue / product-sales figures,
  bypassing the UI restriction entirely.

Fix verified here:
  - Cashier calling get_report_daily_sales / get_report_product_sales →
    rejected with a manager-required error, no report data returned.
  - Manager/Admin calling the same actions → succeeds as before.
"""
from __future__ import annotations

import json

import pytest

from broast_pos.core.models.user import User, UserRole
from broast_pos.infrastructure.web_bridge.bridge import POSBridge


def _cashier() -> User:
    return User(id=2, username="cashier1", display_name="كاشير 1", role=UserRole.CASHIER, pin_hash="", is_active=True)


def _manager() -> User:
    return User(id=1, username="mgr", display_name="مدير", role=UserRole.MANAGER, pin_hash="", is_active=True)


class _StubReportsController:
    """Stands in for a real ReportsController — only presence/absence of a
    call is asserted, not report content."""

    def __init__(self):
        self.calls: list[str] = []

    def generate_daily_summary(self, target_date=None, shift_id=None):
        self.calls.append("generate_daily_summary")
        return {"gross_revenue": 12500.0}

    def get_bestsellers(self):
        self.calls.append("get_bestsellers")
        return [{"product_name": "برجر", "quantity": 10, "revenue": 700.0}]


def _make_bridge(current_user: User) -> tuple[POSBridge, _StubReportsController]:
    bridge = POSBridge.__new__(POSBridge)
    reports_ctrl = _StubReportsController()
    bridge._reports_ctrl = reports_ctrl
    bridge._current_user = current_user
    return bridge, reports_ctrl


@pytest.fixture(autouse=True)
def _public_actions_allow_reports(monkeypatch):
    # dispatch() rejects unauthenticated calls up front via _PUBLIC_ACTIONS;
    # our stub users are always "logged in" (_current_user is set), so the
    # real guard just needs _current_user truthy, which it is here.
    yield


class TestH06ReportPermissions:
    def test_cashier_cannot_get_daily_sales_report(self):
        bridge, ctrl = _make_bridge(_cashier())
        resp = json.loads(bridge.dispatch("get_report_daily_sales", json.dumps({})))
        assert resp["success"] is False, "Cashier must not receive the daily sales report"
        assert "data" not in resp
        assert ctrl.calls == [], "Report must not be generated for an unauthorized caller"

    def test_cashier_cannot_get_product_sales_report(self):
        bridge, ctrl = _make_bridge(_cashier())
        resp = json.loads(bridge.dispatch("get_report_product_sales", json.dumps({})))
        assert resp["success"] is False, "Cashier must not receive the product sales report"
        assert "data" not in resp
        assert ctrl.calls == [], "Report must not be generated for an unauthorized caller"

    def test_manager_can_get_daily_sales_report(self):
        bridge, ctrl = _make_bridge(_manager())
        resp = json.loads(bridge.dispatch("get_report_daily_sales", json.dumps({})))
        assert resp["success"] is True, f"Manager must receive the daily sales report: {resp}"
        assert resp["data"]["gross_revenue"] == 12500.0
        assert ctrl.calls == ["generate_daily_summary"]

    def test_manager_can_get_product_sales_report(self):
        bridge, ctrl = _make_bridge(_manager())
        resp = json.loads(bridge.dispatch("get_report_product_sales", json.dumps({})))
        assert resp["success"] is True, f"Manager must receive the product sales report: {resp}"
        assert resp["data"][0]["product_name"] == "برجر"
        assert ctrl.calls == ["get_bestsellers"]
