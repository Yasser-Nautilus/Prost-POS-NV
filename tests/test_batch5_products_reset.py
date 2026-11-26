"""Product reorder/remove, regular-spicy menu split and the data reset script."""
from __future__ import annotations

import json
import sqlite3

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.menu_data import MENU, SPLIT_PRODUCTS
from broast_pos.data.database.seed import ensure_menu_products
from broast_pos.operations.reset_data import reset


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["batch5-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)

    def call(action, payload=None):
        return json.loads(bridge.dispatch(action, json.dumps(payload or {})))

    assert call("login", {"pin": "1234"})["success"]
    yield bridge, db, call
    DatabaseConnection.reset()


def _cat_products(call, cat_id):
    return [p for p in call("get_all_products")["data"] if p["category_id"] == cat_id]


def test_hide_keeps_product_listed_and_show_restores(env):
    _, _, call = env
    cat = call("create_category", {"name": "ف", "sort_order": 1})["data"]["id"]
    pid = call("create_product", {"name": "س", "price": 5, "category_id": cat})["data"]["id"]
    assert call("update_product", {"product_id": pid, "is_active": False})["success"]
    assert [p["is_active"] for p in _cat_products(call, cat)] == [False]
    assert call("get_products_by_category", {"category_id": cat})["data"] == []
    assert call("update_product", {"product_id": pid, "is_active": True})["success"]
    assert call("get_products_by_category", {"category_id": cat})["data"][0]["id"] == pid


def test_remove_deletes_unused_product(env):
    _, _, call = env
    cat = call("create_category", {"name": "ف", "sort_order": 1})["data"]["id"]
    pid = call("create_product", {"name": "س", "price": 5, "category_id": cat})["data"]["id"]
    assert call("remove_product", {"product_id": pid})["success"]
    assert _cat_products(call, cat) == []


def test_remove_refused_when_product_has_orders(env):
    _, db, call = env
    cat = call("create_category", {"name": "ف", "sort_order": 1})["data"]["id"]
    pid = call("create_product", {"name": "س", "price": 5, "category_id": cat})["data"]["id"]
    db.execute("PRAGMA foreign_keys = OFF")
    db.execute(
        "INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price, total_price)"
        " VALUES (999, ?, 'س', 1, 5, 5)", (pid,))
    db.commit()
    res = call("remove_product", {"product_id": pid})
    assert res["success"] is False
    assert len(_cat_products(call, cat)) == 1


def test_reorder_products_persists_and_validates(env):
    _, _, call = env
    cat = call("create_category", {"name": "ف", "sort_order": 1})["data"]["id"]
    ids = [call("create_product", {"name": n, "price": 5, "category_id": cat})["data"]["id"]
           for n in ("a", "b", "c")]
    new = [ids[2], ids[0], ids[1]]
    assert call("reorder_products", {"category_id": cat, "product_ids": new})["success"]
    assert [p["id"] for p in _cat_products(call, cat)] == new
    assert [p["id"] for p in call("get_products_by_category", {"category_id": cat})["data"]] == new
    assert call("reorder_products", {"category_id": cat, "product_ids": new[:2]})["success"] is False
    assert call("reorder_products", {"category_id": cat, "product_ids": new + [new[0]]})["success"] is False


def test_fresh_menu_import_is_already_split(env):
    _, db, _ = env
    ensure_menu_products(db)
    names = {r["name"] for r in db.fetch_all("SELECT name FROM products")}
    assert {"2 قطع دجاج عادي", "2 قطع دجاج حار", "3 قطع كرسبي", "3 قطع زنجر",
            "تندر دجاج", "زنجر دجاج", "هالك توست"} <= names
    assert not names & set(SPLIT_PRODUCTS)
    total = sum(len(items) for _, _, items in MENU)
    assert db.fetch_one("SELECT COUNT(*) c FROM products WHERE name IN (%s)" % ",".join(
        "?" * 3), ("هالك توست", "تندر دجاج", "زنجر دجاج"))["c"] == 3
    assert total >= 40


def test_old_menu_is_split_once_keeping_ids_and_order(env):
    _, db, _ = env
    cat = db.execute("INSERT INTO categories (name, sort_order, is_active) VALUES ('بروست', 1, 1)").lastrowid
    old = [("2 قطع دجاج", 110.0), ("4 قطع دجاج", 195.0), ("هالك توست", 100.0)]
    for i, (n, pr) in enumerate(old, start=1):
        db.execute("INSERT INTO products (name, price, category_id, is_active, sort_order) VALUES (?,?,?,1,?)",
                   (n, pr, cat, i))
    first_id = db.fetch_one("SELECT id FROM products WHERE name='2 قطع دجاج'")["id"]
    db.execute("PRAGMA user_version = 1")
    db.commit()
    ensure_menu_products(db)
    rows = db.fetch_all("SELECT id, name, price FROM products WHERE category_id=? ORDER BY sort_order, id", (cat,))
    assert [r["name"] for r in rows] == [
        "2 قطع دجاج عادي", "2 قطع دجاج حار", "4 قطع دجاج عادي", "4 قطع دجاج حار", "هالك توست"]
    assert rows[0]["id"] == first_id and rows[1]["price"] == 110.0
    ensure_menu_products(db)
    assert db.fetch_one("SELECT COUNT(*) c FROM products WHERE category_id=?", (cat,))["c"] == 5


def test_reset_wipes_data_keeps_menu_and_admin(tmp_path):
    from broast_pos.data.database.migrations import initialise_database
    from broast_pos.data.database.seed import seed_database

    path = tmp_path / "pos.db"
    db = DatabaseConnection(str(path))
    initialise_database(db)
    seed_database(db)
    db.execute("INSERT INTO users (username, display_name, pin_hash, pin_salt, role, cashier_slot, is_active)"
               " VALUES ('c', 'C', 'x', 'y', 'cashier', 1, 1)")
    db.execute("INSERT INTO customers (name, phone) VALUES ('t', '01012345678')")
    db.commit()
    db.close()

    conn = sqlite3.connect(path)
    products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    zones = conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
    conn.close()
    reset(path, tmp_path / "bak.db")
    conn = sqlite3.connect(path)
    assert [r[0] for r in conn.execute("SELECT role FROM users")] == ["admin"]
    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == products
    assert conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0] == zones
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='cash_ledger_no_delete'").fetchone()[0] == 1
    conn.close()
    bak = sqlite3.connect(tmp_path / "bak.db")
    assert bak.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
    bak.close()
