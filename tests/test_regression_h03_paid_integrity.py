"""
Regression tests — H03: paid-order integrity.

Root causes:
  1. complete_order() checked status == COMPLETED but not is_paid, so a
     paid-but-active takeaway accepted a second payment, posting a duplicate
     SALE_CASH and changing the recorded payment method.
  2. amend_order() checked status (COMPLETED/CANCELLED) but not is_paid, so
     total-changing amendments on paid active orders were silently accepted,
     creating an irreconcilable mismatch between the amount already posted to
     the ledger and the new total.
  3. No idempotency guard: an exact retry of the same payment on a paid active
     order created a second SALE_CASH row.

Fixes verified here:
  - Cash EGP 70 paid, then Visa attempted → rejected; ledger and method unchanged
  - Paid EGP 70 order amended to EGP 140 → rejected
  - Exact retry (same method and amount) → idempotent; still one SALE_CASH row
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


def _open_session(db: DatabaseConnection, user_id: int, float_egp: float) -> int:
    from broast_pos.core.models.cashier_session import (
        CashLedgerEntry,
        CashierSession,
        LedgerEntryType,
    )
    from datetime import datetime

    repo = CashierSessionRepository(db=db)
    ledger = CashLedgerRepository(db=db)
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


def _paid_active_order(
    db: DatabaseConnection,
    svc: OrderService,
    total: float = 70.0,
    method: PaymentMethod = PaymentMethod.CASH,
) -> Order:
    """Create a READY takeaway order and pay it (finalize=False → stays active)."""
    repo = OrderRepository(db=db)
    order = Order(
        id=None,
        invoice_no=1,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.READY,
        items=[OrderItem(product_id=1, product_name="وجبة", unit_price=total, quantity=1)],
        subtotal=total,
        total=total,
        shift_id=1,
        created_by_id=1,
        created_by_name="كاشير 1",
    )
    saved = repo.save(order)
    _open_session(db, user_id=1, float_egp=100.0)
    svc.complete_order(
        saved.id, method, total,
        actor_id=1, actor_name="كاشير 1", finalize=False,
    )
    return OrderRepository(db=db).get_by_id(saved.id)


class TestH03PaidOrderIntegrity:

    def test_payment_method_change_on_paid_active_order_rejected(self):
        """Cash paid, then Visa attempted on the same active order → reject."""
        db = _fresh_db()
        svc = _make_svc(db)
        order = _paid_active_order(db, svc, total=70.0, method=PaymentMethod.CASH)

        with pytest.raises(ValueError):
            svc.complete_order(
                order.id, PaymentMethod.VISA, 70.0,
                actor_id=1, actor_name="كاشير 1",
            )

        # Ledger unchanged — still exactly one SALE_CASH
        rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE entry_type = ?",
            (LedgerEntryType.SALE_CASH.value,),
        )
        assert len(rows) == 1, "No new SALE_CASH row must be created"

        # Payment method in DB must still be CASH
        reloaded = OrderRepository(db=db).get_by_id(order.id)
        assert reloaded.payment_method == PaymentMethod.CASH

    def test_total_changing_amendment_on_paid_order_rejected(self):
        """An amendment that would change the total of a paid order must be rejected."""
        from unittest.mock import MagicMock
        from broast_pos.core.models.user import User, UserRole

        db = _fresh_db()
        svc = _make_svc(db)
        order = _paid_active_order(db, svc, total=70.0)

        manager = User(
            id=1, username="cashier1", display_name="كاشير 1",
            role=UserRole.MANAGER, pin_hash="", is_active=True,
        )
        auth = MagicMock()
        auth.verify_pin.return_value = manager
        svc._auth = auth

        # Try to add a product (would increase total 70→90)
        added = [OrderItem(product_id=2, product_name="مشروب", unit_price=20, quantity=1, notes="")]
        with pytest.raises(ValueError, match="مدفوع"):
            svc.amend_order(order.id, added_items=added, removed_items=[])

    def test_exact_payment_retry_is_idempotent(self):
        """Repeating the exact same payment on a paid active order → one SALE_CASH row."""
        db = _fresh_db()
        svc = _make_svc(db)
        order = _paid_active_order(db, svc, total=70.0, method=PaymentMethod.CASH)

        # Retry with same method and amount
        result = svc.complete_order(
            order.id, PaymentMethod.CASH, 70.0,
            actor_id=1, actor_name="كاشير 1", finalize=False,
        )

        rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE entry_type = ?",
            (LedgerEntryType.SALE_CASH.value,),
        )
        assert len(rows) == 1, f"Exact retry must not create second SALE_CASH, found {len(rows)}"
        assert result.is_paid is True
