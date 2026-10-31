"""
Tests for v2 Phase 2 — CashierSessionService + Station Routing.

Covers:
  FR-SES-1  open_session: valid, negative float rejected, duplicate station rejected
  FR-SES-2  station conflict: ALL+COUNTER, ALL+DELIVERY, COUNTER+ALL
  FR-SES-6  close_session: variance within threshold, variance above threshold
  FR-SES-7  do_handover: HANDOVER_OUT + HANDOVER_IN + correct opening float
  FR-SES-3  OrderService station routing: COUNTER→delivery rejected,
            DELIVERY→takeaway rejected, ALL→anything allowed,
            no-session → graceful skip (legacy mode)
  Ledger    OPENING_FLOAT created on open, ADJUSTMENT on variance, balance correct
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.core.models.cashier_session import (
    CashierSession, CashLedgerEntry, LedgerEntryType, Station
)
from broast_pos.core.models.order import Order, OrderItem, OrderType, OrderStatus
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.core.services.cashier_session_service import CashierSessionService


# ---------------------------------------------------------------------------
# Singleton isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


# ---------------------------------------------------------------------------
# Shared in-memory DB helpers
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


def _make_svc(db: DatabaseConnection) -> CashierSessionService:
    return CashierSessionService(
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
        auth_service=None,
    )


# ===========================================================================
# Part A: open_session (FR-SES-1)
# ===========================================================================

class TestOpenSession:

    def test_open_creates_session(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=50000)
        db.commit()
        assert s.id is not None
        assert s.is_open
        assert s.station == Station.ALL
        assert s.opening_float_pt == 50000

    def test_opening_float_creates_ledger_entry(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=30000)
        db.commit()
        ledger = CashLedgerRepository(db=db)
        balance = ledger.get_session_balance_pt(s.id)
        assert balance == 30000

    def test_zero_float_no_ledger_entry(self):
        """Zero opening float: no ledger entry, balance = 0."""
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0)
        db.commit()
        ledger = CashLedgerRepository(db=db)
        assert ledger.get_session_balance_pt(s.id) == 0

    def test_negative_float_rejected(self):
        db = _fresh_db()
        svc = _make_svc(db)
        with pytest.raises(ValueError, match="سالب"):
            svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=-100)

    def test_open_counter_and_delivery_together(self):
        """COUNTER + DELIVERY can coexist — no conflict."""
        db = _fresh_db()
        svc = _make_svc(db)
        s1 = svc.open_session(day_id=1, user_id=2, station=Station.COUNTER, opening_float_pt=0)
        db.commit()
        s2 = svc.open_session(day_id=1, user_id=1, station=Station.DELIVERY, opening_float_pt=0)
        db.commit()
        assert s1.id != s2.id
        sessions = svc.get_active_sessions(day_id=1)
        assert len(sessions) == 2


# ===========================================================================
# Part B: station conflict (FR-SES-2)
# ===========================================================================

class TestStationConflict:

    def test_all_conflicts_with_counter(self):
        db = _fresh_db()
        svc = _make_svc(db)
        svc.open_session(day_id=1, user_id=2, station=Station.COUNTER, opening_float_pt=0)
        db.commit()
        with pytest.raises(ValueError):
            svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=0)

    def test_all_conflicts_with_delivery(self):
        db = _fresh_db()
        svc = _make_svc(db)
        svc.open_session(day_id=1, user_id=2, station=Station.DELIVERY, opening_float_pt=0)
        db.commit()
        with pytest.raises(ValueError):
            svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=0)

    def test_counter_conflicts_with_all(self):
        db = _fresh_db()
        svc = _make_svc(db)
        svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=0)
        db.commit()
        with pytest.raises(ValueError):
            svc.open_session(day_id=1, user_id=2, station=Station.COUNTER, opening_float_pt=0)

    def test_duplicate_station_rejected(self):
        db = _fresh_db()
        svc = _make_svc(db)
        svc.open_session(day_id=1, user_id=1, station=Station.COUNTER, opening_float_pt=0)
        db.commit()
        with pytest.raises(ValueError, match="مفتوحة"):
            svc.open_session(day_id=1, user_id=2, station=Station.COUNTER, opening_float_pt=0)

    def test_closed_session_does_not_block_new_one(self):
        """A closed ALL session should not block a new COUNTER session."""
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=0)
        db.commit()
        svc.close_session(session_id=s.id, counted_cash_pt=0, actor_id=1)
        db.commit()
        # Now open COUNTER — should succeed
        s2 = svc.open_session(day_id=1, user_id=2, station=Station.COUNTER, opening_float_pt=0)
        db.commit()
        assert s2.id is not None


# ===========================================================================
# Part C: close_session (FR-SES-6)
# ===========================================================================

class TestCloseSession:

    def _open_with_float(self, db, float_pt=100000) -> CashierSession:
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=float_pt)
        db.commit()
        return s

    def test_close_exact_count_no_variance(self):
        db = _fresh_db()
        s = self._open_with_float(db, float_pt=100000)
        svc = _make_svc(db)
        closed = svc.close_session(session_id=s.id, counted_cash_pt=100000, actor_id=1)
        db.commit()
        assert not closed.is_open
        assert closed.expected_cash_pt == 100000
        assert closed.counted_cash_pt == 100000
        assert closed.variance_pt == 0

    def test_close_with_small_variance_no_pin_needed(self):
        """Variance within threshold requires no manager PIN."""
        db = _fresh_db()
        s = self._open_with_float(db, float_pt=100000)
        svc = _make_svc(db)
        # variance = 100100 - 100000 = +100 pt = EGP 1 (< default threshold EGP 20)
        closed = svc.close_session(session_id=s.id, counted_cash_pt=100100, actor_id=1)
        db.commit()
        assert closed.variance_pt == 100

    def test_adjustment_entry_created_on_variance(self):
        db = _fresh_db()
        s = self._open_with_float(db, float_pt=100000)
        svc = _make_svc(db)
        svc.close_session(session_id=s.id, counted_cash_pt=99500, actor_id=1)
        db.commit()
        ledger = CashLedgerRepository(db=db)
        entries = ledger.get_entries_for_session(s.id)
        types = [e.entry_type for e in entries]
        assert LedgerEntryType.ADJUSTMENT in types
        adj = next(e for e in entries if e.entry_type == LedgerEntryType.ADJUSTMENT)
        assert adj.amount_pt == -500  # counted 99500 - expected 100000 = -500

    def test_large_variance_without_reason_rejected(self):
        """Variance above threshold with no reason → ValueError."""
        db = _fresh_db()
        s = self._open_with_float(db, float_pt=100000)
        svc = _make_svc(db)
        with pytest.raises(ValueError, match="يتجاوز الحد"):
            svc.close_session(
                session_id=s.id,
                counted_cash_pt=90000,   # -10000 pt = EGP 100 variance
                actor_id=1,
                variance_threshold_pt=2000,
            )

    def test_large_variance_with_reason_accepted(self):
        """Variance above threshold with reason and no auth → accepted."""
        db = _fresh_db()
        s = self._open_with_float(db, float_pt=100000)
        svc = _make_svc(db)
        closed = svc.close_session(
            session_id=s.id,
            counted_cash_pt=90000,
            actor_id=1,
            variance_threshold_pt=2000,
            variance_reason="خسارة بسبب عجز في الكاشير",
        )
        db.commit()
        assert closed.variance_pt == -10000

    def test_close_already_closed_raises(self):
        db = _fresh_db()
        s = self._open_with_float(db, float_pt=0)
        svc = _make_svc(db)
        svc.close_session(session_id=s.id, counted_cash_pt=0, actor_id=1)
        db.commit()
        with pytest.raises(ValueError, match="مغلقة"):
            svc.close_session(session_id=s.id, counted_cash_pt=0, actor_id=1)

    def test_close_nonexistent_raises(self):
        db = _fresh_db()
        svc = _make_svc(db)
        with pytest.raises(ValueError):
            svc.close_session(session_id=9999, counted_cash_pt=0, actor_id=1)


# ===========================================================================
# Part D: Handover (FR-SES-6 + FR-SES-7)
# ===========================================================================

class TestHandover:

    def test_handover_closes_from_opens_to(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s_from = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=100000)
        db.commit()
        closed, new_s = svc.do_handover(
            from_session_id=s_from.id,
            to_user_id=2,
            station=Station.ALL,
            to_user_counted_pt=100000,
        )
        db.commit()
        assert not closed.is_open
        assert new_s.is_open
        assert new_s.user_id == 2

    def test_handover_out_entry_in_old_session(self):
        db = _fresh_db()
        svc = _make_svc(db)
        ledger = CashLedgerRepository(db=db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=50000)
        db.commit()
        svc.do_handover(
            from_session_id=s.id,
            to_user_id=2,
            station=Station.ALL,
            to_user_counted_pt=50000,
        )
        db.commit()
        entries = ledger.get_entries_for_session(s.id)
        types = [e.entry_type for e in entries]
        assert LedgerEntryType.HANDOVER_OUT in types

    def test_handover_in_entry_in_new_session(self):
        db = _fresh_db()
        svc = _make_svc(db)
        ledger = CashLedgerRepository(db=db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=50000)
        db.commit()
        _, new_s = svc.do_handover(
            from_session_id=s.id,
            to_user_id=2,
            station=Station.ALL,
            to_user_counted_pt=50000,
        )
        db.commit()
        entries = ledger.get_entries_for_session(new_s.id)
        types = [e.entry_type for e in entries]
        assert LedgerEntryType.HANDOVER_IN in types

    def test_fr_ses_7_opening_float_equals_counted_minus_drop(self):
        """FR-SES-7: new session opening = counted − cash_drop."""
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=100000)
        db.commit()
        _, new_s = svc.do_handover(
            from_session_id=s.id,
            to_user_id=2,
            station=Station.ALL,
            to_user_counted_pt=100000,
            cash_drop_pt=20000,        # EGP 200 to safe
        )
        db.commit()
        # new opening float = 100000 - 20000 = 80000
        assert new_s.opening_float_pt == 80000
        ledger = CashLedgerRepository(db=db)
        assert ledger.get_session_balance_pt(new_s.id) == 80000

    def test_handover_variance_large_without_reason_rejected(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=100000)
        db.commit()
        with pytest.raises(ValueError, match="يتجاوز الحد"):
            svc.do_handover(
                from_session_id=s.id,
                to_user_id=2,
                station=Station.ALL,
                to_user_counted_pt=50000,   # -50000 pt = EGP 500 variance
                variance_threshold_pt=2000,
            )


# ===========================================================================
# Part E: OrderService station routing (FR-SES-3)
# ===========================================================================

class TestStationRouting:
    """Unit-test _enforce_station_routing without a real DB."""

    def _make_order_svc(self, sessions: list[CashierSession]):
        """Build a minimal OrderService with mocked session service."""
        from broast_pos.core.services.order_service import OrderService
        mock_session_svc = MagicMock()
        mock_session_svc.get_active_sessions.return_value = sessions

        # Minimal financial_service mock
        mock_shift = MagicMock()
        mock_shift.id = 1
        mock_fin = MagicMock()
        mock_fin.ensure_shift_active.return_value = mock_shift
        mock_fin.get_next_invoice_number.return_value = 1

        svc = OrderService(
            order_repo=MagicMock(),
            audit_service=MagicMock(),
            financial_service=mock_fin,
            session_service=mock_session_svc,
        )
        svc._orders.save.side_effect = lambda o: o
        svc._status_history = MagicMock()
        return svc

    def _session(self, user_id: int, station: Station) -> CashierSession:
        return CashierSession(
            id=1, day_id=1, user_id=user_id, station=station,
            is_open=True, opening_float_pt=0,
        )

    def _delivery_order(self) -> Order:
        item = OrderItem(product_id=1, product_name="X", unit_price=100, quantity=1)
        return Order(
            id=None, invoice_no=None, order_type=OrderType.DELIVERY,
            status=OrderStatus.NEW, items=[item],
            subtotal=100.0, total=100.0,
            customer_phone="01011111111",
            customer_address="شارع النيل",
        )

    def _takeaway_order(self) -> Order:
        item = OrderItem(product_id=1, product_name="X", unit_price=50, quantity=1)
        return Order(
            id=None, invoice_no=None, order_type=OrderType.TAKEAWAY,
            status=OrderStatus.NEW, items=[item],
            subtotal=50.0, total=50.0,
        )

    def test_counter_cannot_create_delivery(self):
        svc = self._make_order_svc([self._session(user_id=2, station=Station.COUNTER)])
        with pytest.raises(ValueError, match="الكاونتر"):
            svc.create_order(self._delivery_order(), cashier_id=2, cashier_name="Cashier")

    def test_delivery_cannot_create_takeaway(self):
        svc = self._make_order_svc([self._session(user_id=2, station=Station.DELIVERY)])
        with pytest.raises(ValueError, match="الديليفري"):
            svc.create_order(self._takeaway_order(), cashier_id=2, cashier_name="Cashier")

    def test_all_can_create_delivery(self):
        svc = self._make_order_svc([self._session(user_id=2, station=Station.ALL)])
        # Should not raise — save is mocked to return the order
        result = svc.create_order(self._delivery_order(), cashier_id=2, cashier_name="Cashier")
        assert result is not None

    def test_all_can_create_takeaway(self):
        svc = self._make_order_svc([self._session(user_id=2, station=Station.ALL)])
        result = svc.create_order(self._takeaway_order(), cashier_id=2, cashier_name="Cashier")
        assert result is not None

    def test_no_session_skips_routing_gracefully(self):
        """If cashier has no open session → routing skipped, order proceeds."""
        svc = self._make_order_svc([])   # no sessions
        # Should not raise for delivery or takeaway
        result = svc.create_order(self._delivery_order(), cashier_id=2, cashier_name="Cashier")
        assert result is not None

    def test_counter_can_create_takeaway(self):
        svc = self._make_order_svc([self._session(user_id=2, station=Station.COUNTER)])
        result = svc.create_order(self._takeaway_order(), cashier_id=2, cashier_name="Cashier")
        assert result is not None
