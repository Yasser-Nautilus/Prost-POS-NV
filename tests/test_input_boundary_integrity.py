"""Malformed unit counts and cash must fail without creating accounting state."""
from __future__ import annotations

import json
import sqlite3

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.order import OrderItem
from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["input-integrity"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)
    def call(action, payload=None, ok=True):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"] is ok, result
        return result.get("data")
    call("login", {"pin": "1234"})
    call("open_shift")
    session = call("session.open", {"station": "COUNTER", "opening_float_egp": 0})
    yield bridge, db, call, session
    DatabaseConnection.reset()


@pytest.mark.parametrize("quantity", [-1, 0, .5, 1.5, True, False, "2", None, float("nan"), float("inf")])
def test_invalid_add_count_is_rejected_before_mutation(env, quantity):
    bridge, db, call, _ = env
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1, "quantity": quantity}, ok=False)
    assert bridge._order_ctrl.current_order.items == []
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 0


@pytest.mark.parametrize("delta", [.5, True, "1", None, float("nan")])
def test_quantity_delta_must_be_integer_without_mutation(env, delta):
    bridge, _, call, _ = env
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    call("change_item_quantity", {"index": 0, "delta": delta}, ok=False)
    assert bridge._order_ctrl.current_order.items[0].quantity == 1


def test_service_and_repository_cannot_save_fractional_units(env):
    bridge, db, call, _ = env
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    bridge._order_ctrl.current_order.items[0].quantity = 1.5
    call("confirm_order", ok=False)
    bridge._order_ctrl.current_order.items[0].quantity = 1
    oid = call("confirm_order")["order_id"]
    repo = bridge._order_svc._orders
    saved = repo.get_by_id(oid)
    saved.items[0].quantity = .5
    with pytest.raises(sqlite3.IntegrityError):
        repo.save(saved)
    assert repo.get_by_id(oid).items[0].quantity == 1
    with pytest.raises(ValueError):
        bridge._order_svc.amend_order(oid, [OrderItem(1, "Item", .5, 70)], [])
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1


@pytest.mark.parametrize("counted", [-1, -.001, float("nan"), float("inf"), None, True, "0"])
def test_invalid_cash_count_rejected_by_bridge_with_no_side_effect(env, counted):
    _, db, call, session = env
    before = db.fetch_one("SELECT count(*) n FROM cash_ledger")["n"]
    call("session.close", {"session_id": session["id"], "counted_cash_egp": counted,
                          "variance_reason": "test", "manager_pin": "1234"}, ok=False)
    assert db.fetch_one("SELECT is_open FROM cashier_sessions WHERE id=?", (session["id"],))["is_open"] == 1
    assert db.fetch_one("SELECT count(*) n FROM cash_ledger")["n"] == before


@pytest.mark.parametrize("counted", [-1, .5, True, float("nan")])
def test_service_count_requires_nonnegative_integer_piasters(env, counted):
    bridge, _, _, session = env
    with pytest.raises(ValueError):
        bridge._session_ctrl._svc.close_session(session["id"], counted, 1,
                                               manager_pin="1234", variance_reason="test")


def test_explicit_zero_count_is_valid_and_missing_count_is_not(env):
    _, _, call, session = env
    call("session.close", {"session_id": session["id"]}, ok=False)
    assert call("session.close", {"session_id": session["id"], "counted_cash_egp": 0})["is_open"] is False


@pytest.mark.parametrize("amount", [0, -1, float("nan"), float("inf"), None, True])
def test_invalid_cash_payment_never_marks_paid(env, amount):
    _, db, call, _ = env
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    oid = call("confirm_order")["order_id"]
    call("complete_payment", {"order_id": oid, "payment_method": "cash", "amount_paid": amount}, ok=False)
    assert db.fetch_one("SELECT is_paid FROM orders")["is_paid"] == 0
    assert db.fetch_one("SELECT count(*) n FROM cash_ledger WHERE entry_type='SALE_CASH'")["n"] == 0


@pytest.mark.parametrize("pin", ["987654", "9876543210987654", "legacyPass9"])
def test_existing_long_and_text_pins_remain_valid_for_login_override_and_update(env, pin):
    bridge, _, call, _ = env
    user = bridge._auth.create_user("long_pin", "Long PIN", UserRole.MANAGER, pin)
    call("logout")
    assert call("login", {"pin": pin})["id"] == user.id
    assert call("verify_manager_pin", {"pin": pin})["id"] == user.id
    bridge._auth.update_user(user.id, pin=pin + "0")
    call("logout")
    assert call("login", {"pin": pin + "0"})["id"] == user.id
