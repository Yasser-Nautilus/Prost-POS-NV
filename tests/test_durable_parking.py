"""Durable parking is private recoverable work, not an accounting event."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.order import Order, OrderItem, OrderType, PaymentMethod
from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.parked_draft_repository import ParkedDraftRepository


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["durable-parking-test"])
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


def park(call, quantity=2):
    call("new_order", {"order_type": "takeaway"})
    call("add_item", {"product_id": 1, "quantity": quantity, "unit_price": .01, "notes": "no salt"})
    call("park_order")


def login_again(call):
    call("logout")
    call("login", {"pin": "1234"})


def count(db, table):
    return db.fetch_one(f"SELECT count(*) n FROM {table}")["n"]


def test_park_logout_login_resume_confirm_once(env):
    bridge, db, call = env
    counter = db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"]
    with patch.object(bridge._print, "on_order_created") as printing:
        park(call)
        assert count(db, "parked_order_drafts") == 1
        assert count(db, "orders") == count(db, "order_items") == 0
        assert count(db, "cash_ledger") == 0  # no sale or drawer movement
        assert db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"] == counter
        printing.assert_not_called()
        login_again(call)
        parked = call("get_parked_orders")
        assert len(parked) == 1
        assert parked[0]["items"][0]["unit_price"] == 70
        call("resume_parked_order", {"index": 0})
        assert len(call("get_parked_orders")) == 0
        assert count(db, "parked_order_drafts") == 1  # recovery retained while editing
        call("change_item_quantity", {"index": 0, "delta": 1})
        login_again(call)
        call("resume_parked_order", {"index": 0})
        assert bridge._order_ctrl.current_order.items[0].quantity == 3
        assert bridge._order_ctrl.current_order.items[0].product_id == 1
        assert bridge._order_ctrl.current_order.items[0].notes == "no salt"
        saved = call("confirm_order")
        assert saved["invoice_no"] == counter
        assert count(db, "orders") == 1
        assert count(db, "parked_order_drafts") == 0
        printing.assert_called_once()
        login_again(call)
        assert call("get_parked_orders") == []
        call("confirm_order", ok=False)
        assert count(db, "orders") == 1


def test_drafts_are_scoped_to_authenticated_user_not_payload_or_slot(env):
    bridge, db, call = env
    bridge._auth.create_user("other", "Other", UserRole.CASHIER, "5678", cashier_slot=1)
    park(call)
    call("logout")
    call("login", {"pin": "5678"})
    assert call("get_parked_orders", {"user_id": 1}) == []
    call("resume_parked_order", {"index": 0, "user_id": 1}, ok=False)
    login_again(call)
    assert len(call("get_parked_orders")) == 1
    assert count(db, "parked_order_drafts") == 1


def test_repark_and_swap_do_not_duplicate_recovery_rows(env):
    _, db, call = env
    park(call, 1)
    park(call, 2)
    call("resume_parked_order", {"index": 0})
    call("resume_parked_order", {"index": 0})
    call("park_order")
    assert count(db, "parked_order_drafts") == 2
    login_again(call)
    assert sorted(o["items"][0]["quantity"] for o in call("get_parked_orders")) == [1, 2]


def test_park_write_failure_keeps_current_and_no_occupancy(env):
    bridge, db, call = env
    call("new_order", {"order_type": "dine_in"})
    call("add_item", {"product_id": 1})
    call("set_table", {"table_number": 4})
    with patch.object(bridge._order_ctrl._drafts, "save", side_effect=sqlite3.OperationalError("disk full")):
        call("park_order", ok=False)
    assert bridge._order_ctrl.current_order is not None
    assert call("get_parked_orders") == []
    assert count(db, "parked_order_drafts") == 0
    assert count(db, "orders") == 0


def test_confirm_failure_rolls_back_consumption_then_retry_uses_one_invoice(env):
    bridge, db, call = env
    park(call)
    call("resume_parked_order", {"index": 0})
    before = db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"]
    db.execute("CREATE TRIGGER fail_draft_sale BEFORE INSERT ON order_items BEGIN SELECT RAISE(ABORT,'disk failure'); END")
    db.commit()
    call("confirm_order", ok=False)
    assert bridge._order_ctrl.current_order.id is None
    assert bridge._order_ctrl.current_order.invoice_no is None
    assert count(db, "parked_order_drafts") == 1
    assert count(db, "orders") == 0
    assert db.fetch_one("SELECT next_invoice_no n FROM shifts")["n"] == before
    db.execute("DROP TRIGGER fail_draft_sale")
    db.commit()
    assert call("confirm_order")["invoice_no"] == before
    assert count(db, "parked_order_drafts") == 0


def test_duplicate_controller_cannot_confirm_consumed_draft(env):
    bridge, db, call = env
    park(call)
    call("resume_parked_order", {"index": 0})
    first = bridge._order_ctrl
    login_again(call)
    call("resume_parked_order", {"index": 0})
    call("confirm_order")
    ok, _ = first.confirm_order(bridge._current_user.id, "admin")
    assert not ok
    assert first.current_order.id is None
    assert count(db, "orders") == 1


def test_saved_amendment_restores_diff_without_new_invoice(env):
    bridge, db, call = env
    call("new_order", {"order_type": "dine_in"})
    call("add_item", {"product_id": 1})
    call("set_table", {"table_number": 4})
    saved = call("confirm_order")
    call("load_order", {"order_id": saved["order_id"]})
    call("change_item_quantity", {"index": 0, "delta": 2})
    call("park_order")
    login_again(call)
    call("resume_parked_order", {"index": 0})
    assert bridge._order_ctrl.current_order.items[0].quantity == 3
    call("confirm_order", ok=False)  # cannot turn saved draft into another sale
    call("save_amendment")
    assert count(db, "orders") == 1
    assert count(db, "parked_order_drafts") == 0
    assert db.fetch_one("SELECT sum(quantity) quantity FROM order_items")["quantity"] == 3


def test_saved_snapshot_cannot_revert_intervening_payment(env):
    bridge, db, call = env
    park(call)
    call("resume_parked_order", {"index": 0})
    saved = call("confirm_order")
    call("load_order", {"order_id": saved["order_id"]})
    call("park_order")
    db.execute("UPDATE orders SET is_paid=1,status='completed' WHERE id=?", (saved["order_id"],))
    db.commit()
    login_again(call)
    call("resume_parked_order", {"index": 0}, ok=False)
    assert bridge._order_ctrl.current_order is None
    assert db.fetch_one("SELECT is_paid FROM orders")["is_paid"] == 1
    assert count(db, "orders") == 1


def test_file_database_restart_roundtrips_lossless_draft(tmp_path):
    path = str(tmp_path / "restart.db")
    db = DatabaseConnection(path)
    initialise_database(db)
    db.execute("INSERT INTO users(id,username,display_name,role,pin_hash) VALUES(1,'a','A','cashier','x')")
    order = Order(order_type=OrderType.DELIVERY, customer_phone="0123", customer_address="address",
                  customer_zone="zone", payment_method=PaymentMethod.ONLINE,
                  discount_type="percent", discount_amount=8.5, delivery_fee=20,
                  items=[OrderItem(7, "Arabic اسم", 2, 42.5, "note")])
    order.recalculate()
    repo = ParkedDraftRepository(db)
    with repo.transaction():
        repo.save(1, order)
    db.close()
    db = DatabaseConnection(path)
    initialise_database(db)  # idempotent schema upgrade/startup path
    assert ParkedDraftRepository(db).list_for_user(1)[0][1] == order
    assert count(db, "orders") == 0
    db.close()


def test_existing_v6_upgrade_preserves_drafts_and_sales(env):
    _, db, call = env
    park(call)
    db.execute("UPDATE schema_version SET version=6")
    db.commit()
    initialise_database(db)
    initialise_database(db)
    assert db.fetch_one("SELECT version FROM schema_version")["version"] == 13
    assert count(db, "parked_order_drafts") == 1
    assert count(db, "orders") == 0


def test_discount_and_table_survive_with_no_extra_grant(env):
    bridge, db, call = env
    call("new_order", {"order_type": "dine_in"})
    call("add_item", {"product_id": 1, "quantity": 2})
    call("set_table", {"table_number": 5})
    call("apply_discount", {"value": 10, "discount_type": "percent", "manager_pin": "1234"})
    expected = bridge._order_ctrl.current_order
    call("park_order")
    login_again(call)
    assert bridge._order_ctrl.get_table_state()[5] == "parked"
    call("resume_parked_order", {"index": 0})
    assert bridge._order_ctrl.current_order == expected
    assert bridge._order_ctrl.current_order.discount_type == "percent"
    assert bridge._order_ctrl.current_order.discount_amount == 14
    assert count(db, "orders") == 0


def test_recovered_removal_still_requires_manager_pin(env):
    bridge, db, call = env
    call("new_order", {"order_type": "dine_in"})
    call("add_item", {"product_id": 1, "quantity": 3})
    call("set_table", {"table_number": 5})
    saved = call("confirm_order")
    call("load_order", {"order_id": saved["order_id"]})
    call("change_item_quantity", {"index": 0, "delta": -1})
    call("park_order")
    login_again(call)
    call("resume_parked_order", {"index": 0})
    call("save_amendment", ok=False)
    assert count(db, "parked_order_drafts") == 1
    assert db.fetch_one("SELECT sum(quantity) q FROM order_items")["q"] == 3
    call("save_amendment", {"manager_pin": "1234", "reason": "تعديل العميل"})
    assert count(db, "parked_order_drafts") == 0
    assert db.fetch_one("SELECT sum(quantity) q FROM order_items")["q"] == 2


def test_user_cannot_update_or_consume_another_users_draft(env):
    bridge, db, call = env
    park(call)
    other = bridge._auth.create_user("other", "Other", UserRole.CASHIER, "5678")
    repo = ParkedDraftRepository(db)
    draft_id, order = repo.list_for_user(bridge._current_user.id)[0]
    with pytest.raises(ValueError):
        with repo.transaction():
            repo.save(other.id, order, draft_id)
    with pytest.raises(ValueError):
        with repo.transaction():
            repo.delete(other.id, draft_id)
    assert count(db, "parked_order_drafts") == 1


def test_outer_draft_transaction_failure_restores_retryable_identity(env):
    from contextlib import contextmanager
    bridge, db, call = env
    park(call)
    call("resume_parked_order", {"index": 0})
    repo = bridge._order_ctrl._drafts

    @contextmanager
    def failed_commit():
        with db.transaction():
            yield
            raise sqlite3.OperationalError("commit failed")

    with patch.object(repo, "transaction", failed_commit):
        call("confirm_order", ok=False)
    assert bridge._order_ctrl.current_order.id is None
    assert bridge._order_ctrl.current_order.invoice_no is None
    assert count(db, "orders") == 0
    assert count(db, "parked_order_drafts") == 1
    call("confirm_order")
    assert count(db, "orders") == 1
    assert count(db, "parked_order_drafts") == 0


def test_existing_v6_without_draft_table_upgrades(env):
    _, db, _ = env
    db.execute("DROP TABLE parked_order_drafts")
    db.execute("UPDATE schema_version SET version=6")
    db.commit()
    initialise_database(db)
    assert db.fetch_one("SELECT version FROM schema_version")["version"] == 13
    assert count(db, "parked_order_drafts") == 0
