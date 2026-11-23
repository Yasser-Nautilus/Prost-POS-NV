"""Blind count errors and nested shift data must honor cashier visibility."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection


@pytest.fixture
def setup():
    app = QCoreApplication.instance() or QCoreApplication(["blind-count-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)

    def call(action, payload=None, ok=True):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"] is ok, result
        return result.get("data") if ok else result["error"]

    call("login", {"pin": "1234"})
    call("open_shift")
    user = bridge._auth.create_user("cashier", "Cashier", UserRole.CASHIER, "5678", cashier_slot=1)
    recipient = bridge._auth.create_user("receiver", "Receiver", UserRole.CASHIER, "6789", cashier_slot=2)
    call("logout")
    call("login", {"pin": "5678"})
    session = call("session.open", {"station": "ALL", "opening_float_egp": 500})
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    oid = call("confirm_order")["order_id"]
    call("complete_payment", {"order_id": oid, "payment_method": "cash", "amount_paid": 70, "keep_open": True})
    yield bridge, db, call, session["id"], user.id, recipient.id
    DatabaseConnection.reset()


@pytest.mark.parametrize("action", ["session.close", "session.handover"])
def test_rejected_count_never_discloses_difference_or_expected_cash(setup, action):
    _, db, call, sid, _, recipient = setup
    errors = []
    before = db.fetch_one("SELECT count(*) n FROM cash_ledger")["n"]
    for counted in (0, 100, 200):
        payload = {"session_id": sid, "from_session_id": sid,
                   "to_user_id": recipient, "counted_cash_egp": counted}
        error = call(action, payload, ok=False)
        errors.append(error)
        assert not any(char.isdigit() for char in error)
        assert "570" not in error
    assert len(set(errors)) == 1
    assert db.fetch_one("SELECT is_open FROM cashier_sessions WHERE id=?", (sid,))["is_open"] == 1
    assert db.fetch_one("SELECT count(*) n FROM cash_ledger")["n"] == before


def test_cashier_summary_has_only_permitted_fields_and_manager_keeps_breakdown(setup):
    _, _, call, _, _, _ = setup
    summary = call("get_shift_summary")
    assert set(summary) == {"total_expenses", "pending_delivery", "pending_dinein", "pending_kitchen", "order_count"}
    assert summary["order_count"] == 1
    call("logout")
    call("login", {"pin": "1234"})
    privileged = call("get_shift_summary")
    assert privileged["total_sales"] == 70
    assert privileged["cash_sales"] == 70
    assert privileged["expected_cash"] == 570
    assert privileged["order_breakdown"]["takeaway"]["revenue"] == 70


def test_committed_count_reveals_reconciliation_after_close(setup):
    _, db, call, sid, _, _ = setup
    closed = call("session.close", {"session_id": sid, "counted_cash_egp": 570})
    assert closed["is_open"] is False
    assert closed["expected_cash_egp"] == 570
    assert closed["variance_egp"] == 0
    assert db.fetch_one("SELECT counted_cash_pt FROM cashier_sessions WHERE id=?", (sid,))["counted_cash_pt"] == 57000


def test_privileged_approved_variance_still_closes(setup):
    _, _, call, sid, _, _ = setup
    call("logout")
    call("login", {"pin": "1234"})
    closed = call("session.close", {"session_id": sid, "counted_cash_egp": 470,
                                    "variance_reason": "Manager verified shortage", "manager_pin": "1234"})
    assert closed["expected_cash_egp"] == 570
    assert closed["variance_egp"] == -100
    assert closed["is_open"] is False
