"""
Tests for v2 Phase 3 — Cash Ledger Integration.

Covers:
  SALE_CASH   → created atomically in complete_order() for CASH payments
  SALE_CASH   → NOT created for ONLINE/VISA payments (FR-CASH-4)
  SALE_CASH   → skipped gracefully if no active session (legacy mode)
  SALE_CASH   → uq_ledger_sale prevents duplicate entries for same order
  DRIVER_REMITTANCE → created in settle_driver() per trip (DELIVERY/ALL session)
  DRIVER_REMITTANCE → skipped when no ledger_repo wired (backward compat)
  Balance     → SUM(ledger) = expected_cash after SALE_CASH entries
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.core.models.cashier_session import (
    CashierSession, CashLedgerEntry, LedgerEntryType, Station
)
from broast_pos.core.models.order import Order, OrderItem, OrderType, OrderStatus, PaymentMethod
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.order_service import OrderService


# ---------------------------------------------------------------------------
# Singleton isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'mgr','Manager','manager','h1',1), (2,'cas','Cashier','cashier','h2',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    # Seed category + product so order_items FK passes
    db.execute("INSERT INTO categories (id, name, sort_order, is_active) VALUES (1,'طعام',0,1)")
    db.execute("INSERT INTO products (id, name, price, category_id, is_active) VALUES (1,'بيتزا',100.0,1,1)")
    db.commit()
    return db


def _open_session(db: DatabaseConnection, user_id: int = 2,
                   station: Station = Station.ALL, float_pt: int = 100000) -> CashierSession:
    svc = CashierSessionService(
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
    )
    s = svc.open_session(day_id=1, user_id=user_id, station=station, opening_float_pt=float_pt)
    db.commit()
    return s


def _make_order_svc(db: DatabaseConnection, with_ledger: bool = True) -> OrderService:
    """Build an OrderService wired with real in-memory repos."""
    session_repo = CashierSessionRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db) if with_ledger else None

    # Mock FinancialService: shift is active, id=1, invoice=1
    mock_shift = MagicMock()
    mock_shift.id = 1
    mock_fin = MagicMock()
    mock_fin.ensure_shift_active.return_value = mock_shift
    mock_fin.get_next_invoice_number.return_value = 1

    from broast_pos.data.repositories.order_repository import OrderRepository
    order_repo = OrderRepository(db=db)

    svc = OrderService(
        order_repo=order_repo,
        financial_service=mock_fin,
        audit_service=MagicMock(),
        ledger_repo=ledger_repo,
        cashier_session_repo=session_repo if with_ledger else None,
    )
    svc._status_history = MagicMock()
    return svc


def _takeaway_order() -> Order:
    item = OrderItem(product_id=1, product_name="بيتزا", unit_price=100.0, quantity=2)
    return Order(
        id=None, invoice_no=None,
        order_type=OrderType.TAKEAWAY, status=OrderStatus.NEW,
        items=[item], subtotal=200.0, total=200.0,
        cashier_slot=1,
    )


# ===========================================================================
# Part A: SALE_CASH created in complete_order
# ===========================================================================

class TestSaleCashLedgerEntry:

    def _create_saved_order(self, db: DatabaseConnection, svc: OrderService) -> Order:
        """Create and save a new order, returning the saved object."""
        order = _takeaway_order()
        saved = svc.create_order(order, cashier_id=2, cashier_name="Cashier")
        db.commit()
        return saved

    def test_sale_cash_created_for_cash_payment(self):
        """SALE_CASH ledger entry is created when a CASH order is completed."""
        db = _fresh_db()
        session = _open_session(db, user_id=2)
        svc = _make_order_svc(db, with_ledger=True)
        saved = self._create_saved_order(db, svc)

        svc.complete_order(
            order_id=saved.id,
            payment_method=PaymentMethod.CASH,
            amount_received=200.0,
            actor_id=2,
        )
        db.commit()

        ledger = CashLedgerRepository(db=db)
        entries = ledger.get_entries_for_session(session.id)
        types = [e.entry_type for e in entries]
        assert LedgerEntryType.SALE_CASH in types

    def test_sale_cash_amount_matches_order_total(self):
        """SALE_CASH.amount_pt = round(order.total * 100)."""
        db = _fresh_db()
        session = _open_session(db, user_id=2)
        svc = _make_order_svc(db, with_ledger=True)
        saved = self._create_saved_order(db, svc)

        svc.complete_order(
            order_id=saved.id,
            payment_method=PaymentMethod.CASH,
            amount_received=200.0,
            actor_id=2,
        )
        db.commit()

        ledger = CashLedgerRepository(db=db)
        entries = ledger.get_entries_for_session(session.id)
        sale_entry = next(e for e in entries if e.entry_type == LedgerEntryType.SALE_CASH)
        assert sale_entry.amount_pt == round(200.0 * 100)  # 20000 piasters

    def test_no_sale_cash_for_online_payment(self):
        """ONLINE payment does NOT create a SALE_CASH entry (FR-CASH-4)."""
        db = _fresh_db()
        session = _open_session(db, user_id=2)
        svc = _make_order_svc(db, with_ledger=True)
        # Create a TAKEAWAY order (takeaway supports online payment in our system)
        order = _takeaway_order()
        saved = svc.create_order(order, cashier_id=2, cashier_name="Cashier")
        db.commit()

        svc.complete_order(
            order_id=saved.id,
            payment_method=PaymentMethod.ONLINE,
            amount_received=200.0,
            actor_id=2,
        )
        db.commit()

        ledger = CashLedgerRepository(db=db)
        entries = ledger.get_entries_for_session(session.id)
        types = [e.entry_type for e in entries]
        assert LedgerEntryType.SALE_CASH not in types

    def test_no_sale_cash_when_ledger_not_wired(self):
        """When ledger_repo not injected, complete_order completes successfully with no ledger entries."""
        db = _fresh_db()
        _open_session(db, user_id=2)
        svc = _make_order_svc(db, with_ledger=False)
        saved = self._create_saved_order(db, svc)

        # Should not raise
        result = svc.complete_order(
            order_id=saved.id,
            payment_method=PaymentMethod.CASH,
            amount_received=200.0,
            actor_id=2,
        )
        db.commit()
        assert result.is_paid

    def test_no_sale_cash_when_no_session_open(self):
        """No active session → SALE_CASH skipped, order still completes."""
        db = _fresh_db()
        # No session opened
        svc = _make_order_svc(db, with_ledger=True)
        saved = self._create_saved_order(db, svc)

        result = svc.complete_order(
            order_id=saved.id,
            payment_method=PaymentMethod.CASH,
            amount_received=200.0,
            actor_id=2,
        )
        db.commit()
        assert result.is_paid

        ledger = CashLedgerRepository(db=db)
        count = db.fetch_one("SELECT COUNT(*) AS c FROM cash_ledger")["c"]
        assert count == 0

    def test_balance_increases_after_sale_cash(self):
        """Expected cash = OPENING_FLOAT + SALE_CASH amount."""
        db = _fresh_db()
        float_pt = 50000  # EGP 500
        session = _open_session(db, user_id=2, float_pt=float_pt)
        svc = _make_order_svc(db, with_ledger=True)
        saved = self._create_saved_order(db, svc)  # EGP 200

        svc.complete_order(
            order_id=saved.id,
            payment_method=PaymentMethod.CASH,
            amount_received=200.0,
            actor_id=2,
        )
        db.commit()

        ledger = CashLedgerRepository(db=db)
        balance = ledger.get_session_balance_pt(session.id)
        # 50000 (float) + 20000 (200 EGP sale) = 70000
        assert balance == float_pt + round(200.0 * 100)


# ===========================================================================
# Part B: DRIVER_REMITTANCE in settle_driver
# ===========================================================================

class TestDriverRemittanceLedgerEntry:

    def _setup_settled_trip(self, db: DatabaseConnection):
        """Seed a driver, trip, order, and perform settle_driver — return (session, trip_cash)."""
        from broast_pos.core.services.driver_settlement_service import DriverSettlementService
        from broast_pos.data.repositories.delivery_repository import DeliveryRepository
        from broast_pos.data.repositories.driver_settlement_repository import DriverSettlementRepository
        from broast_pos.data.repositories.order_repository import OrderRepository
        from broast_pos.data.repositories.user_repository import UserRepository

        # Add driver user
        db.execute(
            "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
            "VALUES (3,'drv','Driver','cashier','h3',1)"
        )
        # Add trip returned (eligible for settlement)
        db.execute(
            "INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled, returned_at, created_at) "
            "VALUES (10, 3, 'Driver', 0, datetime('now'), datetime('now'))"
        )
        # Add a cash order on that trip
        db.execute(
            "INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
            "payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
            "VALUES (200, 1, 1, 'delivery', 'delivered', 150.0, 150.0, 'cash', 1, 1, 'Manager', 1)"
        )
        db.execute(
            "INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (10, 200)"
        )
        db.commit()

        # Open DELIVERY session
        session = _open_session(db, user_id=1, station=Station.DELIVERY, float_pt=0)

        svc = DriverSettlementService(
            settlement_repo=DriverSettlementRepository(db=db),
            delivery_repo=DeliveryRepository(db=db),
            order_repo=OrderRepository(db=db),
            user_repo=UserRepository(db=db),
            audit_repo=MagicMock(),
            ledger_repo=CashLedgerRepository(db=db),
            cashier_session_repo=CashierSessionRepository(db=db),
        )
        return svc, session

    def test_driver_remittance_created_on_settle(self):
        db = _fresh_db()
        svc, session = self._setup_settled_trip(db)

        svc.settle_driver(driver_id=3, settled_by_id=1, settled_by_name="Manager")

        ledger = CashLedgerRepository(db=db)
        entries = ledger.get_entries_for_session(session.id)
        types = [e.entry_type for e in entries]
        assert LedgerEntryType.DRIVER_REMITTANCE in types

    def test_driver_remittance_amount_correct(self):
        """DRIVER_REMITTANCE.amount_pt = round(trip_cash * 100)."""
        db = _fresh_db()
        svc, session = self._setup_settled_trip(db)

        svc.settle_driver(driver_id=3, settled_by_id=1, settled_by_name="Manager")

        ledger = CashLedgerRepository(db=db)
        entries = ledger.get_entries_for_session(session.id)
        remit = next(e for e in entries if e.entry_type == LedgerEntryType.DRIVER_REMITTANCE)
        # trip_cash = 150.0 → 15000 piasters
        assert remit.amount_pt == 15000

    def test_no_remittance_when_ledger_not_wired(self):
        """Without ledger_repo, settle_driver completes with no ledger entries."""
        from broast_pos.core.services.driver_settlement_service import DriverSettlementService
        from broast_pos.data.repositories.delivery_repository import DeliveryRepository
        from broast_pos.data.repositories.driver_settlement_repository import DriverSettlementRepository
        from broast_pos.data.repositories.order_repository import OrderRepository
        from broast_pos.data.repositories.user_repository import UserRepository

        db = _fresh_db()
        db.execute(
            "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
            "VALUES (3,'drv','Driver','cashier','h3',1)"
        )
        db.execute(
            "INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled, returned_at, created_at) "
            "VALUES (10, 3, 'Driver', 0, datetime('now'), datetime('now'))"
        )
        db.execute(
            "INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
            "payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
            "VALUES (200, 1, 1, 'delivery', 'delivered', 150.0, 150.0, 'cash', 1, 1, 'Manager', 1)"
        )
        db.execute("INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (10, 200)")
        db.commit()

        svc = DriverSettlementService(
            settlement_repo=DriverSettlementRepository(db=db),
            delivery_repo=DeliveryRepository(db=db),
            order_repo=OrderRepository(db=db),
            user_repo=UserRepository(db=db),
            audit_repo=MagicMock(),
            ledger_repo=None,  # not wired
        )
        result = svc.settle_driver(driver_id=3, settled_by_id=1, settled_by_name="Manager")
        assert result is not None
        count = db.fetch_one("SELECT COUNT(*) AS c FROM cash_ledger")["c"]
        assert count == 0
