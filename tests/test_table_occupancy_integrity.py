"""One active confirmed dine-in order per table, including alternate writers."""
from __future__ import annotations

import itertools
import json
import sqlite3
import threading

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.order_repository import OrderRepository


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["table-integrity"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)
    def call(action, payload=None, ok=True):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"] is ok, result
        return result.get("data")
    call("login", {"pin": "1234"})
    call("open_shift")
    call("session.open", {"station": "COUNTER", "opening_float_egp": 0})
    yield bridge, db, call
    DatabaseConnection.reset()


def draft(call, table=4):
    call("new_order", {"order_type": "dine_in"})
    call("set_table", {"table_number": table})
    call("add_item", {"product_id": 1})


INVOICES = itertools.count(100)


def order(table=4, status=OrderStatus.NEW, kind=OrderType.DINE_IN):
    return Order(invoice_no=next(INVOICES), shift_id=1, created_by_id=1, order_type=kind, status=status, table_no=table,
                 items=[OrderItem(1, "Item", 1, 70)], subtotal=70, total=70)


def test_bridge_duplicate_confirm_preserves_draft_invoice_and_existing_order(env):
    bridge, db, call = env
    draft(call)
    first = call("confirm_order")
    before = db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"]
    draft(call)
    call("confirm_order", ok=False)
    assert bridge._order_ctrl.current_order.id is None
    assert bridge._order_ctrl.current_order.invoice_no is None
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
    assert db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"] == before
    assert bridge._order_svc.get_order_by_id(first["order_id"]).table_no == 4
    call("set_table", {"table_number": 5})
    assert call("confirm_order")["invoice_no"] == before


def test_parked_draft_cannot_claim_table_confirmed_while_away(env):
    bridge, db, call = env
    draft(call)
    call("park_order")
    draft(call)
    call("confirm_order")
    call("resume_parked_order", {"index": 0})
    call("confirm_order", ok=False)
    assert db.fetch_one("SELECT count(*) n FROM parked_order_drafts")["n"] == 1
    assert bridge._order_ctrl.current_order.items
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1


@pytest.mark.parametrize("release", ["payment", "cancel", "move"])
def test_table_reusable_after_existing_release_paths(env, release):
    _, _, call = env
    draft(call)
    first = call("confirm_order")
    if release == "payment":
        call("complete_payment", {"order_id": first["order_id"], "payment_method": "cash", "amount_paid": 100})
    elif release == "cancel":
        call("cancel_order", {"order_id": first["order_id"], "manager_pin": "1234", "reason": "test"})
    else:
        call("load_order", {"order_id": first["order_id"]})
        call("change_table", {"table_number": 5})
    draft(call)
    assert call("confirm_order")["order_id"] != first["order_id"]


def test_existing_table_append_keeps_same_order_and_invoice(env):
    _, db, call = env
    draft(call)
    first = call("confirm_order")
    call("load_order_by_table", {"table_number": 4})
    call("add_item", {"product_id": 1})
    call("save_amendment")
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
    saved = db.fetch_one("SELECT id,invoice_no,total FROM orders")
    assert saved["id"] == first["order_id"] and saved["invoice_no"] == first["invoice_no"]
    assert saved["total"] == 140


def test_repository_and_direct_sql_writes_cannot_enter_occupied_table(env):
    _, db, _ = env
    repo = OrderRepository(db)
    first = repo.save(order())
    second = repo.save(order(5))
    duplicate = order()
    with pytest.raises(ValueError, match="الطاولة مشغولة"):
        repo.save(duplicate)
    assert duplicate.id is None
    for sql, params in [
        ("INSERT INTO orders(invoice_no,shift_id,order_type,status,table_no) VALUES(999,1,'dine_in','new',4)", ()),
        ("UPDATE orders SET table_no=4 WHERE id=?", (second.id,)),
    ]:
        with pytest.raises(sqlite3.IntegrityError, match="active_dine_in_table_occupied"):
            with db.transaction():
                db.execute(sql, params)
    first.items[0].quantity = 2
    repo.save(first)  # ordinary amendment at the same table stays valid
    assert repo.get_by_id(first.id).items[0].quantity == 2


def test_reopening_closed_order_or_converting_type_cannot_bypass_guard(env):
    _, db, _ = env
    repo = OrderRepository(db)
    repo.save(order())
    closed = repo.save(order(status=OrderStatus.COMPLETED))
    other_type = repo.save(order(kind=OrderType.TAKEAWAY))
    closed.status = OrderStatus.NEW
    with pytest.raises(ValueError):
        repo.save(closed)
    other_type.order_type = OrderType.DINE_IN
    with pytest.raises(ValueError):
        repo.save(other_type)


def test_paid_but_still_active_holds_table_and_other_types_do_not(env):
    _, db, _ = env
    repo = OrderRepository(db)
    paid = order()
    paid.is_paid = True
    repo.save(paid)
    with pytest.raises(ValueError):
        repo.save(order())
    repo.save(order(kind=OrderType.TAKEAWAY))
    repo.save(order(kind=OrderType.DELIVERY))
    repo.save(order(status=OrderStatus.CANCELLED))


def test_existing_duplicates_survive_upgrade_but_are_not_silently_selected(env):
    _, db, _ = env
    db.execute("DROP TRIGGER trg_orders_table_insert")
    db.execute("DROP TRIGGER trg_orders_table_update")
    repo = OrderRepository(db)
    first = repo.save(order())
    second = repo.save(order())
    db.execute("UPDATE schema_version SET version=7")
    db.commit()
    initialise_database(db)
    initialise_database(db)
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 2
    assert db.fetch_one("SELECT version FROM schema_version")["version"] == 9
    with pytest.raises(ValueError, match="متعددة"):
        repo.get_by_table(4)
    with pytest.raises(ValueError):
        repo.save(order())
    first.items[0].notes = "existing work"
    repo.save(first)
    second.table_no = 5
    repo.save(second)
    assert repo.get_by_table(4).id == first.id
    assert repo.get_by_table(5).id == second.id


def test_two_connections_race_to_insert_and_move_without_duplicates(tmp_path):
    path = str(tmp_path / "table-race.db")
    db = DatabaseConnection(path)
    initialise_database(db)
    seed_database(db)
    db.execute("INSERT INTO shifts(id,opened_by) VALUES(1,1)")
    db.commit()
    db.close()
    barrier = threading.Barrier(2)
    results = []
    def insert():
        local = DatabaseConnection(path)
        barrier.wait()
        try:
            OrderRepository(local).save(order())
            results.append("saved")
        except ValueError:
            results.append("occupied")
        finally:
            local.close()
    threads = [threading.Thread(target=insert) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(results) == ["occupied", "saved"]
    db = DatabaseConnection(path)
    repo = OrderRepository(db)
    a, b = repo.save(order(5)), repo.save(order(6))
    db.close()
    barrier = threading.Barrier(2)
    results.clear()
    def move(saved):
        local = DatabaseConnection(path)
        saved.table_no = 7
        barrier.wait()
        try:
            OrderRepository(local).save(saved)
            results.append("saved")
        except ValueError:
            results.append("occupied")
        finally:
            local.close()
    threads = [threading.Thread(target=move, args=(saved,)) for saved in (a, b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(results) == ["occupied", "saved"]
    db = DatabaseConnection(path)
    assert db.fetch_one("SELECT count(*) n FROM orders WHERE table_no=7")["n"] == 1
    db.close()


def test_two_cashier_service_calls_race_without_losing_invoice(env):
    bridge, db, _ = env
    barrier = threading.Barrier(2)
    results = []
    before = db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"]
    def confirm():
        draft_order = order()
        draft_order.invoice_no = None
        barrier.wait()
        try:
            bridge._order_svc.create_order(draft_order, 1, "Admin")
            results.append("saved")
        except ValueError:
            results.append("occupied")
            assert draft_order.id is None and draft_order.invoice_no is None
    threads = [threading.Thread(target=confirm) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert sorted(results) == ["occupied", "saved"]
    assert db.fetch_one("SELECT count(*) n FROM orders")["n"] == 1
    assert db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"] == before + 1
