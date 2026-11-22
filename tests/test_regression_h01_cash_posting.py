"""
Regression tests — H01: cash SALE_CASH entry must be posted on payment.

Root cause: order_controller.complete_payment() called complete_order()
without passing actor_id/actor_name. With actor_id=None the session
lookup in _create_sale_cash_entry() was skipped, so no SALE_CASH row
was ever written to cash_ledger.

Fix: pass the authenticated cashier's id and name from complete_payment
through to complete_order; and when session mode is active but no open
session is found for that cashier, raise instead of silently skipping.
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.cashier_session import LedgerEntryType, Station
from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.order_service import OrderService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


# ---------------------------------------------------------------------------
# Shared DB bootstrap
# ---------------------------------------------------------------------------

def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'cashier1','كاشير 1','cashier','h1',1),(2,'cashier2','كاشير 2','cashier','h2',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.execute("INSERT INTO categories (id, name) VALUES (1, 'عام')")
    db.execute(
        "INSERT INTO products (id, name, price, category_id, is_active) VALUES (1, 'وجبة', 70.0, 1, 1)"
    )
    db.commit()
    return db


def _make_svc(db: DatabaseConnection) -> OrderService:
    ledger_repo = CashLedgerRepository(db=db)
    session_repo = CashierSessionRepository(db=db)
    return OrderService(
        order_repo=OrderRepository(db=db),
        audit_repo=AuditRepository(db=db),
        audit_service=AuditService(AuditRepository(db=db)),
        status_history_repo=OrderStatusHistoryRepository(db=db),
        ledger_repo=ledger_repo,
        cashier_session_repo=session_repo,
    )


def _open_session(db: DatabaseConnection, user_id: int, float_egp: float) -> int:
    """Open a cashier session with opening float; return session id."""
    repo = CashierSessionRepository(db=db)
    ledger = CashLedgerRepository(db=db)
    from broast_pos.core.models.cashier_session import CashierSession, CashLedgerEntry, LedgerEntryType
    from datetime import datetime
    session = repo.create(CashierSession(
        id=None, day_id=1, user_id=user_id, station=Station.ALL, is_open=True,
        opened_at=datetime.now().isoformat(),
    ))
    ledger.append(CashLedgerEntry(
        id=None, day_id=1, session_id=session.id,
        entry_type=LedgerEntryType.OPENING_FLOAT,
        amount_pt=round(float_egp * 100),
        actor_id=user_id,
    ))
    db.commit()
    return session.id


def _saved_order(db: DatabaseConnection, total: float = 70.0, shift_id: int = 1) -> Order:
    """Insert and return a READY takeaway order."""
    repo = OrderRepository(db=db)
    order = Order(
        id=None,
        invoice_no=1,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.READY,
        items=[OrderItem(product_id=1, product_name="وجبة", unit_price=total, quantity=1)],
        subtotal=total,
        total=total,
        shift_id=shift_id,
        created_by_id=1,
        created_by_name="كاشير 1",
    )
    return repo.save(order)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestH01CashPosting:

    def test_cash_payment_with_actor_id_posts_exactly_one_sale_cash(self):
        """When actor_id is supplied, exactly one SALE_CASH row must appear."""
        db = _fresh_db()
        session_id = _open_session(db, user_id=1, float_egp=100.0)
        svc = _make_svc(db)
        order = _saved_order(db, total=70.0)

        svc.complete_order(
            order_id=order.id,
            payment_method=PaymentMethod.CASH,
            amount_received=70.0,
            actor_id=1,
            actor_name="كاشير 1",
        )

        rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE entry_type = ? AND session_id = ?",
            (LedgerEntryType.SALE_CASH.value, session_id),
        )
        assert len(rows) == 1, "Expected exactly one SALE_CASH entry"

    def test_session_balance_increases_by_payment_amount(self):
        """Session balance = float + payment = 100 + 70 = 170 EGP after payment."""
        db = _fresh_db()
        session_id = _open_session(db, user_id=1, float_egp=100.0)
        svc = _make_svc(db)
        order = _saved_order(db, total=70.0)

        svc.complete_order(
            order_id=order.id,
            payment_method=PaymentMethod.CASH,
            amount_received=70.0,
            actor_id=1,
            actor_name="كاشير 1",
        )

        ledger = CashLedgerRepository(db=db)
        balance_pt = ledger.get_session_balance_pt(session_id)
        assert balance_pt == 17000, f"Expected 17000 pt (EGP 170), got {balance_pt}"

    def test_visa_payment_does_not_post_sale_cash(self):
        """Visa payment must not add any entry to cash_ledger."""
        db = _fresh_db()
        session_id = _open_session(db, user_id=1, float_egp=100.0)
        svc = _make_svc(db)
        order = _saved_order(db, total=70.0)

        svc.complete_order(
            order_id=order.id,
            payment_method=PaymentMethod.VISA,
            amount_received=70.0,
            actor_id=1,
            actor_name="كاشير 1",
        )

        rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE entry_type = ?",
            (LedgerEntryType.SALE_CASH.value,),
        )
        assert len(rows) == 0

    def test_missing_session_in_session_mode_raises_not_skips(self):
        """When session mode is wired and no session exists for cashier, must raise."""
        db = _fresh_db()
        # No session opened — session mode is active (ledger+session repos wired)
        svc = _make_svc(db)
        order = _saved_order(db, total=70.0)

        with pytest.raises(ValueError, match="جلسة"):
            svc.complete_order(
                order_id=order.id,
                payment_method=PaymentMethod.CASH,
                amount_received=70.0,
                actor_id=1,
                actor_name="كاشير 1",
            )

    def test_no_actor_id_in_session_mode_raises(self):
        """Calling complete_order without actor_id when session mode is active must raise."""
        db = _fresh_db()
        _open_session(db, user_id=1, float_egp=100.0)
        svc = _make_svc(db)
        order = _saved_order(db, total=70.0)

        with pytest.raises(ValueError, match="actor_id|جلسة"):
            svc.complete_order(
                order_id=order.id,
                payment_method=PaymentMethod.CASH,
                amount_received=70.0,
                # actor_id intentionally omitted
            )

    def test_order_is_not_marked_paid_when_session_missing(self):
        """With no session, order must NOT be saved as paid (atomic rollback)."""
        db = _fresh_db()
        # No open session for user 1
        svc = _make_svc(db)
        order = _saved_order(db, total=70.0)
        order_id = order.id

        try:
            svc.complete_order(
                order_id=order_id,
                payment_method=PaymentMethod.CASH,
                amount_received=70.0,
                actor_id=1,
                actor_name="كاشير 1",
            )
        except ValueError:
            pass  # expected

        repo = OrderRepository(db=db)
        reloaded = repo.get_by_id(order_id)
        assert reloaded is not None
        assert reloaded.is_paid is False, "Order must NOT be saved as paid after failed posting"
