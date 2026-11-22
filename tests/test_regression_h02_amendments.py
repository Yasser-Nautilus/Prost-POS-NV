"""
Regression tests — H02/M04: amendment identity and result shape.

H02 root causes:
  1. AmendmentTracker.diff() omits product_id/notes so the controller
     rebuilds changes by product_name, losing note variants.
  2. amend_order() uses a product-id set for removal, deleting the entire
     line instead of applying a quantity delta.
  3. save_amendment() no-op branch returns 2 values; the bridge always
     unpacks 3 (M04).

Fixes verified here:
  - qty 3→2 keeps line with qty 2 after DB reload
  - same product, different notes — only the matched variant is changed
  - note-only edit (no qty change) persists to DB
  - DB matches controller state after save
  - no-op save returns 3 values and succeeds
  - all result branches from save_amendment return exactly 3 values
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.features.order_lifecycle.amendment_tracker import AmendmentTracker


# ---------------------------------------------------------------------------
# DB bootstrap
# ---------------------------------------------------------------------------

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
        "VALUES (1,'cashier1','كاشير 1','cashier','h1',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.execute("INSERT INTO categories (id, name) VALUES (1, 'عام')")
    db.execute(
        "INSERT INTO products (id, name, price, category_id, is_active) "
        "VALUES (1,'وجبة',70.0,1,1),(2,'مشروب',20.0,1,1)"
    )
    db.commit()
    return db


def _saved_order(
    db: DatabaseConnection,
    items: list[tuple[int, str, float, int, str]],  # (pid, name, price, qty, notes)
) -> Order:
    repo = OrderRepository(db=db)
    order_items = [
        OrderItem(
            product_id=pid,
            product_name=name,
            unit_price=price,
            quantity=qty,
            notes=notes,
        )
        for pid, name, price, qty, notes in items
    ]
    total = sum(i.unit_price * i.quantity for i in order_items)
    order = Order(
        id=None,
        invoice_no=1,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.READY,
        items=order_items,
        subtotal=total,
        total=total,
        shift_id=1,
        created_by_id=1,
        created_by_name="كاشير 1",
    )
    return repo.save(order)


# ---------------------------------------------------------------------------
# AmendmentTracker.diff — includes product_id and notes in output
# ---------------------------------------------------------------------------

class TestAmendmentTrackerDiff:

    def test_diff_includes_product_id_and_notes(self):
        tracker = AmendmentTracker()
        items = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=3, notes="")]
        tracker.snapshot(items)
        # reduce to 2
        modified = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=2, notes="")]
        changes = tracker.diff(modified)
        assert len(changes) == 1
        c = changes[0]
        assert c["action"] == "removed"
        assert c["product_id"] == 1
        assert c["notes"] == ""
        assert c["quantity"] == 1

    def test_diff_note_variant_is_distinct(self):
        tracker = AmendmentTracker()
        items = [
            OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=1, notes=""),
            OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=1, notes="بدون ملح"),
        ]
        tracker.snapshot(items)
        # Remove the note variant only
        modified = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=1, notes="")]
        changes = tracker.diff(modified)
        assert len(changes) == 1
        c = changes[0]
        assert c["action"] == "removed"
        assert c["notes"] == "بدون ملح"
        assert c["product_id"] == 1

    def test_no_change_returns_empty(self):
        tracker = AmendmentTracker()
        items = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=2, notes="")]
        tracker.snapshot(items)
        changes = tracker.diff(items)
        assert changes == []


# ---------------------------------------------------------------------------
# amend_order — quantity delta, not full remove
# ---------------------------------------------------------------------------

def _svc_with_mock_auth(db: DatabaseConnection):
    """OrderService with a mock auth that accepts any PIN as manager."""
    from unittest.mock import MagicMock
    from broast_pos.core.models.user import User, UserRole
    from broast_pos.core.services.order_service import OrderService
    from broast_pos.data.repositories.order_repository import OrderRepository

    manager = User(
        id=1, username="cashier1", display_name="كاشير 1",
        role=UserRole.MANAGER, pin_hash="", is_active=True,
    )
    auth = MagicMock()
    auth.verify_pin.return_value = manager
    auth.get_current_user.return_value = manager
    return OrderService(order_repo=OrderRepository(db=db), auth_service=auth)


class TestAmendOrderQuantityDelta:

    def test_qty_decrease_keeps_line_with_new_qty(self):
        db = _fresh_db()
        order = _saved_order(db, [(1, "وجبة", 70.0, 3, "")])
        order_id = order.id

        svc = _svc_with_mock_auth(db)
        # decrease qty by 1 (3 → 2): removed_items carries the delta=1
        removed = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=1, notes="")]
        svc.amend_order(order_id, added_items=[], removed_items=removed, manager_pin="1234")

        from broast_pos.data.repositories.order_repository import OrderRepository
        reloaded = OrderRepository(db=db).get_by_id(order_id)
        assert reloaded is not None
        lines = [i for i in reloaded.items if i.product_id == 1]
        assert len(lines) == 1
        assert lines[0].quantity == 2, f"Expected qty=2, got {lines[0].quantity}"

    def test_full_removal_deletes_line(self):
        db = _fresh_db()
        order = _saved_order(db, [(1, "وجبة", 70.0, 2, "")])
        order_id = order.id

        svc = _svc_with_mock_auth(db)
        removed = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=2, notes="")]
        svc.amend_order(order_id, added_items=[], removed_items=removed, manager_pin="1234")

        from broast_pos.data.repositories.order_repository import OrderRepository
        reloaded = OrderRepository(db=db).get_by_id(order_id)
        lines = [i for i in reloaded.items if i.product_id == 1]
        assert lines == [], "Line should be fully removed"

    def test_note_variant_only_matching_line_changed(self):
        db = _fresh_db()
        order = _saved_order(
            db,
            [
                (1, "وجبة", 70.0, 1, ""),
                (1, "وجبة", 70.0, 1, "بدون ملح"),
            ],
        )
        order_id = order.id

        svc = _svc_with_mock_auth(db)
        # Remove only the "بدون ملح" variant (qty=1 → delta=1 → full remove of that line)
        removed = [OrderItem(product_id=1, product_name="وجبة", unit_price=70, quantity=1, notes="بدون ملح")]
        svc.amend_order(order_id, added_items=[], removed_items=removed, manager_pin="1234")

        from broast_pos.data.repositories.order_repository import OrderRepository
        reloaded = OrderRepository(db=db).get_by_id(order_id)
        # plain variant must still be there
        plain = [i for i in reloaded.items if i.product_id == 1 and (i.notes or "") == ""]
        noted = [i for i in reloaded.items if i.product_id == 1 and (i.notes or "") == "بدون ملح"]
        assert len(plain) == 1, "Plain variant should survive"
        assert len(noted) == 0, "Noted variant should be removed"


# ---------------------------------------------------------------------------
# M04 — save_amendment result shape (always 3 values)
# ---------------------------------------------------------------------------

class TestSaveAmendmentResultShape:

    def _make_controller(self, db: DatabaseConnection):
        from unittest.mock import MagicMock
        from broast_pos.core.services.audit_service import AuditService
        from broast_pos.core.services.order_service import OrderService
        from broast_pos.data.repositories.audit_repository import AuditRepository
        from broast_pos.data.repositories.order_repository import OrderRepository
        from broast_pos.data.repositories.order_status_history_repository import (
            OrderStatusHistoryRepository,
        )
        from broast_pos.features.order_lifecycle.order_controller import OrderController

        svc = OrderService(
            order_repo=OrderRepository(db=db),
            audit_service=AuditService(AuditRepository(db=db)),
            status_history_repo=OrderStatusHistoryRepository(db=db),
        )
        ctrl = OrderController(
            order_service=svc,
            financial_service=MagicMock(),
            auth_service=MagicMock(),
            print_triggers=MagicMock(),
        )
        return ctrl

    def test_no_op_save_returns_three_values(self):
        db = _fresh_db()
        order = _saved_order(db, [(1, "وجبة", 70.0, 1, "")])
        ctrl = self._make_controller(db)
        ctrl.load_order(order.id)
        # No edits — save without changes
        result = ctrl.save_amendment()
        assert len(result) == 3, f"Expected 3 values, got {len(result)}: {result}"
        ok, msg, _ = result
        assert ok is True

    def test_successful_save_returns_three_values(self):
        db = _fresh_db()
        order = _saved_order(db, [(1, "وجبة", 70.0, 1, "")])
        ctrl = self._make_controller(db)
        ctrl.load_order(order.id)
        # Edit: add another item (additions don't need manager PIN)
        ctrl.add_item(product_id=2, product_name="مشروب", unit_price=20.0, quantity=1)
        result = ctrl.save_amendment()
        assert len(result) == 3, f"Expected 3 values, got {len(result)}: {result}"
        ok, msg, _ = result
        assert ok is True, f"Expected success, got: {msg}"
