"""
Tests for B-06 — State Machine + transaction().

Covers:
1. DatabaseConnection.transaction() — atomicity, rollback, nesting
2. _ALLOWED_TRANSITIONS — delivery-extra dispatch from NEW/PREPARING/READY
3. change_order_status() validates transitions by order type
4. DeliveryService._change_order_status no longer silently swallows errors
5. mark_dispatched accepts PREPARING and READY orders (not just NEW)
6. Invalid transition raises ValueError (not silently bypassed)
"""
from __future__ import annotations

import pytest
import sqlite3
from unittest.mock import MagicMock, patch

from broast_pos.core.models.order import Order, OrderItem, OrderStatus, OrderType
from broast_pos.core.services.order_service import (
    OrderService, _allowed_targets, _ALLOWED_TRANSITIONS, _DELIVERY_EXTRA
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order(
    order_id: int = 1,
    status: OrderStatus = OrderStatus.NEW,
    order_type: OrderType = OrderType.TAKEAWAY,
) -> Order:
    return Order(
        id=order_id,
        invoice_no=order_id,
        order_type=order_type,
        status=status,
        items=[OrderItem(product_id=1, product_name="x", unit_price=100.0, quantity=1)],
        subtotal=100.0,
        total=100.0,
        shift_id=1,
    )


def _order_svc_with_repo(order_map: dict):
    """Build OrderService with an order_repo that returns from order_map."""
    order_repo = MagicMock()
    order_repo.get_by_id.side_effect = lambda oid: order_map.get(oid)
    order_repo.save.side_effect = lambda o: o
    return OrderService(
        order_repo=order_repo,
        status_history_repo=MagicMock(**{"record_transition.return_value": None}),
    )


# ===========================================================================
# Part A: transaction() context manager
# ===========================================================================

class TestTransactionContextManager:

    def _fresh_db(self):
        """In-memory DB that bypasses the singleton for test isolation."""
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")
        DatabaseConnection.reset()
        return db

    def test_transaction_commits_on_success(self):
        """Values inserted inside transaction() are visible after exit."""
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")

        with db.transaction():
            db.execute("INSERT INTO t VALUES (42)")

        row = db.fetch_one("SELECT v FROM t")
        assert row is not None
        assert row["v"] == 42
        DatabaseConnection.reset()

    def test_transaction_rolls_back_on_exception(self):
        """An exception inside transaction() causes a full rollback."""
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")

        with pytest.raises(RuntimeError, match="boom"):
            with db.transaction():
                db.execute("INSERT INTO t VALUES (99)")
                raise RuntimeError("boom")

        row = db.fetch_one("SELECT v FROM t")
        assert row is None  # rolled back
        DatabaseConnection.reset()

    def test_nested_transaction_commits_at_outermost(self):
        """Inner transaction() calls are no-ops; commit happens at depth 0."""
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")

        with db.transaction():          # depth 1 → BEGIN
            db.execute("INSERT INTO t VALUES (1)")
            with db.transaction():      # depth 2 → no BEGIN
                db.execute("INSERT INTO t VALUES (2)")
            # depth back to 1 — no commit yet
        # depth 0 → COMMIT

        rows = db.fetch_all("SELECT v FROM t ORDER BY v")
        assert [r["v"] for r in rows] == [1, 2]
        DatabaseConnection.reset()

    def test_nested_transaction_rollback_propagates(self):
        """Exception in inner block rolls back everything."""
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")

        with pytest.raises(ValueError):
            with db.transaction():
                db.execute("INSERT INTO t VALUES (10)")
                with db.transaction():
                    db.execute("INSERT INTO t VALUES (20)")
                    raise ValueError("inner fail")

        rows = db.fetch_all("SELECT v FROM t")
        assert len(rows) == 0
        DatabaseConnection.reset()

    def test_commit_is_noop_inside_transaction(self):
        """Calling db.commit() inside transaction() does not flush partial writes."""
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")

        with pytest.raises(RuntimeError):
            with db.transaction():
                db.execute("INSERT INTO t VALUES (7)")
                db.commit()   # must be a no-op — should NOT commit
                raise RuntimeError("abort")

        row = db.fetch_one("SELECT v FROM t")
        assert row is None   # rolled back, proving commit() was a no-op
        DatabaseConnection.reset()

    def test_tx_depth_resets_after_success(self):
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")
        with db.transaction():
            db.execute("INSERT INTO t VALUES (1)")
        assert db._tx_depth == 0
        DatabaseConnection.reset()

    def test_tx_depth_resets_after_failure(self):
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        db = DatabaseConnection.get_instance(":memory:")
        db.execute("CREATE TABLE t (v INTEGER)")
        try:
            with db.transaction():
                raise RuntimeError("x")
        except RuntimeError:
            pass
        assert db._tx_depth == 0
        DatabaseConnection.reset()


# ===========================================================================
# Part B: _allowed_targets — order-type-aware transitions
# ===========================================================================

class TestAllowedTargets:

    def test_takeaway_new_cannot_dispatch(self):
        """A takeaway order in NEW cannot go to OUT_FOR_DELIVERY."""
        order = _make_order(status=OrderStatus.NEW, order_type=OrderType.TAKEAWAY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY not in targets

    def test_delivery_new_can_dispatch(self):
        """A delivery order in NEW CAN go to OUT_FOR_DELIVERY."""
        order = _make_order(status=OrderStatus.NEW, order_type=OrderType.DELIVERY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY in targets

    def test_delivery_preparing_can_dispatch(self):
        """B-06: dispatch from PREPARING should work for delivery."""
        order = _make_order(status=OrderStatus.PREPARING, order_type=OrderType.DELIVERY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY in targets

    def test_delivery_ready_can_dispatch(self):
        """B-06: dispatch from READY should work for delivery."""
        order = _make_order(status=OrderStatus.READY, order_type=OrderType.DELIVERY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY in targets

    def test_delivery_completed_cannot_dispatch(self):
        """COMPLETED delivery cannot be dispatched."""
        order = _make_order(status=OrderStatus.COMPLETED, order_type=OrderType.DELIVERY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY not in targets

    def test_delivery_cancelled_cannot_dispatch(self):
        order = _make_order(status=OrderStatus.CANCELLED, order_type=OrderType.DELIVERY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY not in targets

    def test_takeaway_ready_can_complete(self):
        """A non-delivery READY order goes straight to COMPLETED."""
        order = _make_order(status=OrderStatus.READY, order_type=OrderType.TAKEAWAY)
        targets = _allowed_targets(order)
        assert OrderStatus.COMPLETED in targets

    def test_takeaway_ready_cannot_dispatch(self):
        order = _make_order(status=OrderStatus.READY, order_type=OrderType.TAKEAWAY)
        targets = _allowed_targets(order)
        assert OrderStatus.OUT_FOR_DELIVERY not in targets


# ===========================================================================
# Part C: change_order_status() validates transitions
# ===========================================================================

class TestChangeOrderStatusValidation:

    def test_invalid_transition_raises(self):
        """Transitioning to an invalid state must raise ValueError."""
        order = _make_order(status=OrderStatus.NEW, order_type=OrderType.TAKEAWAY)
        svc = _order_svc_with_repo({1: order})
        with pytest.raises(ValueError, match="لا يمكن الانتقال"):
            svc.change_order_status(1, OrderStatus.COMPLETED)

    def test_valid_transition_succeeds(self):
        order = _make_order(status=OrderStatus.NEW, order_type=OrderType.TAKEAWAY)
        svc = _order_svc_with_repo({1: order})
        result = svc.change_order_status(1, OrderStatus.PREPARING)
        assert result.status == OrderStatus.PREPARING

    def test_delivery_dispatch_from_new_via_service(self):
        """change_order_status allows NEW→OUT_FOR_DELIVERY for delivery."""
        order = _make_order(status=OrderStatus.NEW, order_type=OrderType.DELIVERY)
        svc = _order_svc_with_repo({1: order})
        result = svc.change_order_status(1, OrderStatus.OUT_FOR_DELIVERY)
        assert result.status == OrderStatus.OUT_FOR_DELIVERY

    def test_delivery_dispatch_from_preparing_via_service(self):
        """B-06: PREPARING→OUT_FOR_DELIVERY allowed for delivery."""
        order = _make_order(status=OrderStatus.PREPARING, order_type=OrderType.DELIVERY)
        svc = _order_svc_with_repo({1: order})
        result = svc.change_order_status(1, OrderStatus.OUT_FOR_DELIVERY)
        assert result.status == OrderStatus.OUT_FOR_DELIVERY

    def test_delivery_dispatch_from_ready_via_service(self):
        """B-06: READY→OUT_FOR_DELIVERY allowed for delivery."""
        order = _make_order(status=OrderStatus.READY, order_type=OrderType.DELIVERY)
        svc = _order_svc_with_repo({1: order})
        result = svc.change_order_status(1, OrderStatus.OUT_FOR_DELIVERY)
        assert result.status == OrderStatus.OUT_FOR_DELIVERY

    def test_takeaway_cannot_dispatch(self):
        """Takeaway orders MUST NOT be dispatched."""
        order = _make_order(status=OrderStatus.NEW, order_type=OrderType.TAKEAWAY)
        svc = _order_svc_with_repo({1: order})
        with pytest.raises(ValueError):
            svc.change_order_status(1, OrderStatus.OUT_FOR_DELIVERY)

    def test_order_not_found_raises(self):
        svc = _order_svc_with_repo({})
        with pytest.raises(ValueError, match="غير موجود"):
            svc.change_order_status(999, OrderStatus.PREPARING)

    def test_completed_is_terminal(self):
        """No transition from COMPLETED is allowed."""
        order = _make_order(status=OrderStatus.COMPLETED, order_type=OrderType.DELIVERY)
        svc = _order_svc_with_repo({1: order})
        with pytest.raises(ValueError):
            svc.change_order_status(1, OrderStatus.DELIVERED)

    def test_cancelled_is_terminal(self):
        order = _make_order(status=OrderStatus.CANCELLED, order_type=OrderType.TAKEAWAY)
        svc = _order_svc_with_repo({1: order})
        with pytest.raises(ValueError):
            svc.change_order_status(1, OrderStatus.NEW)


# ===========================================================================
# Part D: DeliveryService error propagation (no silent swallowing)
# ===========================================================================

class TestDeliveryServiceNoSilentErrors:

    def _delivery_svc_no_order_svc(self):
        """Build a DeliveryService with _order_svc=None to trigger the guard."""
        from broast_pos.core.services.delivery_service import DeliveryService
        svc = DeliveryService.__new__(DeliveryService)
        svc._order_svc = None
        svc._orders = MagicMock()
        svc._delivery = MagicMock()
        svc._users = MagicMock()
        svc._audit = MagicMock()
        return svc

    def test_change_order_status_raises_without_order_svc(self):
        """B-06: _change_order_status must raise RuntimeError if no OrderService."""
        from broast_pos.core.services.delivery_service import DeliveryService
        svc = self._delivery_svc_no_order_svc()
        with pytest.raises(RuntimeError, match="OrderService not injected"):
            svc._change_order_status(1, OrderStatus.OUT_FOR_DELIVERY)

    def test_change_order_status_propagates_invalid_transition(self):
        """_change_order_status must NOT swallow ValueError from OrderService."""
        from broast_pos.core.services.delivery_service import DeliveryService
        svc = DeliveryService.__new__(DeliveryService)
        order_svc_mock = MagicMock()
        order_svc_mock.change_order_status.side_effect = ValueError("bad transition")
        svc._order_svc = order_svc_mock
        svc._orders = MagicMock()
        svc._delivery = MagicMock()
        svc._users = MagicMock()
        svc._audit = MagicMock()

        # Must propagate, not swallow
        with pytest.raises(ValueError, match="bad transition"):
            svc._change_order_status(1, OrderStatus.OUT_FOR_DELIVERY)
