# ruff: noqa: F811
"""Real bridge regressions for the combined QA fixes."""
from __future__ import annotations

import json

import pytest
from test_batch_workflow_e2e import _delivery_order, _setup
from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401
from test_regression_h02_amendments import _fresh_db, _saved_order, _svc_with_mock_auth

from broast_pos.core.models.order import OrderItem
from broast_pos.core.phone import INVALID_PHONE_MSG, normalize_egyptian_mobile
from broast_pos.data.repositories.order_repository import OrderRepository


@pytest.mark.parametrize("quantity", [1, 2, 3, 4])
def test_removal_consumes_delta_once_across_identical_lines(quantity):
    db = _fresh_db()
    order = _saved_order(db, [(1, "وجبة", 70., 3, ""), (1, "وجبة", 70., 1, "")])
    svc = _svc_with_mock_auth(db)
    svc.amend_order(order.id, added_items=[], removed_items=[OrderItem(
        product_id=1, product_name="وجبة", unit_price=70, quantity=quantity,
    )], manager_pin="1234")
    result = OrderRepository(db).get_by_id(order.id)
    assert sum(i.quantity for i in result.items) == 4-quantity
    assert result.total == (4-quantity)*70


@pytest.mark.parametrize("legacy_row", [False, True])
@pytest.mark.parametrize("per_trip", [False, True])
def test_trip_then_day_fee_paid_once(qapp, legacy_row, per_trip):
    c, db, _, (driver, _) = _setup(qapp)
    oid, _ = _delivery_order(c)
    assert c.call("check_in_driver", {"driver_id": driver})["success"]
    trip = c.call("create_trip", {"driver_id": driver, "order_ids": [oid]})["data"]["trip_id"]
    assert c.call("dispatch_trip", {"trip_id": trip})["success"]
    assert c.call("return_trip", {"trip_id": trip})["success"]
    if per_trip:
        assert c.call("settle_driver", {"driver_id": driver, "trip_id": trip})["success"]
        assert c.call("get_expenses")["data"] == []
    assert c.call("settle_driver", {"driver_id": driver})["success"]
    if legacy_row:
        # Old valid daily payouts must remain recognizable, without rewriting history.
        db.execute("DELETE FROM driver_day_closures")
        db.commit()
    state = c.call("get_driver_settlement_preview", {"driver_id": driver})["data"]["day_settlement"]
    assert state["completed"] and state["paid_amount"] == 15
    assert state["expense_id"]
    assert not c.call("settle_driver", {"driver_id": driver})["success"]
    assert len(c.call("get_expenses")["data"]) == 1
    ledger = db.fetch_all("SELECT entry_type,amount_pt FROM cash_ledger WHERE trip_id=?", (trip,))
    assert len([x for x in ledger if x["entry_type"] == "DRIVER_REMITTANCE"]) == 1
    assert [x["amount_pt"] for x in ledger if x["entry_type"] == "DRIVER_FEE_PAYOUT"] == [-1500]


def test_boundary_errors_and_ascii_pin_policy(qapp):
    c, db, _, _ = _setup(qapp)
    c.call("logout"); c.call("login", {"pin": "1234"})
    for pin in ["abcd", "١٢٣٤", "12ab"]:
        result = c.call("create_user", {"username": "bad_pin", "display_name": "Bad", "role": "manager", "pin": pin})
        assert not result["success"] and "0-9" in result["error"]
    result = c.call("create_product", {"name": "Bad category", "category_id": 999999, "price": 10})
    assert not result["success"] and "FOREIGN KEY" not in json.dumps(result)
    result = c.call("create_zone", {"name": "Bad fee", "delivery_fee": "text"})
    assert not result["success"] and "could not convert" not in json.dumps(result)
    assert normalize_egyptian_mobile("٠١٠١٢٣٤٥٦٧٨") is None
    assert "0-9" in INVALID_PHONE_MSG
