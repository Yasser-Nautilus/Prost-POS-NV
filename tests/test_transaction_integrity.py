"""Transaction failure must not contaminate later unrelated successful work."""
from __future__ import annotations

import json
import sqlite3
import threading
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.repositories.order_repository import OrderRepository


@pytest.fixture
def setup():
    app = QCoreApplication.instance() or QCoreApplication(["transaction-test"])
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


def test_rejected_order_cannot_be_committed_by_customer_save(setup):
    _, db, call = setup
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1, "quantity": -1})
    counter = db.fetch_one("SELECT next_invoice_no FROM shifts")["next_invoice_no"]
    call("confirm_order", ok=False)
    assert not db.raw_connection.in_transaction
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 0
    assert db.fetch_one("SELECT count(*) n FROM order_items")["n"] == 0
    assert db.fetch_one("SELECT next_invoice_no FROM shifts")["next_invoice_no"] == counter
    call("create_customer", {"name": "After failure", "phone": "01012345678"})
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 0
    # Fix the same draft and retry, not a freshly created replacement draft.
    call("change_item_quantity", {"index": 0, "delta": 2})
    result = call("confirm_order")
    assert result["invoice_no"] == counter
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
    assert db.fetch_one("SELECT quantity FROM order_items")["quantity"] == 1
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction


def test_failed_item_replacement_preserves_saved_order(setup):
    _, db, call = setup
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    oid = call("confirm_order")["order_id"]
    repo = OrderRepository(db)
    order = repo.get_by_id(oid)
    original_total = order.total
    original_item_id = order.items[0].id
    order.total = -1
    order.items[0].quantity = -1
    with pytest.raises(sqlite3.IntegrityError):
        repo.save(order)
    call("create_customer", {"name": "After update", "phone": "01012345679"})
    saved = repo.get_by_id(oid)
    assert saved.total == original_total
    assert saved.items[0].id == original_item_id
    assert saved.items[0].quantity == 1
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction


def test_caught_nested_failure_rolls_back_only_its_scope(setup):
    _, db, _ = setup
    db.execute("CREATE TABLE transaction_probe (value TEXT)")
    db.commit()
    with db.transaction():
        db.execute("INSERT INTO transaction_probe VALUES ('outer-before')")
        with pytest.raises(ValueError):
            with db.transaction():
                db.execute("INSERT INTO transaction_probe VALUES ('inner-failed')")
                db.commit()  # repository-style commit cannot release the savepoint
                raise ValueError("injected")
        with db.transaction():
            db.execute("INSERT INTO transaction_probe VALUES ('inner-success')")
        db.execute("INSERT INTO transaction_probe VALUES ('outer-after')")
    assert [r["value"] for r in db.fetch_all("SELECT value FROM transaction_probe")] == [
        "outer-before", "inner-success", "outer-after",
    ]
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction


def test_outer_failure_rolls_back_successful_inner_scope(setup):
    _, db, _ = setup
    db.execute("CREATE TABLE transaction_probe (value TEXT)")
    db.commit()
    with pytest.raises(KeyboardInterrupt):
        with db.transaction():
            with db.transaction():
                db.execute("INSERT INTO transaction_probe VALUES ('nested')")
            raise KeyboardInterrupt()
    db.commit()
    assert not db.fetch_all("SELECT * FROM transaction_probe")
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction


def test_commit_failure_rolls_back_and_restores_depth(setup):
    _, db, _ = setup
    # Deferred FK: INSERT succeeds, only the outer COMMIT raises.
    db.execute("CREATE TABLE parent_probe(id INTEGER PRIMARY KEY)")
    db.execute("CREATE TABLE child_probe(pid INTEGER REFERENCES parent_probe(id) DEFERRABLE INITIALLY DEFERRED)")
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction():
            db.execute("INSERT INTO child_probe VALUES (999)")
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction
    db.commit()
    assert not db.fetch_all("SELECT * FROM child_probe")
    with db.transaction():
        db.execute("INSERT INTO parent_probe VALUES (1)")
    assert db.fetch_one("SELECT id FROM parent_probe")["id"] == 1


def test_other_thread_cannot_commit_owners_partial_work(setup):
    _, db, _ = setup
    db.execute("CREATE TABLE transaction_probe (value TEXT)")
    db.commit()
    attempted = threading.Event()
    completed = threading.Event()
    errors = []

    def worker():
        attempted.set()
        try:
            with db.transaction():
                db.execute("INSERT INTO transaction_probe VALUES ('worker')")
        except BaseException as exc:
            errors.append(exc)
        finally:
            completed.set()

    with pytest.raises(ValueError):
        with db.transaction():
            db.execute("INSERT INTO transaction_probe VALUES ('owner-failed')")
            thread = threading.Thread(target=worker)
            thread.start()
            assert attempted.wait(2)
            assert not completed.wait(0.05)
            raise ValueError("owner rollback")
    thread.join(timeout=5)
    assert completed.is_set() and not errors
    assert [r["value"] for r in db.fetch_all("SELECT value FROM transaction_probe")] == ["worker"]


def test_script_cannot_implicitly_commit_managed_scope(setup):
    _, db, _ = setup
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.executescript("CREATE TABLE bypass_probe (id INTEGER);")
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction


def test_partial_repository_insert_restores_draft_id(setup):
    _, db, call = setup
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    oid = call("confirm_order")["order_id"]
    repo = OrderRepository(db)
    draft = repo.get_by_id(oid)
    draft.id = None
    draft.invoice_no = 999
    with patch.object(repo, "_save_items", side_effect=RuntimeError("injected item failure")):
        with pytest.raises(RuntimeError):
            repo.save(draft)
    assert draft.id is None
    db.commit()
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1


def test_caught_history_failure_does_not_commit_partial_history(setup):
    bridge, db, call = setup
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1})
    service = bridge._order_svc
    db.execute("CREATE TABLE history_probe (value TEXT)")
    db.commit()

    def broken_history(**kwargs):
        db.execute("INSERT INTO history_probe VALUES ('partial')")
        raise RuntimeError("injected best-effort history failure")

    with patch.object(service._status_history, "record_transition", side_effect=broken_history):
        call("confirm_order")
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
    assert not db.fetch_all("SELECT * FROM history_probe")
    assert db._tx_depth == 0 and not db.raw_connection.in_transaction
