# ruff: noqa: F811
"""Driver statistics: deliveries and average trip time, per day and month."""
from __future__ import annotations

from datetime import date

import pytest
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401

from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.delivery_repository import DeliveryRepository


@pytest.fixture()
def repo(tmp_path):
    db = DatabaseConnection(str(tmp_path / "s.db"))
    initialise_database(db)
    db.execute("PRAGMA foreign_keys = OFF")
    return db, DeliveryRepository(db)


def _trip(db, tid, driver, name, disp, ret, order_ids):
    db.execute(
        "INSERT INTO delivery_trips (id, driver_id, driver_name, created_at, dispatched_at, returned_at)"
        " VALUES (?,?,?,?,?,?)", (tid, driver, name, disp, disp, ret))
    for oid, status in order_ids:
        db.execute("INSERT INTO orders (id, invoice_no, shift_id, order_type, created_by_id, created_by_name, cashier_slot, status, total) VALUES (?,?,1,'delivery',1,'x',1,?,?)", (oid, oid, status, 100))
        db.execute("INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (?,?)", (tid, oid))
    db.commit()


def test_stats_per_driver_day_and_month(repo):
    db, r = repo
    _trip(db, 1, 7, "علي", "2026-11-10 12:00:00", "2026-11-10 12:30:00", [(1, "completed"), (2, "completed")])
    _trip(db, 2, 7, "علي", "2026-11-10 14:00:00", "2026-11-10 14:10:00", [(3, "cancelled"), (4, "completed")])
    _trip(db, 3, 8, "سعد", "2026-11-02 13:00:00", None, [(5, "completed")])
    svc = DeliveryService(delivery_repo=r)
    day = {x["driver_id"]: x for x in svc.get_driver_stats("day", date(2026, 11, 10))}
    assert list(day) == [7]
    assert day[7]["delivery_count"] == 3          # the cancelled order is not a delivery
    assert day[7]["trip_count"] == 2
    assert day[7]["avg_trip_minutes"] == 20.0     # (30 + 10) / 2
    month = {x["driver_id"]: x for x in svc.get_driver_stats("month", date(2026, 11, 20))}
    assert month[7]["delivery_count"] == 3
    assert month[8]["delivery_count"] == 1
    assert month[8]["avg_trip_minutes"] is None   # never returned: no time to average


def test_bad_period_is_rejected(repo):
    _, r = repo
    with pytest.raises(ValueError):
        DeliveryService(delivery_repo=r).get_driver_stats("week")
