"""
Regression tests — H13: dispatch/return state changes could partially commit.

Root cause:
  DeliveryService.mark_dispatched()/mark_returned() persisted and committed
  the trip timestamp (DeliveryRepository.mark_dispatched/mark_returned call
  db.commit() directly) BEFORE transitioning each order. If a later order's
  transition failed, the trip already looked dispatched/returned while its
  orders remained in an earlier state — a partial commit.

Fix verified here:
  - Every order on the trip is validated up front (OrderService.can_transition)
    before anything is written.
  - The trip timestamp and all order transitions are written inside one
    database transaction (DatabaseConnection.transaction() — repo-level
    commit() calls become safe no-ops while nested inside it).
  - A failure on order 2 rolls back order 1's transition AND the trip
    timestamp — nothing is left half-applied.
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.order import OrderStatus
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.order_service import OrderService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.order_repository import OrderRepository


@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'mgr','مدير','manager','h1',1), (3,'drv','سائق','cashier','h3',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.execute("INSERT INTO categories (id, name, sort_order, is_active) VALUES (1,'طعام',0,1)")
    db.execute("INSERT INTO products (id, name, price, category_id, is_active) VALUES (1,'بيتزا',100.0,1,1)")
    db.execute(
        "INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled, created_at) "
        "VALUES (10, 3, 'سائق', 0, datetime('now'))"
    )
    # Both orders start dispatchable (NEW) — order 2's failure below is
    # injected mid-transaction, not a pre-validation rejection, so this
    # test exercises the transaction rollback itself.
    db.execute(
        "INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
        "payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
        "VALUES (201, 1, 1, 'delivery', 'new', 70.0, 70.0, 'cash', 0, 1, 'مدير', 1)"
    )
    db.execute(
        "INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
        "payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
        "VALUES (202, 2, 1, 'delivery', 'new', 50.0, 50.0, 'cash', 0, 1, 'مدير', 1)"
    )
    db.execute(
        "INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (10, 201), (10, 202)"
    )
    db.commit()
    return db


def _build_services(db: DatabaseConnection) -> tuple[DeliveryService, OrderRepository, DeliveryRepository]:
    order_repo = OrderRepository(db=db)
    delivery_repo = DeliveryRepository(db=db)
    audit_repo = AuditRepository(db=db)

    order_svc = OrderService(order_repo=order_repo, audit_repo=audit_repo)
    delivery_svc = DeliveryService(
        delivery_repo=delivery_repo,
        order_repo=order_repo,
        audit_repo=audit_repo,
        order_service=order_svc,
    )
    return delivery_svc, order_repo, delivery_repo


class TestH13DispatchRollsBackOnOrderFailure:

    def test_invalid_second_order_blocks_dispatch_entirely(self):
        db = _fresh_db()
        delivery_svc, order_repo, delivery_repo = _build_services(db)

        # Both orders pass pre-validation (both NEW). Inject a real failure
        # on order 2's write specifically, to exercise the transaction's
        # rollback — not the pre-validation shortcut.
        real_change_status = delivery_svc._order_svc.change_order_status

        def _fail_on_order_202(order_id, *args, **kwargs):
            if order_id == 202:
                raise RuntimeError("simulated write failure on order 2")
            return real_change_status(order_id, *args, **kwargs)

        delivery_svc._order_svc.change_order_status = _fail_on_order_202

        with pytest.raises(RuntimeError, match="simulated write failure"):
            delivery_svc.mark_dispatched(trip_id=10)

        # Order 1 must NOT have been transitioned — the whole batch rolled back.
        order1 = order_repo.get_by_id(201)
        assert order1.status == OrderStatus.NEW, (
            "H13 regression: order 1 was dispatched even though order 2's "
            "transition was invalid — the batch was not atomic"
        )

        # The trip itself must still look un-dispatched.
        trip = delivery_repo.get_trip_by_id(10)
        assert trip.dispatched_at is None, (
            "H13 regression: the trip timestamp was committed even though "
            "an order transition in the same batch failed"
        )
        assert trip.is_dispatched is False

    def test_already_cancelled_order_is_skipped_not_rejected(self):
        """A cancelled order on the trip is legitimately left alone (not an
        error) — only orders actually eligible for dispatch are touched."""
        db = _fresh_db()
        db.execute("UPDATE orders SET status = 'cancelled' WHERE id = 202")
        db.commit()
        delivery_svc, order_repo, delivery_repo = _build_services(db)

        trip = delivery_svc.mark_dispatched(trip_id=10)

        assert trip.is_dispatched is True
        assert order_repo.get_by_id(201).status == OrderStatus.OUT_FOR_DELIVERY
        assert order_repo.get_by_id(202).status == OrderStatus.CANCELLED

    def test_valid_trip_dispatches_normally(self):
        """No behaviour change for the common, all-valid case."""
        db = _fresh_db()
        delivery_svc, order_repo, delivery_repo = _build_services(db)

        trip = delivery_svc.mark_dispatched(trip_id=10)

        assert trip.is_dispatched is True
        assert order_repo.get_by_id(201).status == OrderStatus.OUT_FOR_DELIVERY
        assert order_repo.get_by_id(202).status == OrderStatus.OUT_FOR_DELIVERY
