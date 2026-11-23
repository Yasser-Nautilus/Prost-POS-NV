# ruff: noqa: F811
"""Regression tests for the QA findings: users-list guard, duplicate zone names,
same-user shift transfer, expense cap."""
from __future__ import annotations

from test_e2e_user_flows import (  # noqa: F401
    POSUserClient,
    _build_test_bridge,
    qapp,
    reset_db_singleton,
)


def _setup(qapp):
    """One bridge (singleton DB): admin, manager 5555 and cashier 2222 exist."""
    bridge, db = _build_test_bridge(qapp)
    c = POSUserClient(bridge)
    assert c.call("login", {"pin": "1234"})["success"]
    c.call("create_user", {"username": "m", "display_name": "م", "role": "manager", "pin": "5555", "cashier_slot": 1})
    c.call("create_user", {"username": "k", "display_name": "ك", "role": "cashier", "pin": "2222", "cashier_slot": 2})
    return c


def _as(c, pin):
    c.call("logout")
    assert c.call("login", {"pin": pin})["success"]
    return c


def test_users_management_is_admin_only(qapp):
    c = _setup(qapp)
    assert c.call("get_users_management")["success"]
    for pin in ("5555", "2222"):  # manager, cashier
        assert _as(c, pin).call("get_users_management")["success"] is False


def test_duplicate_zone_name_rejected_on_create_and_rename(qapp):
    c = _as(_setup(qapp), "5555")
    a = c.call("create_zone", {"name": "حي الورد", "delivery_fee": 20})
    assert a["success"]
    assert not c.call("create_zone", {"name": "حي الورد", "delivery_fee": 30})["success"]
    assert not c.call("create_zone", {"name": "  حي   الورد ", "delivery_fee": 30})["success"]
    b = c.call("create_zone", {"name": "حي النور", "delivery_fee": 10})["data"]
    assert not c.call("update_zone", {"zone_id": b["id"], "name": "حي الورد"})["success"]
    # keeping its own name while changing the fee is fine
    assert c.call("update_zone", {"zone_id": b["id"], "name": "حي النور", "delivery_fee": 12})["success"]


def test_transfer_to_same_user_rejected(qapp):
    c = _as(_setup(qapp), "5555")
    assert c.call("open_shift")["success"]
    me = c.call("get_active_shift")["data"]["opened_by"]
    r = c.call("transfer_shift", {"from_user_id": me, "to_user_id": me, "manager_pin": "5555"})
    assert r["success"] is False


def test_expense_cap(qapp):
    c = _as(_setup(qapp), "5555")
    day = c.call("open_shift")["data"]
    me = c.call("get_active_shift")["data"]["opened_by"]
    assert c.call("session.open", {"day_id": day["id"], "user_id": me, "station": "ALL",
                                   "opening_float_egp": 100.0})["success"]
    assert c.call("add_expense", {"amount": 50000, "category": "supplies", "description": "x"})["success"]
    r = c.call("add_expense", {"amount": 50000.01, "category": "supplies", "description": "x"})
    assert r["success"] is False
    assert not c.call("add_expense", {"amount": 99999999, "category": "other", "description": "x"})["success"]
