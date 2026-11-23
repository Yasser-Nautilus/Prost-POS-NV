"""
Regression tests — H12: a genuine remittance write failure was treated as
an already-recorded duplicate.

Root cause:
  DriverSettlementService._create_driver_remittance_entry() caught every
  exception from the ledger append and logged it as "already recorded"
  (uq_ledger_remit idempotency), then continued as if the remittance had
  succeeded. A disk error, bad foreign key, or any other write failure was
  silently swallowed the same way as a genuine duplicate retry.

Fix verified here:
  - A non-integrity write failure (e.g. a disk error) propagates — it is
    NOT treated as a successful retry.
  - A genuine duplicate (same trip, same amount/day/session) is still
    idempotent and does not raise.
  - A duplicate trip_id whose existing row does NOT match the intended
    entry (different amount/day/session) raises instead of being silently
    accepted — that's a conflict, not a safe retry.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.cashier_session import LedgerEntryType, Station
from broast_pos.core.services.driver_settlement_service import DriverSettlementService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
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
    db.execute(
        "INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled, returned_at, created_at) "
        "VALUES (10, 3, 'سائق', 0, datetime('now'), datetime('now'))"
    )
    db.execute("INSERT INTO categories (id, name, sort_order, is_active) VALUES (1,'طعام',0,1)")
    db.execute("INSERT INTO products (id, name, price, category_id, is_active) VALUES (1,'بيتزا',100.0,1,1)")
    db.execute(
        "INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
        "payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
        "VALUES (200, 1, 1, 'delivery', 'delivered', 150.0, 150.0, 'cash', 1, 1, 'مدير', 1)"
    )
    db.commit()
    return db


def _build_service(db: DatabaseConnection) -> DriverSettlementService:
    return DriverSettlementService(
        order_repo=OrderRepository(db=db),
        audit_repo=MagicMock(),
        ledger_repo=CashLedgerRepository(db=db),
        cashier_session_repo=CashierSessionRepository(db=db),
    )


def _open_delivery_session(db: DatabaseConnection):
    session_repo = CashierSessionRepository(db=db)
    from broast_pos.core.models.cashier_session import CashierSession
    return session_repo.create(
        CashierSession(id=None, day_id=1, user_id=1, station=Station.DELIVERY, opening_float_pt=0)
    )


def _trip():
    return SimpleNamespace(id=10, order_ids=[200])


class TestH12GenuineFailureNotSwallowed:

    def test_non_integrity_write_failure_propagates(self):
        """A real DB error must not be mistaken for a safe duplicate retry."""
        db = _fresh_db()
        _open_delivery_session(db)
        svc = _build_service(db)

        svc._ledger.append = MagicMock(
            side_effect=sqlite3.OperationalError("disk I/O error")
        )

        with pytest.raises(sqlite3.OperationalError):
            svc.remit_trip_cash(_trip(), trip_cash=150.0, actor_id=1)

    def test_generic_exception_propagates(self):
        """Any non-sqlite exception must also propagate, never be swallowed."""
        db = _fresh_db()
        _open_delivery_session(db)
        svc = _build_service(db)

        svc._ledger.append = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            svc.remit_trip_cash(_trip(), trip_cash=150.0, actor_id=1)

    def test_genuine_duplicate_is_idempotent(self):
        """Calling remit_trip_cash twice for the same trip/amount is a no-op."""
        db = _fresh_db()
        _open_delivery_session(db)
        svc = _build_service(db)

        svc.remit_trip_cash(_trip(), trip_cash=150.0, actor_id=1)
        # Second call hits uq_ledger_remit with an IDENTICAL existing row.
        svc.remit_trip_cash(_trip(), trip_cash=150.0, actor_id=1)

        entries = svc._ledger.get_entries_for_session(
            svc._cashier_sessions.get_open_sessions_for_day(1)[0].id
        )
        remits = [e for e in entries if e.entry_type == LedgerEntryType.DRIVER_REMITTANCE]
        assert len(remits) == 1, "Duplicate retry must not create a second entry"

    def test_mismatched_duplicate_raises_instead_of_silently_succeeding(self):
        """A conflicting existing row for the same trip must raise, not be accepted."""
        db = _fresh_db()
        _open_delivery_session(db)
        svc = _build_service(db)

        # Pre-existing remittance for trip 10 with a DIFFERENT amount — this
        # should never happen organically, but must not be papered over if it does.
        svc.remit_trip_cash(_trip(), trip_cash=150.0, actor_id=1)

        with pytest.raises(ValueError, match="conflict"):
            svc._create_driver_remittance_entry(
                trip_id=10, day_id=1, trip_cash=200.0, actor_id=1,
            )
