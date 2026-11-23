"""Address removal is not customer deletion and cannot rewrite sales history."""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.user import UserRole
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["customer-workflows"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)
    def call(action, payload=None, ok=True):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"] is ok, result
        return result.get("data")
    call("login", {"pin": "1234"})
    customer = call("create_customer", {"name": "Customer", "phone": "01012345678"})
    zone = call("get_active_zones")[0]
    address = call("add_customer_address", {"customer_id": customer["id"], "street_name": "Old street", "zone_id": zone["id"]})
    other_address = call("add_customer_address", {"customer_id": customer["id"], "street_name": "Keep street", "zone_id": zone["id"]})
    yield bridge, db, call, customer, address, other_address
    DatabaseConnection.reset()


def test_service_delete_removes_only_address_from_all_lookups(env):
    bridge, db, call, customer, address, keep = env
    bridge._customer.delete_address(address["id"])
    assert bridge._customer.get_address(address["id"]) is None
    assert [a.id for a in bridge._customer.get_addresses(customer["id"])] == [keep["id"]]
    assert [a["id"] for a in call("find_customer_by_phone", {"phone": customer["phone"]})["addresses"]] == [keep["id"]]
    assert call("get_customer_by_id", {"customer_id": customer["id"]})["id"] == customer["id"]
    assert db.fetch_one("SELECT is_active FROM customer_addresses WHERE id=?", (address["id"],))["is_active"] == 0
    with pytest.raises(ValueError):
        bridge._customer.delete_address(address["id"])
    with pytest.raises(ValueError):
        bridge._customer.delete_address(99999)


def test_bridge_requires_customer_match_and_authenticated_login(env):
    bridge, db, call, customer, address, _ = env
    other = call("create_customer", {"name": "Other", "phone": "01012345679"})
    call("delete_customer_address", {"customer_id": other["id"], "address_id": address["id"]}, ok=False)
    call("delete_customer_address", {"address_id": address["id"]}, ok=False)
    call("logout")
    call("delete_customer_address", {"customer_id": customer["id"], "address_id": address["id"]}, ok=False)
    bridge._auth.create_user("cashier", "Cashier", UserRole.CASHIER, "5678")
    call("login", {"pin": "5678"})
    call("delete_customer_address", {"customer_id": customer["id"], "address_id": address["id"]})
    call("delete_customer_address", {"customer_id": customer["id"], "address_id": address["id"]}, ok=False)
    assert db.fetch_one("SELECT count(*) n FROM customers")["n"] == 2


def test_removal_preserves_order_history_snapshots_and_blocks_new_selection(env):
    bridge, db, call, customer, address, _ = env
    call("open_shift")
    call("new_order", {"order_type": "delivery"})
    call("add_item", {"product_id": 1})
    info = {"customer_id": customer["id"], "phone": customer["phone"], "name": customer["name"],
            "address_id": address["id"], "address": address["street_name"]}
    call("set_customer_info", info)
    saved = call("confirm_order")
    before = dict(db.fetch_one("SELECT * FROM orders WHERE id=?", (saved["order_id"],)))
    call("delete_customer_address", {"customer_id": customer["id"], "address_id": address["id"]})
    assert dict(db.fetch_one("SELECT * FROM orders WHERE id=?", (saved["order_id"],))) == before
    history = call("get_customer_history", {"customer_id": customer["id"]})
    assert history[0]["customer_address"] == "Old street"
    assert call("get_customer_statistics", {"customer_id": customer["id"]})["total_orders"] == 1
    call("new_order", {"order_type": "delivery"})
    call("set_customer_info", info, ok=False)
    assert bridge._order_ctrl.current_order.customer_id is None


def test_delete_failure_does_not_report_success(env):
    bridge, db, call, customer, address, _ = env
    db.execute("CREATE TRIGGER block_address_remove BEFORE UPDATE OF is_active ON customer_addresses BEGIN SELECT RAISE(ABORT,'write failure'); END")
    db.commit()
    call("delete_customer_address", {"customer_id": customer["id"], "address_id": address["id"]}, ok=False)
    assert bridge._customer.get_address(address["id"]) is not None
    assert not db.raw_connection.in_transaction


def test_saved_address_cannot_be_reassigned_or_resurrected(env):
    bridge, _, call, customer, address, _ = env
    original = bridge._customer.get_address(address["id"])
    other = call("create_customer", {"name": "Other", "phone": "01012345679"})
    original.customer_id = other["id"]
    with pytest.raises(ValueError):
        bridge._customer._customers.save_address(original)
    original.customer_id = customer["id"]
    bridge._customer.delete_address(address["id"])
    with pytest.raises(ValueError):
        bridge._customer._customers.save_address(original)
    assert bridge._customer.get_address(address["id"]) is None


def test_v8_address_migration_defaults_active_and_keeps_data(env):
    _, db, _, _, address, _ = env
    db.execute("ALTER TABLE customer_addresses DROP COLUMN is_active")
    db.execute("UPDATE schema_version SET version=8")
    db.commit()
    initialise_database(db)
    initialise_database(db)
    assert db.fetch_one("SELECT version FROM schema_version")["version"] == 10
    assert db.fetch_one("SELECT is_active FROM customer_addresses WHERE id=?", (address["id"],))["is_active"] == 1


def test_customer_record_delete_is_still_noop_not_address_removal(env):
    bridge, _, call, customer, address, _ = env
    bridge._customer._customers.delete(customer["id"])
    assert call("get_customer_by_id", {"customer_id": customer["id"]})
    assert bridge._customer.get_address(address["id"]) is not None


def test_lookup_uses_exact_validated_phone(env):
    _, _, call, customer, _, _ = env
    assert call("find_customer_by_phone", {"phone": customer["phone"]})["id"] == customer["id"]
    assert call("find_customer_by_phone", {"phone": "01099999999"}) is None
    call("find_customer_by_phone", {"phone": "01012"}, ok=False)
