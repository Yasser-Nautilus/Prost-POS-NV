"""Regression tests for the cashier/delivery change batch."""
from __future__ import annotations

import pytest

from broast_pos.core.models.order import OrderItem
from broast_pos.core.models.user import UserRole
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import LATEST_VERSION, initialise_database
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.features.order_lifecycle.amendment_tracker import AmendmentTracker


@pytest.fixture(autouse=True)
def _reset():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _item(pid=1, qty=1, notes=None):
    return OrderItem(product_id=pid, product_name="x", quantity=qty, unit_price=70.0, notes=notes)


def test_amendment_duplicate_lines_are_summed_not_doubled():
    """Order 210: duplicate (product, notes) lines must not inflate the diff."""
    t = AmendmentTracker()
    t.snapshot([_item(qty=2), _item(qty=1)])  # 3 total
    assert t.diff([_item(qty=2), _item(qty=1)]) == []
    changes = t.diff([_item(qty=2)])
    assert len(changes) == 1
    assert changes[0]["action"] == "removed" and changes[0]["quantity"] == 1


def test_db_is_latest_version_with_phone_column():
    db = DatabaseConnection(":memory:")
    initialise_database(db)
    assert LATEST_VERSION >= 13
    cols = [r["name"] for r in db.fetch_all("PRAGMA table_info(users)")]
    assert "phone" in cols


def test_driver_requires_phone_and_saves_it():
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    svc = AuthService(UserRepository(db))
    with pytest.raises(ValueError):
        svc.create_user("drv", "سائق", UserRole.CASHIER, "4821", cashier_slot=None, require_driver_phone=True)
    u = svc.create_user("drv", "سائق", UserRole.CASHIER, "4821", cashier_slot=None,
                        phone="01012345678", require_driver_phone=True)
    assert UserRepository(db).get_by_id(u.id).phone


def test_attendance_uses_restaurant_clock_and_open_record_has_no_checkout(monkeypatch):
    from broast_pos.data.repositories import delivery_repository as dr
    from broast_pos.data.repositories.delivery_repository import DeliveryRepository

    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    db.execute("INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
               "VALUES (9,'d','سائق','cashier','h',1)")
    monkeypatch.setattr(dr, "restaurant_now_str", lambda: "2026-11-23 09:50:00")
    repo = DeliveryRepository(db)
    repo.check_in(9)
    rec = repo.get_attendance_for_date("2026-11-23")[0]
    assert str(rec.check_in_at) == "2026-11-23 09:50:00" and rec.check_out_at is None
    monkeypatch.setattr(dr, "restaurant_now_str", lambda: "2026-11-23 17:05:00")
    repo.check_out(9)
    assert str(repo.get_attendance_for_date("2026-11-23")[0].check_out_at) == "2026-11-23 17:05:00"


def test_restaurant_clock_is_cairo():
    from datetime import datetime, timedelta, timezone

    from broast_pos.core.clock import restaurant_now
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    diff = restaurant_now() - utc
    assert timedelta(hours=1, minutes=59) <= diff <= timedelta(hours=3, minutes=1)
