# ruff: noqa: F811
"""Business-day isolation with real bridge, database, drawer and payouts."""
from __future__ import annotations

import pytest
from test_batch_workflow_e2e import _delivery_order, _setup
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401


def _call(c, action, payload=None):
    result = c.call(action, payload)
    assert result["success"], (action, result)
    return result.get("data")


def _trip(c, driver, db, repeat=False):
    if not repeat:
        oid, _ = _delivery_order(c)
    else:
        cust = db.fetch_one("SELECT id FROM customers")["id"]
        addr = db.fetch_one("SELECT id FROM customer_addresses")["id"]
        _call(c, "new_order", {"order_type": "delivery"})
        _call(c, "set_customer_info", {"customer_id": cust, "name": "عميل", "phone": "01099887766",
                                        "address": "ش 1", "address_id": addr, "payment_method": "cash"})
        _call(c, "add_item", {"product_id": 1})
        oid = _call(c, "confirm_order")["order_id"]
    _call(c, "check_in_driver", {"driver_id": driver})
    tid = _call(c, "create_trip", {"driver_id": driver, "order_ids": [oid]})["trip_id"]
    _call(c, "dispatch_trip", {"trip_id": tid})
    _call(c, "return_trip", {"trip_id": tid})
    return tid


def _close_and_open(c):
    _call(c, "session.close", {"session_id": c.session_id, "counted_cash_egp": 500,
                                "manager_pin": "1234", "variance_reason": "regression"})
    _call(c, "logout"); _call(c, "login", {"pin": "1234"})
    _call(c, "print_shift_summary"); _call(c, "close_shift")
    _call(c, "logout"); _call(c, "login", {"pin": "2222"})
    day = _call(c, "open_shift")["id"]
    c.session_id = _call(c, "session.open", {"day_id": day, "user_id": _call(c, "get_current_user")["id"],
                                             "station": "ALL", "opening_float_egp": 100})["id"]
    return day


@pytest.mark.parametrize("overnight", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_new_day_does_not_inherit_trips_or_paid_marker(qapp, overnight, legacy):
    c, db, old_day, (driver, _) = _setup(qapp)
    if overnight:
        db.execute("UPDATE shifts SET business_date=date('now','localtime','-1 day') WHERE id=?", (old_day,))
        db.commit()
    old_trip = _trip(c, driver, db)
    _call(c, "settle_driver", {"driver_id": driver})
    if legacy:
        # Recreate the previous release's marker, preserving its linked expense.
        db.execute("INSERT INTO driver_day_closures (driver_id,settlement_date,settlement_id,expense_id,paid_amount) "
                   "SELECT driver_id,date('now','localtime'),settlement_id,expense_id,paid_amount "
                   "FROM driver_business_day_closures")
        db.execute("DELETE FROM driver_business_day_closures")
        db.commit()
    assert _call(c, "get_driver_settlement_preview", {"driver_id": driver})["day_settlement"]["completed"]
    before = [tuple(r) for r in db.fetch_all("SELECT * FROM driver_day_closures")]
    day = _close_and_open(c)
    assert day != old_day
    assert not c.call("get_driver_settlement_preview", {"driver_id": driver})["success"]
    assert not c.call("print_driver_day_sheet", {"driver_id": driver})["success"]
    assert _call(c, "get_expenses") == []
    tid = _trip(c, driver, db, repeat=True)
    prev = _call(c, "get_driver_settlement_preview", {"driver_id": driver})
    assert prev["day_id"] == day
    assert [t["trip_id"] for t in prev["trips"]] == [tid]
    assert not prev["day_settlement"]["completed"]
    for action in ("settle_driver", "print_driver_day_sheet", "get_driver_settlement_preview"):
        result = c.call(action, {"driver_id": driver, "expected_day_id": old_day})
        assert not result["success"] and "تغير يوم العمل" in result["error"]
    assert not c.call("settle_driver", {"driver_id": driver, "trip_id": old_trip})["success"]
    _call(c, "settle_driver", {"driver_id": driver})
    assert len(_call(c, "get_expenses")) == 1
    assert not c.call("settle_driver", {"driver_id": driver})["success"]
    assert db.fetch_one("SELECT count(*) n FROM cash_ledger WHERE entry_type='DRIVER_FEE_PAYOUT'")["n"] == 2
    assert before == [tuple(r) for r in db.fetch_all("SELECT * FROM driver_day_closures")]


def test_same_day_drawer_handover_keeps_trips_and_paid_state(qapp):
    c, db, day, (driver, _) = _setup(qapp)
    tid = _trip(c, driver, db)
    _call(c, "settle_driver", {"driver_id": driver})
    _call(c, "session.close", {"session_id": c.session_id, "counted_cash_egp": 500,
                                "manager_pin": "1234", "variance_reason": "handover"})
    c.session_id = _call(c, "session.open", {"day_id": day, "user_id": _call(c, "get_current_user")["id"],
                                             "station": "ALL", "opening_float_egp": 100})["id"]
    prev = _call(c, "get_driver_settlement_preview", {"driver_id": driver})
    assert prev["day_id"] == day and prev["day_settlement"]["completed"]
    assert [t["trip_id"] for t in prev["trips"]] == [tid]
    assert not c.call("settle_driver", {"driver_id": driver})["success"]


def test_trip_timestamp_is_not_the_live_day_filter(qapp):
    c, db, day, (driver, _) = _setup(qapp)
    tid = _trip(c, driver, db)
    db.execute("UPDATE delivery_trips SET created_at='2020-01-01 01:00:00' WHERE id=?", (tid,))
    db.commit()
    assert _call(c, "get_driver_settlement_preview", {"driver_id": driver})["day_id"] == day
    assert _call(c, "settle_driver", {"driver_id": driver})["total_delivery_fees"] == 15


def test_old_trip_direct_handover_cannot_book_into_new_day(qapp):
    c, db, _, (driver, _) = _setup(qapp)
    tid = _trip(c, driver, db)
    _call(c, "settle_driver", {"driver_id": driver})
    _close_and_open(c)
    trip = c.bridge._settlement._delivery.get_trip_by_id(tid)
    count = db.fetch_one("SELECT count(*) n FROM cash_ledger")["n"]
    with pytest.raises(ValueError, match="يوم العمل"):
        c.bridge._settlement.remit_trip_cash(trip, 100, 1)
    assert db.fetch_one("SELECT count(*) n FROM cash_ledger")["n"] == count


def test_v14_upgrade_preserves_legacy_rows(qapp):
    from broast_pos.data.database.migrations import initialise_database

    c, db, _, (driver, _) = _setup(qapp)
    _trip(c, driver, db)
    _call(c, "settle_driver", {"driver_id": driver})
    db.execute("INSERT INTO driver_day_closures (driver_id,settlement_date,settlement_id,expense_id,paid_amount) "
               "SELECT driver_id,date('now','localtime'),settlement_id,expense_id,paid_amount FROM driver_business_day_closures")
    old = [tuple(r) for r in db.fetch_all("SELECT * FROM driver_day_closures")]
    db.execute("DROP TABLE driver_business_day_closures")
    db.execute("UPDATE schema_version SET version=14")
    db.commit()
    initialise_database(db)
    assert db.fetch_one("SELECT version FROM schema_version")["version"] == 15
    assert old == [tuple(r) for r in db.fetch_all("SELECT * FROM driver_day_closures")]
    assert _call(c, "get_driver_settlement_preview", {"driver_id": driver})["day_settlement"]["completed"]
