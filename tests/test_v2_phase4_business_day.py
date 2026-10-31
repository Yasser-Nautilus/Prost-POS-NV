"""
Tests for v2 Phase 4 — BusinessDayService: X-Report, Z-Report, DRIVER_FEE_PAYOUT.

Covers:
  FR-DAY-1  close_business_day: blocked if any session still open (Arabic msg)
  FR-DAY-2  DRIVER_FEE_PAYOUT batch: entry created for each settled trip
  FR-DAY-2  Idempotency: re-running batch does not create duplicate entries
  FR-DAY-3  X-Report: live snapshot — expected_cash = SUM(ledger)
  FR-DAY-3  Z-Report: total_variance_pt = sum of session variances
  FR-DAY-3  Z-Report: breakdown contains all entry types
  ADR-1     Expected cash comes from ledger, never from orders table
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.core.models.cashier_session import (
    CashierSession, CashLedgerEntry, LedgerEntryType, Station,
)
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.business_day_service import (
    BusinessDayService, XReport, ZReport, SessionSnapshot,
)


# ---------------------------------------------------------------------------
# Singleton isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


# ---------------------------------------------------------------------------
# Shared helpers
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
    db.commit()
    return db


def _make_svc(db: DatabaseConnection, financial_svc=None) -> BusinessDayService:
    return BusinessDayService(
        financial_service=financial_svc,
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
        auth_service=None,
    )


def _open_session(db: DatabaseConnection, user_id: int = 2,
                   station: Station = Station.ALL, float_pt: int = 50000) -> CashierSession:
    svc = CashierSessionService(
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
    )
    s = svc.open_session(day_id=1, user_id=user_id, station=station, opening_float_pt=float_pt)
    db.commit()
    return s


def _close_session(db: DatabaseConnection, session_id: int, counted_pt: int) -> CashierSession:
    svc = CashierSessionService(
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
    )
    s = svc.close_session(session_id=session_id, counted_cash_pt=counted_pt, actor_id=1)
    db.commit()
    return s


def _add_ledger(db: DatabaseConnection, session_id: int, entry_type: LedgerEntryType,
                amount_pt: int) -> None:
    repo = CashLedgerRepository(db=db)
    repo.append(CashLedgerEntry(
        id=None, day_id=1, session_id=session_id,
        entry_type=entry_type, amount_pt=amount_pt, actor_id=1,
    ))
    db.commit()


# ===========================================================================
# Part A: FR-DAY-1 — Session close guard
# ===========================================================================

class TestDayCloseSessionGuard:

    def test_close_blocked_when_session_open(self):
        """close_business_day raises if any session is still open."""
        db = _fresh_db()
        _open_session(db)
        svc = _make_svc(db)
        with pytest.raises(ValueError, match="وردية مفتوحة"):
            svc.close_business_day(day_id=1)

    def test_close_blocked_lists_open_station(self):
        """Error message includes the station name of the open session."""
        db = _fresh_db()
        _open_session(db, station=Station.COUNTER)
        svc = _make_svc(db)
        with pytest.raises(ValueError, match="COUNTER"):
            svc.close_business_day(day_id=1)

    def test_close_allowed_when_all_sessions_closed(self):
        """Day can close once all sessions are closed (financial_svc=None skips shift close)."""
        db = _fresh_db()
        s = _open_session(db)
        _close_session(db, s.id, counted_pt=50000)
        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)   # financial_svc=None → no shift close
        assert isinstance(z, ZReport)

    def test_close_no_sessions_allowed(self):
        """No sessions at all → also allowed to close (legacy mode)."""
        db = _fresh_db()
        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)
        assert isinstance(z, ZReport)
        assert z.sessions == []


# ===========================================================================
# Part B: FR-DAY-3 — X-Report
# ===========================================================================

class TestXReport:

    def test_x_report_empty_day(self):
        db = _fresh_db()
        svc = _make_svc(db)
        r = svc.generate_x_report(day_id=1)
        assert isinstance(r, XReport)
        assert r.day_id == 1
        assert r.sessions == []
        assert r.total_expected_cash_pt == 0

    def test_x_report_includes_open_session(self):
        db = _fresh_db()
        s = _open_session(db, float_pt=100000)
        svc = _make_svc(db)
        r = svc.generate_x_report(day_id=1)
        assert len(r.sessions) == 1
        snap = r.sessions[0]
        assert snap.session_id == s.id
        assert snap.is_open
        assert snap.expected_cash_pt == 100000   # = OPENING_FLOAT entry

    def test_x_report_cash_sales_breakdown(self):
        db = _fresh_db()
        s = _open_session(db, float_pt=50000)
        _add_ledger(db, s.id, LedgerEntryType.SALE_CASH, 20000)
        _add_ledger(db, s.id, LedgerEntryType.EXPENSE, -5000)
        svc = _make_svc(db)
        r = svc.generate_x_report(day_id=1)
        snap = r.sessions[0]
        # balance = 50000 + 20000 - 5000 = 65000
        assert snap.expected_cash_pt == 65000
        assert snap.breakdown["SALE_CASH"] == 20000
        assert snap.breakdown["EXPENSE"] == -5000

    def test_x_report_total_expected_across_two_sessions(self):
        db = _fresh_db()
        s1 = _open_session(db, user_id=1, station=Station.COUNTER, float_pt=30000)
        s2 = _open_session(db, user_id=2, station=Station.DELIVERY, float_pt=20000)
        _add_ledger(db, s1.id, LedgerEntryType.SALE_CASH, 10000)
        svc = _make_svc(db)
        r = svc.generate_x_report(day_id=1)
        assert len(r.sessions) == 2
        # s1: 30000 + 10000 = 40000, s2: 20000 → total = 60000
        assert r.total_expected_cash_pt == 60000

    def test_x_report_total_cash_sales(self):
        db = _fresh_db()
        s = _open_session(db, float_pt=0)
        _add_ledger(db, s.id, LedgerEntryType.SALE_CASH, 15000)
        _add_ledger(db, s.id, LedgerEntryType.SALE_CASH, 8000)
        svc = _make_svc(db)
        r = svc.generate_x_report(day_id=1)
        assert r.total_cash_sales_pt == 23000

    def test_x_report_adr1_cash_from_ledger_not_orders(self):
        """ADR-1: expected_cash comes from ledger SUM, not orders table."""
        db = _fresh_db()
        # Seed an order in DB but DO NOT add SALE_CASH entry → should not affect balance
        db.execute(
            "INSERT INTO categories (id, name, sort_order, is_active) VALUES (1,'طعام',0,1)"
        )
        db.execute(
            "INSERT INTO products (id, name, price, category_id) VALUES (1,'P',50.0,1)"
        )
        db.execute(
            "INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
            "payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
            "VALUES (1, 1, 1, 'takeaway', 'completed', 100.0, 100.0, 'cash', 1, 1, 'M', 1)"
        )
        db.commit()
        s = _open_session(db, float_pt=0)
        # No SALE_CASH entry added to ledger
        svc = _make_svc(db)
        r = svc.generate_x_report(day_id=1)
        # Expected cash = 0 (ledger is empty for this session) — order NOT counted
        assert r.total_expected_cash_pt == 0
        assert r.total_cash_sales_pt == 0


# ===========================================================================
# Part C: Z-Report from close_business_day
# ===========================================================================

class TestZReport:

    def test_z_report_produced_on_close(self):
        db = _fresh_db()
        s = _open_session(db, float_pt=100000)
        _add_ledger(db, s.id, LedgerEntryType.SALE_CASH, 20000)
        _close_session(db, s.id, counted_pt=120000)
        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)
        assert isinstance(z, ZReport)
        assert z.day_id == 1
        assert len(z.sessions) == 1

    def test_z_report_no_variance_exact_count(self):
        db = _fresh_db()
        s = _open_session(db, float_pt=100000)
        _add_ledger(db, s.id, LedgerEntryType.SALE_CASH, 20000)
        # Expected = 120000; count exactly 120000 → variance = 0
        _close_session(db, s.id, counted_pt=120000)
        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)
        assert z.total_variance_pt == 0

    def test_z_report_variance_aggregated(self):
        """Z-Report total_variance = sum of all session variances."""
        db = _fresh_db()
        s1 = _open_session(db, user_id=1, station=Station.COUNTER, float_pt=100000)
        s2 = _open_session(db, user_id=2, station=Station.DELIVERY, float_pt=50000)
        # s1: expected=100000, count=99000 → variance=-1000
        _close_session(db, s1.id, counted_pt=99000)
        # s2: expected=50000, count=51000 → variance=+1000
        _close_session(db, s2.id, counted_pt=51000)
        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)
        # -1000 + 1000 = 0
        assert z.total_variance_pt == 0

    def test_z_report_total_expected_uses_ledger(self):
        """Total expected cash in Z-Report = SUM(all session ledger balances)."""
        db = _fresh_db()
        s = _open_session(db, float_pt=80000)
        _add_ledger(db, s.id, LedgerEntryType.SALE_CASH, 25000)
        _close_session(db, s.id, counted_pt=105000)
        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)
        # expected = 80000 (float) + 25000 (sale) = 105000
        # After close, ADJUSTMENT = 0 (exact), so total still 105000
        assert z.total_expected_cash_pt == 105000


# ===========================================================================
# Part D: FR-DAY-2 — DRIVER_FEE_PAYOUT batch
# ===========================================================================

class TestDriverFeePayoutBatch:

    def _seed_settled_trip(self, db: DatabaseConnection,
                            trip_id: int, fee: float, session: CashierSession) -> None:
        """Seed a settled delivery trip with a given fee."""
        uid = trip_id + 100
        db.execute(
            "INSERT OR IGNORE INTO users (id, username, display_name, role, pin_hash, is_active) "
            f"VALUES ({uid},'drv{trip_id}','Driver{trip_id}','cashier','h{trip_id}x{uid}',1)"
        )
        db.execute(
            f"INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled, "
            f"returned_at, total_delivery_fees, created_at) "
            f"VALUES ({trip_id}, {trip_id+100}, 'Driver', 1, datetime('now'), {fee}, datetime('now'))"
        )
        db.execute(
            "INSERT INTO categories (id, name, sort_order, is_active) "
            "VALUES (99,'طعام',0,1) ON CONFLICT(id) DO NOTHING"
        )
        db.execute(
            "INSERT INTO products (id, name, price, category_id) "
            "VALUES (99,'P',50.0,99) ON CONFLICT(id) DO NOTHING"
        )
        db.execute(
            f"INSERT INTO orders (id, invoice_no, shift_id, order_type, status, "
            f"subtotal, total, payment_method, is_paid, created_by_id, created_by_name, cashier_slot) "
            f"VALUES ({trip_id*10}, {trip_id}, 1, 'delivery', 'completed', 100.0, 100.0, 'cash', 1, 1, 'M', 1)"
        )
        db.execute(
            f"INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES ({trip_id}, {trip_id*10})"
        )
        db.commit()

    def test_fee_payout_created_for_settled_trip(self):
        db = _fresh_db()
        s = _open_session(db, station=Station.DELIVERY, float_pt=100000)
        self._seed_settled_trip(db, trip_id=1, fee=50.0, session=s)
        _close_session(db, s.id, counted_pt=100000)

        svc = _make_svc(db, financial_svc=None)
        z = svc.close_business_day(day_id=1)

        # Verify DRIVER_FEE_PAYOUT entry exists
        entries = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'"
        )
        assert len(entries) == 1
        assert entries[0]["amount_pt"] == -5000  # -50.00 EGP = -5000 pt

    def test_fee_payout_amount_correct(self):
        db = _fresh_db()
        s = _open_session(db, station=Station.ALL, float_pt=200000)
        self._seed_settled_trip(db, trip_id=2, fee=75.50, session=s)
        _close_session(db, s.id, counted_pt=200000)

        svc = _make_svc(db, financial_svc=None)
        svc.close_business_day(day_id=1)

        entries = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(entries) == 1
        assert entries[0]["amount_pt"] == -7550   # -75.50 EGP

    def test_fee_payout_idempotent(self):
        """Running batch twice does NOT create duplicate entries."""
        db = _fresh_db()
        s = _open_session(db, station=Station.DELIVERY, float_pt=100000)
        self._seed_settled_trip(db, trip_id=3, fee=30.0, session=s)
        _close_session(db, s.id, counted_pt=100000)

        svc = _make_svc(db, financial_svc=None)
        svc._batch_driver_fee_payouts(day_id=1)
        svc._batch_driver_fee_payouts(day_id=1)  # second run

        entries = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(entries) == 1  # Only ONE entry, not two

    def test_no_fee_payout_without_session(self):
        """No DELIVERY/ALL session → batch skipped, no entries."""
        db = _fresh_db()
        # Open a COUNTER session only
        s = _open_session(db, station=Station.COUNTER, float_pt=0)
        self._seed_settled_trip(db, trip_id=4, fee=20.0, session=s)
        _close_session(db, s.id, counted_pt=0)

        svc = _make_svc(db, financial_svc=None)
        count = svc._batch_driver_fee_payouts(day_id=1)
        assert count == 0

    def test_multiple_trips_multiple_entries(self):
        db = _fresh_db()
        s = _open_session(db, station=Station.DELIVERY, float_pt=0)
        self._seed_settled_trip(db, trip_id=5, fee=40.0, session=s)
        self._seed_settled_trip(db, trip_id=6, fee=60.0, session=s)
        _close_session(db, s.id, counted_pt=0)

        svc = _make_svc(db, financial_svc=None)
        count = svc._batch_driver_fee_payouts(day_id=1)
        assert count == 2
        entries = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(entries) == 2
        total_pt = sum(e["amount_pt"] for e in entries)
        assert total_pt == -(4000 + 6000)  # -40 + -60 EGP = -10000 pt


# ===========================================================================
# Part E: SessionSnapshot model
# ===========================================================================

class TestSessionSnapshot:

    def test_expected_cash_egp_conversion(self):
        snap = SessionSnapshot(
            session_id=1, user_id=1, station="ALL", is_open=False,
            opened_at="2026-10-05T10:00:00Z", closed_at="2026-10-05T18:00:00Z",
            opening_float_pt=50000, expected_cash_pt=75000,
            counted_cash_pt=74000, variance_pt=-1000,
            breakdown={},
        )
        assert snap.expected_cash_egp == pytest.approx(750.0)
        assert snap.variance_egp == pytest.approx(-10.0)

    def test_variance_none_when_session_open(self):
        snap = SessionSnapshot(
            session_id=1, user_id=1, station="COUNTER", is_open=True,
            opened_at="2026-10-05T10:00:00Z", closed_at=None,
            opening_float_pt=0, expected_cash_pt=0,
            counted_cash_pt=None, variance_pt=None,
            breakdown={},
        )
        assert snap.variance_egp is None
