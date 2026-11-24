# ruff: noqa: F811
"""Overall QA regressions: prices and cashier slots fail before persistence."""
from __future__ import annotations

import pytest
from test_batch_workflow_e2e import _setup
from test_driver_business_day import _call
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401


@pytest.mark.parametrize("price", [-1, 50000.01, 1e20, float("inf"), float("-inf"), float("nan"), True, "bad"])
@pytest.mark.parametrize("update", [False, True])
def test_bad_product_price_rejected_with_clear_message(qapp, price, update):
    c, db, _, _ = _setup(qapp)
    _call(c, "logout"); _call(c, "login", {"pin": "1234"})
    before = [tuple(r) for r in db.fetch_all("SELECT * FROM products ORDER BY id")]
    payload = {"price": price, "name": "Invalid", "category_id": 1}
    if update:
        payload["product_id"] = 1
    result = c.call("update_product" if update else "create_product", payload)
    assert not result["success"] and "50,000" in result["error"]
    assert before == [tuple(r) for r in db.fetch_all("SELECT * FROM products ORDER BY id")]


@pytest.mark.parametrize("price", [0, .5, 49999.5, 50000])
def test_valid_price_boundaries_create_and_update(qapp, price):
    c, _, _, _ = _setup(qapp)
    _call(c, "logout"); _call(c, "login", {"pin": "1234"})
    product = _call(c, "create_product", {"price": price, "name": "Valid", "category_id": 1})
    assert product["price"] == price
    assert _call(c, "update_product", {"product_id": product["id"], "price": price})["price"] == price


@pytest.mark.parametrize("slot", [0, 3, 99, 1.5, "1", True, False])
@pytest.mark.parametrize("update", [False, True])
def test_bad_cashier_slot_rejected_without_partial_changes(qapp, slot, update):
    c, db, _, _ = _setup(qapp)
    _call(c, "logout"); _call(c, "login", {"pin": "1234"})
    before = [tuple(r) for r in db.fetch_all("SELECT * FROM users ORDER BY id")]
    payload = {"cashier_slot": slot, "username": "invalid", "display_name": "Invalid", "role": "cashier", "pin": "9999"}
    if update:
        payload["user_id"] = db.fetch_one("SELECT id FROM users WHERE username='sara'")["id"]
    result = c.call("update_user" if update else "create_user", payload)
    assert not result["success"] and "1 أو 2" in result["error"]
    assert before == [tuple(r) for r in db.fetch_all("SELECT * FROM users ORDER BY id")]


def test_price_change_preserves_existing_order_snapshot(qapp):
    c, db, _, _ = _setup(qapp)
    _call(c, "new_order", {"order_type": "takeaway"})
    _call(c, "add_item", {"product_id": 1})
    oid = _call(c, "confirm_order")["order_id"]
    before = dict(db.fetch_one("SELECT total,subtotal FROM orders WHERE id=?", (oid,)))
    _call(c, "logout"); _call(c, "login", {"pin": "1234"})
    _call(c, "update_product", {"product_id": 1, "price": 50000})
    assert dict(db.fetch_one("SELECT total,subtotal FROM orders WHERE id=?", (oid,))) == before
