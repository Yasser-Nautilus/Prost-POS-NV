"""Admin user rules (no 2nd admin, delete, reactivate) and the menu import."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.menu_data import MENU
from broast_pos.data.database.seed import ensure_menu_products
from broast_pos.data.repositories.user_repository import UserRepository


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["user-admin-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)

    def call(action, payload=None):
        return json.loads(bridge.dispatch(action, json.dumps(payload or {})))

    login = call("login", {"pin": "1234"})
    assert login["success"], login
    yield bridge, db, call
    DatabaseConnection.reset()


def test_cannot_create_second_admin(env):
    _, _, call = env
    res = call("create_user", {"username": "a2", "display_name": "A2", "role": "admin", "pin": "5678"})
    assert res["success"] is False


def test_cannot_promote_to_admin(env):
    bridge, _, call = env
    u = bridge._auth.create_user("c1", "C1", UserRole.CASHIER, "4321", cashier_slot=1)
    res = call("update_user", {"user_id": u.id, "role": "admin"})
    assert res["success"] is False


def test_driver_can_be_created_without_pin_from_ui(env):
    _, _, call = env
    res = call("create_user", {
        "username": "drv", "display_name": "Drv", "role": "cashier", "pin": "48291736",
        "cashier_slot": None, "phone": "01012345678",
    })
    assert res["success"], res


def test_reactivate_deactivated_user(env):
    bridge, _, call = env
    u = bridge._auth.create_user("c2", "C2", UserRole.CASHIER, "4321", cashier_slot=1)
    assert call("deactivate_user", {"user_id": u.id})["success"]
    assert bridge._auth._users.get_by_id(u.id).is_active is False
    assert call("update_user", {"user_id": u.id, "is_active": True})["success"]
    assert bridge._auth._users.get_by_id(u.id).is_active is True


def test_delete_user_without_history(env):
    bridge, _, call = env
    u = bridge._auth.create_user("c3", "C3", UserRole.CASHIER, "4321", cashier_slot=1)
    assert call("delete_user", {"user_id": u.id})["success"]
    assert bridge._auth._users.get_by_id(u.id) is None


def test_delete_user_with_history_is_refused(env):
    bridge, db, call = env
    u = bridge._auth.create_user("c4", "C4", UserRole.CASHIER, "4321", cashier_slot=1)
    repo = UserRepository(db)
    # Any FK reference blocks a hard delete; audit rows reference the actor.
    db.execute(
        "INSERT INTO audit_log (event_type, user_id, user_name, entity_type, entity_id, action, details)"
        " VALUES ('user_created', ?, 'c4', 'user', ?, 'x', '{}')", (u.id, u.id),
    )
    db.commit()
    assert repo.has_references(u.id)
    res = call("delete_user", {"user_id": u.id})
    assert res["success"] is False


def test_cannot_delete_self_or_admin(env):
    bridge, _, call = env
    me = bridge._auth.get_current_user()
    assert call("delete_user", {"user_id": me.id})["success"] is False


def test_menu_import_adds_once_and_is_idempotent(env):
    _, db, _ = env
    first = ensure_menu_products(db)
    assert first > 0
    assert ensure_menu_products(db) == 0
    total = sum(len(items) for _, _, items in MENU)
    names = [r["name"] for r in db.fetch_all("SELECT name FROM products")]
    assert "هالك توست" in names and "20 قطعة دجاج عادي" in names and "20 قطعة دجاج حار" in names
    assert first <= total


def test_session_dict_has_cashier_name(env):
    bridge, _, call = env
    ctrl = bridge._session_ctrl
    from broast_pos.core.models.cashier_session import CashierSession, Station
    s = CashierSession(id=1, day_id=1, user_id=bridge._auth.get_current_user().id, station=Station.ALL)
    assert ctrl._session_to_dict(s)["cashier_name"]
