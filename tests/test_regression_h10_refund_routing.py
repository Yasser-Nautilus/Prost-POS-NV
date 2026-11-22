"""
Regression tests — H10: refund/cancellation entries could rewrite a closed
drawer's balance.

Root cause:
  OrderService._create_cancel_reversal_entry() posted the REVERSAL entry to
  the original sale's session_id unconditionally, even when that session
  had already been counted and closed. A closed session's sealed expected
  cash would then silently change after the count was taken.

Fix verified here:
  - Cancelling a paid order after its session closed posts the REVERSAL to
    the currently open session instead, leaving the closed session's
    ledger balance exactly as it was when it was counted.
  - The REVERSAL entry still links back to the original sale
    (reverses_entry_id) for the audit trail.
  - If a session is still open when the order is cancelled, the REVERSAL
    is posted there as before (no behaviour change in the common case).
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.cashier_session import (
    CashierSession,
    CashLedgerEntry,
    LedgerEntryType,
    Station,
)
from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.core.services.auth_service import AuthService
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
from broast_pos.data.repositories.user_repository import UserRepository


@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    manager_hash = AuthService.hash_pin("1234")
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'mgr','مدير',?,?,1)",
        ("manager", manager_hash),
    )
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (2,'cashier1','كاشير 1','cashier','h2',1)"
    )
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (3,'cashier2','كاشير 2','cashier','h3',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.execute(
        "INSERT INTO categories (id, name, sort_order, is_active) VALUES (1, 'وجبات', 0, 1)"
    )
    db.execute(
        "INSERT INTO products (id, name, price, category_id, sort_order, is_active) "
        "VALUES (1, 'برجر', 70.0, 1, 0, 1)"
    )
    db.commit()
    return db


def _build_service(db: DatabaseConnection) -> tuple[OrderService, CashLedgerRepository, CashierSessionRepository]:
    order_repo = OrderRepository(db=db)
    audit_repo = AuditRepository(db=db)
    status_history_repo = OrderStatusHistoryRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    session_repo = CashierSessionRepository(db=db)
    user_repo = UserRepository(db)
    auth_service = AuthService(user_repo)

    svc = OrderService(
        order_repo=order_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        status_history_repo=status_history_repo,
        ledger_repo=ledger_repo,
        cashier_session_repo=session_repo,
    )
    return svc, ledger_repo, session_repo


def _paid_active_order(shift_id: int, total: float = 70.0) -> Order:
    return Order(
        invoice_no=1,
        shift_id=shift_id,
        order_type=OrderType.TAKEAWAY,
        status=OrderStatus.NEW,
        items=[OrderItem(product_id=1, product_name="برجر", quantity=1, unit_price=total)],
        subtotal=total,
        total=total,
        payment_method=PaymentMethod.CASH,
        amount_paid=total,
        is_paid=True,
        created_by_id=2,
        created_by_name="كاشير 1",
    )


class TestH10RefundRoutingAfterSessionClosed:

    def test_reversal_skips_closed_session_and_uses_new_open_one(self):
        db = _fresh_db()
        svc, ledger_repo, session_repo = _build_service(db)

        # Session A: cashier1 opens, sells, session is then closed and counted.
        session_a = session_repo.create(
            CashierSession(id=None, day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0)
        )
        order = svc._orders.save(_paid_active_order(shift_id=1))
        ledger_repo.append(CashLedgerEntry(
            id=None, day_id=1, session_id=session_a.id,
            entry_type=LedgerEntryType.SALE_CASH, amount_pt=7000,
            order_id=order.id, actor_id=2,
        ))
        balance_a_before_close = ledger_repo.get_session_balance_pt(session_a.id)
        assert balance_a_before_close == 7000

        session_repo.close_session(
            session_id=session_a.id,
            counted_cash_pt=7000, expected_cash_pt=7000, variance_pt=0,
        )

        # Session B: cashier2 opens a new till after A's count was taken.
        session_b = session_repo.create(
            CashierSession(id=None, day_id=1, user_id=3, station=Station.ALL, opening_float_pt=0)
        )

        # Manager cancels the still-active paid order — the refund must NOT
        # touch session A's now-sealed count.
        svc.cancel_order(order.id, manager_pin="1234", reason="تست")

        balance_a_after_cancel = ledger_repo.get_session_balance_pt(session_a.id)
        assert balance_a_after_cancel == balance_a_before_close == 7000, (
            "H10 regression: cancelling after the till closed must not change "
            "its sealed, already-counted balance"
        )

        balance_b = ledger_repo.get_session_balance_pt(session_b.id)
        assert balance_b == -7000, (
            "The refund outflow must be posted to the currently open till instead"
        )

        reversal = ledger_repo.get_entry_by_order(order.id, LedgerEntryType.REVERSAL)
        assert reversal is not None
        assert reversal.session_id == session_b.id
        sale = ledger_repo.get_entry_by_order(order.id, LedgerEntryType.SALE_CASH)
        assert reversal.reverses_entry_id == sale.id, \
            "Reversal must still reference the original sale entry"

    def test_reversal_uses_still_open_session_when_not_closed(self):
        """No behaviour change when the original session is still open."""
        db = _fresh_db()
        svc, ledger_repo, session_repo = _build_service(db)

        session_a = session_repo.create(
            CashierSession(id=None, day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0)
        )
        order = svc._orders.save(_paid_active_order(shift_id=1))
        ledger_repo.append(CashLedgerEntry(
            id=None, day_id=1, session_id=session_a.id,
            entry_type=LedgerEntryType.SALE_CASH, amount_pt=7000,
            order_id=order.id, actor_id=2,
        ))

        svc.cancel_order(order.id, manager_pin="1234", reason="تست")

        assert ledger_repo.get_session_balance_pt(session_a.id) == 0
        reversal = ledger_repo.get_entry_by_order(order.id, LedgerEntryType.REVERSAL)
        assert reversal.session_id == session_a.id

    def test_cancel_rejected_outright_when_no_session_open_at_all(self):
        """H10 addendum: with no open till anywhere, the cancellation must
        fail completely — not cancel the order while silently skipping the
        refund."""
        db = _fresh_db()
        svc, ledger_repo, session_repo = _build_service(db)

        # Sale was recorded against a session that has since closed, and no
        # new session was opened — there is nowhere to post the refund.
        session_a = session_repo.create(
            CashierSession(id=None, day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0)
        )
        order = svc._orders.save(_paid_active_order(shift_id=1))
        ledger_repo.append(CashLedgerEntry(
            id=None, day_id=1, session_id=session_a.id,
            entry_type=LedgerEntryType.SALE_CASH, amount_pt=7000,
            order_id=order.id, actor_id=2,
        ))
        session_repo.close_session(
            session_id=session_a.id,
            counted_cash_pt=7000, expected_cash_pt=7000, variance_pt=0,
        )

        with pytest.raises(ValueError):
            svc.cancel_order(order.id, manager_pin="1234", reason="تست")

        unchanged_order = svc._orders.get_by_id(order.id)
        assert unchanged_order.status == OrderStatus.NEW, (
            "H10 regression: the order was cancelled even though no refund "
            "could be posted anywhere"
        )
        assert ledger_repo.get_entry_by_order(order.id, LedgerEntryType.REVERSAL) is None
        assert ledger_repo.get_session_balance_pt(session_a.id) == 7000, (
            "The closed session's sealed balance must remain untouched"
        )
