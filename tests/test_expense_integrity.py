"""Expense, cash-ledger outflow and authenticated actor are inseparable."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection


@pytest.fixture
def setup():
    app = QCoreApplication.instance() or QCoreApplication(["expense-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)

    def call(action, payload=None, ok=True):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"] is ok, result
        return result.get("data")

    call("login", {"pin": "1234"})
    call("open_shift")
    yield bridge, db, call
    DatabaseConnection.reset()


def expense(call, ok=True, **extra):
    return call("add_expense", {"amount": 25.50, "description": "Supplies", "category": "supplies", **extra}, ok=ok)


def assert_no_expense(db):
    assert db.fetch_one("SELECT count(*) n FROM cash_transactions")["n"] == 0
    assert db.fetch_one("SELECT count(*) n FROM cash_ledger WHERE entry_type='EXPENSE'")["n"] == 0
    assert db.fetch_one("SELECT count(*) n FROM audit_log WHERE event_type='expense_added'")["n"] == 0
    assert not db.raw_connection.in_transaction


def test_missing_drawer_rejects_expense_and_later_customer_save_cannot_rescue_it(setup):
    _, db, call = setup
    expense(call, ok=False)
    call("create_customer", {"name": "Unrelated", "phone": "01012345678"})
    assert_no_expense(db)


@pytest.mark.parametrize("role", [UserRole.CASHIER, UserRole.ADMIN])
def test_actor_comes_from_login_not_payload(setup, role):
    bridge, db, call = setup
    actor = bridge._auth.create_user(
        "actor", "Expense actor", role, "5678", cashier_slot=1,
        allow_second_admin=True,  # the seeded admin already exists
    )
    call("logout")
    call("login", {"pin": "5678"})
    session = call("session.open", {"station": "ALL", "opening_float_egp": 100})
    saved = expense(call, user_id=1)
    transaction = db.fetch_one("SELECT * FROM cash_transactions WHERE id=?", (saved["id"],))
    entry = db.fetch_one("SELECT * FROM cash_ledger WHERE expense_id=?", (saved["id"],))
    audit = db.fetch_one("SELECT * FROM audit_log WHERE event_type='expense_added'")
    assert transaction["user_id"] == actor.id
    assert entry["actor_id"] == actor.id
    assert audit["user_id"] == actor.id
    assert entry["session_id"] == session["id"] and entry["amount_pt"] == -2550
    assert db.fetch_one("SELECT SUM(amount_pt) n FROM cash_ledger")["n"] == 7450


@pytest.mark.parametrize("component", ["ledger", "audit"])
def test_failed_ledger_or_audit_rolls_back_everything(setup, component):
    bridge, db, call = setup
    call("session.open", {"station": "ALL", "opening_float_egp": 100})
    target = bridge._financial._ledger if component == "ledger" else bridge._financial._audit
    method = "append" if component == "ledger" else "log"
    with patch.object(target, method, side_effect=sqlite3.IntegrityError("injected")):
        expense(call, ok=False)
    call("create_customer", {"name": "Unrelated", "phone": "01012345679"})
    assert_no_expense(db)
    assert db.fetch_one("SELECT SUM(amount_pt) n FROM cash_ledger")["n"] == 10000


def test_existing_drawer_preference_is_preserved(setup):
    _, db, call = setup
    delivery = call("session.open", {"station": "DELIVERY", "opening_float_egp": 0})
    counter = call("session.open", {"station": "COUNTER", "opening_float_egp": 0})
    expense(call)
    entry = db.fetch_one("SELECT * FROM cash_ledger WHERE entry_type='EXPENSE'")
    assert entry["session_id"] == counter["id"] != delivery["id"]


@pytest.mark.parametrize("missing", ["_ledger", "_sessions"])
def test_partial_accounting_wiring_fails_closed(setup, missing):
    bridge, db, call = setup
    with patch.object(bridge._financial, missing, None):
        expense(call, ok=False)
    assert_no_expense(db)


def test_closed_drawer_is_not_reused(setup):
    _, db, call = setup
    session = call("session.open", {"station": "ALL", "opening_float_egp": 0})
    call("session.close", {"session_id": session["id"], "counted_cash_egp": 0})
    expense(call, ok=False)
    assert_no_expense(db)
