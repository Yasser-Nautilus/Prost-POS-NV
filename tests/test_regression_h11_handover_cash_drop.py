"""
Regression tests for H11: Cash Drop at Handover (Entnahme bei Übergabe).

Requirements:
- Ensure: 0 ≤ cash_drop ≤ counted_cash
- Atomically book cash drop (CASH_DROP entry), safe deposit, and new session opening float
- Invalid cash drop amounts (negative or exceeding counted cash) are rejected
- Overall cash balance is conserved and remains correct after handover
"""

from __future__ import annotations

import pytest

from broast_pos.core.models.cashier_session import (
    CashLedgerEntry,
    LedgerEntryType,
    Station,
)
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.features.financial.session_controller import SessionController


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
        "VALUES (1,'mgr','Manager','manager','h1',1), (2,'cas','Cashier','cashier','h2',1), "
        "(3,'cas2','Cashier 2','cashier','h3',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.commit()
    return db


def _make_svc(db: DatabaseConnection) -> CashierSessionService:
    return CashierSessionService(
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
        auth_service=None,
    )


def _make_ctrl(db: DatabaseConnection) -> SessionController:
    session_repo = CashierSessionRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    svc = CashierSessionService(
        session_repo=session_repo,
        ledger_repo=ledger_repo,
    )
    day_svc = BusinessDayService(
        financial_service=None,
        session_repo=session_repo,
        ledger_repo=ledger_repo,
    )
    return SessionController(
        session_service=svc,
        business_day_service=day_svc,
    )


class TestH11CashDropValidation:
    """Test 0 ≤ cash_drop ≤ counted_cash validation."""

    def test_negative_cash_drop_rejected_in_service(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        with pytest.raises(ValueError, match="لا يمكن أن يكون سالباً"):
            svc.do_handover(
                from_session_id=s.id,
                to_user_id=3,
                station=Station.ALL,
                to_user_counted_pt=50000,
                cash_drop_pt=-1000,
            )

    def test_negative_cash_drop_rejected_in_controller(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        s = ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=500.0)

        with pytest.raises(ValueError, match="لا يمكن أن يكون سالباً"):
            ctrl.do_handover(
                from_session_id=s["id"],
                to_user_id=3,
                station="ALL",
                counted_cash_egp=500.0,
                cash_drop_egp=-10.0,
            )

    def test_cash_drop_exceeding_counted_rejected_in_service(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        with pytest.raises(ValueError, match="لا يمكن أن يتجاوز المبلغ المعدود"):
            svc.do_handover(
                from_session_id=s.id,
                to_user_id=3,
                station=Station.ALL,
                to_user_counted_pt=50000,
                cash_drop_pt=60000,  # 600 > 500
            )

    def test_cash_drop_exceeding_counted_rejected_in_controller(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        s = ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=500.0)

        with pytest.raises(ValueError, match="لا يمكن أن يتجاوز المبلغ المعدود"):
            ctrl.do_handover(
                from_session_id=s["id"],
                to_user_id=3,
                station="ALL",
                counted_cash_egp=500.0,
                cash_drop_egp=550.0,
            )

    def test_negative_counted_cash_rejected(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        with pytest.raises(ValueError, match="لا يمكن أن يكون سالباً"):
            svc.do_handover(
                from_session_id=s.id,
                to_user_id=3,
                station=Station.ALL,
                to_user_counted_pt=-5000,
                cash_drop_pt=0,
            )

    def test_cash_drop_exceeding_expected_when_counted_omitted(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        # When to_user_counted_pt is None, counted defaults to expected_pt (50000)
        with pytest.raises(ValueError, match="لا يمكن أن يتجاوز المبلغ المعدود"):
            svc.do_handover(
                from_session_id=s.id,
                to_user_id=3,
                station=Station.ALL,
                cash_drop_pt=50001,
            )


class TestH11AtomicBookingAndLedger:
    """Test ledger booking, atomic execution, and balance conservation."""

    def test_zero_cash_drop_creates_no_cash_drop_entry(self):
        db = _fresh_db()
        svc = _make_svc(db)
        ledger = CashLedgerRepository(db=db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        closed, new_s = svc.do_handover(
            from_session_id=s.id,
            to_user_id=3,
            station=Station.ALL,
            to_user_counted_pt=50000,
            cash_drop_pt=0,
        )
        db.commit()

        entries_old = ledger.get_entries_for_session(closed.id)
        types_old = [e.entry_type for e in entries_old]
        assert LedgerEntryType.CASH_DROP not in types_old
        assert LedgerEntryType.HANDOVER_OUT in types_old
        assert ledger.get_session_balance_pt(closed.id) == 0

        entries_new = ledger.get_entries_for_session(new_s.id)
        types_new = [e.entry_type for e in entries_new]
        assert LedgerEntryType.HANDOVER_IN in types_new
        assert ledger.get_session_balance_pt(new_s.id) == 50000
        assert new_s.opening_float_pt == 50000

    def test_cash_drop_creates_ledger_entry_and_conserves_balance(self):
        """
        Session 1: opens with 100,000 pt (1000 EGP).
        Handover with counted 100,000 pt, cash_drop 30,000 pt (300 EGP to safe).
        Result:
        - Outgoing session gets CASH_DROP (-30000) and HANDOVER_OUT (-70000)
        - Outgoing session balance is exactly 0
        - Incoming session gets HANDOVER_IN (+70000) and opening float 70000
        - Incoming session balance is exactly 70000
        - Ledger repository cash drop total for session is 30000
        - Total money accounted for = Drawer (70000) + Safe (30000) = 100000
        """
        db = _fresh_db()
        svc = _make_svc(db)
        ledger = CashLedgerRepository(db=db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=100000)
        db.commit()

        closed, new_s = svc.do_handover(
            from_session_id=s.id,
            to_user_id=3,
            station=Station.ALL,
            to_user_counted_pt=100000,
            cash_drop_pt=30000,
        )
        db.commit()

        # Outgoing session
        assert not closed.is_open
        entries_old = ledger.get_entries_for_session(closed.id)
        drop_entries = [e for e in entries_old if e.entry_type == LedgerEntryType.CASH_DROP]
        out_entries = [e for e in entries_old if e.entry_type == LedgerEntryType.HANDOVER_OUT]
        assert len(drop_entries) == 1
        assert drop_entries[0].amount_pt == -30000
        assert len(out_entries) == 1
        assert out_entries[0].amount_pt == -70000

        # Outgoing drawer balance is exactly 0
        assert ledger.get_session_balance_pt(closed.id) == 0

        # Incoming session
        assert new_s.is_open
        assert new_s.opening_float_pt == 70000
        entries_new = ledger.get_entries_for_session(new_s.id)
        in_entries = [e for e in entries_new if e.entry_type == LedgerEntryType.HANDOVER_IN]
        assert len(in_entries) == 1
        assert in_entries[0].amount_pt == 70000
        assert ledger.get_session_balance_pt(new_s.id) == 70000

        # Cash drop repository helper
        assert ledger.get_cash_drop_total_pt(closed.id) == 30000
        assert ledger.get_day_cash_drop_total_pt(1) == 30000

        # Total money in drawers + safe = 100,000 pt
        drawer_cash = ledger.get_session_balance_pt(new_s.id)
        safe_cash = ledger.get_day_cash_drop_total_pt(1)
        assert drawer_cash + safe_cash == 100000

    def test_cash_drop_with_sales_and_variance(self):
        """
        Session 1:
        - Opens with 50,000 pt
        - Sales of 30,000 pt (expected = 80,000 pt)
        - Cashier counts 85,000 pt (+5,000 pt surplus variance)
        - Drops 35,000 pt to safe
        - New session receives 50,000 pt
        - Outgoing session drawer balance is 0
        - Incoming session drawer balance is 50,000 pt
        - Business day report reflects safe drops and active cash
        """
        db = _fresh_db()
        svc = _make_svc(db)
        ledger = CashLedgerRepository(db=db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        # Add cash sale of 30,000 pt (order_id=None or valid order)
        ledger.append(CashLedgerEntry(
            id=None,
            day_id=1,
            session_id=s.id,
            entry_type=LedgerEntryType.SALE_CASH,
            amount_pt=30000,
            order_id=None,
            actor_id=2,
        ))
        db.commit()

        assert ledger.get_session_balance_pt(s.id) == 80000

        closed, new_s = svc.do_handover(
            from_session_id=s.id,
            to_user_id=3,
            station=Station.ALL,
            to_user_counted_pt=85000,
            cash_drop_pt=35000,
            variance_reason="زيادة نقدية معتمدة",
        )
        db.commit()

        assert closed.counted_cash_pt == 85000
        assert closed.variance_pt == 5000
        assert ledger.get_session_balance_pt(closed.id) == 0

        assert new_s.opening_float_pt == 50000
        assert ledger.get_session_balance_pt(new_s.id) == 50000

        # Reports
        day_svc = BusinessDayService(
            session_repo=CashierSessionRepository(db=db),
            ledger_repo=ledger,
        )
        x_rep = day_svc.generate_x_report(day_id=1)
        assert x_rep.total_cash_drops_pt == 35000
        assert x_rep.total_cash_drops_egp == 350.0
        assert x_rep.total_expected_cash_pt == 50000

    def test_cash_drop_equal_to_counted_cash(self):
        """Edge case: Entire counted cash is dropped to the safe."""
        db = _fresh_db()
        svc = _make_svc(db)
        ledger = CashLedgerRepository(db=db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=40000)
        db.commit()

        closed, new_s = svc.do_handover(
            from_session_id=s.id,
            to_user_id=3,
            station=Station.ALL,
            to_user_counted_pt=40000,
            cash_drop_pt=40000,  # all to safe
        )
        db.commit()

        assert new_s.opening_float_pt == 0
        assert ledger.get_session_balance_pt(new_s.id) == 0
        assert ledger.get_session_balance_pt(closed.id) == 0
        assert ledger.get_cash_drop_total_pt(closed.id) == 40000

    def test_handover_atomic_rollback_on_failure(self):
        """If a failure occurs during handover, all writes are rolled back."""
        db = _fresh_db()
        session_repo = CashierSessionRepository(db=db)
        ledger = CashLedgerRepository(db=db)
        svc = CashierSessionService(
            session_repo=session_repo,
            ledger_repo=ledger,
            auth_service=None,
        )

        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()

        # Simulate a crash right when set_handover_link is called
        original_set_link = session_repo.set_handover_link

        def _exploding_link(*args, **kwargs):
            raise RuntimeError("Database connection lost during link")

        session_repo.set_handover_link = _exploding_link

        with pytest.raises(RuntimeError, match="Database connection lost"):
            svc.do_handover(
                from_session_id=s.id,
                to_user_id=3,
                station=Station.ALL,
                to_user_counted_pt=50000,
                cash_drop_pt=10000,
            )

        # Restore
        session_repo.set_handover_link = original_set_link

        # Outgoing session MUST still be open and untouched
        refreshed = session_repo.get_by_id(s.id)
        assert refreshed.is_open
        assert refreshed.handover_to_session is None

        # Ledger entries MUST be rolled back: only original OPENING_FLOAT
        entries = ledger.get_entries_for_session(s.id)
        assert len(entries) == 1
        assert entries[0].entry_type == LedgerEntryType.OPENING_FLOAT
        assert ledger.get_session_balance_pt(s.id) == 50000
