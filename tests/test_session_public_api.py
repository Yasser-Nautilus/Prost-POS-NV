"""
Regression tests for private-attribute coupling fixes.

Covers:
  - CashierSessionService.get_all_sessions_for_day() — new public method that
    replaces SessionController's direct access to self._svc._sessions
  - SessionController.get_all_sessions() — no longer accesses private _sessions
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.cashier_session import Station
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
        "VALUES (1,'mgr','Manager','manager','h1',1)"
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


class TestGetAllSessionsForDay:
    """CashierSessionService.get_all_sessions_for_day() — public wrapper."""

    def test_returns_empty_when_no_sessions(self):
        db = _fresh_db()
        svc = _make_svc(db)
        result = svc.get_all_sessions_for_day(day_id=1)
        assert result == []

    def test_returns_open_session(self):
        db = _fresh_db()
        svc = _make_svc(db)
        svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=10000)
        db.commit()
        result = svc.get_all_sessions_for_day(day_id=1)
        assert len(result) == 1
        assert result[0].is_open

    def test_returns_closed_session(self):
        db = _fresh_db()
        svc = _make_svc(db)
        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=10000)
        db.commit()
        svc.close_session(
            session_id=s.id,
            counted_cash_pt=10000,
            actor_id=1,
            manager_pin=None,
        )
        db.commit()
        result = svc.get_all_sessions_for_day(day_id=1)
        assert len(result) == 1
        assert not result[0].is_open

    def test_returns_both_open_and_closed_sessions(self):
        db = _fresh_db()
        # Add a second user (cashier)
        db.execute(
            "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
            "VALUES (2,'cas','Cashier','cashier','h2',1)"
        )
        db.commit()
        svc = _make_svc(db)

        s1 = svc.open_session(day_id=1, user_id=1, station=Station.COUNTER, opening_float_pt=5000)
        db.commit()
        svc.close_session(
            session_id=s1.id,
            counted_cash_pt=5000,
            actor_id=1,
            manager_pin=None,
        )
        db.commit()
        svc.open_session(day_id=1, user_id=2, station=Station.DELIVERY, opening_float_pt=3000)
        db.commit()

        all_sessions = svc.get_all_sessions_for_day(day_id=1)
        assert len(all_sessions) == 2
        open_count = sum(1 for s in all_sessions if s.is_open)
        closed_count = sum(1 for s in all_sessions if not s.is_open)
        assert open_count == 1
        assert closed_count == 1

    def test_different_day_id_isolated(self):
        db = _fresh_db()
        # Insert a second shift for a different day
        db.execute(
            "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
            "VALUES (2, 1, datetime('now'), 1, 0, date('now','+1 day','localtime'))"
        )
        db.commit()
        svc = _make_svc(db)
        svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=1000)
        db.commit()

        # Day 2 has no sessions
        result_day2 = svc.get_all_sessions_for_day(day_id=2)
        assert result_day2 == []

        # Day 1 has one session
        result_day1 = svc.get_all_sessions_for_day(day_id=1)
        assert len(result_day1) == 1


class TestCloseSessionRepoGuard:
    """CashierSessionRepository.close_session raises on no-op update."""

    def test_raises_when_session_already_closed(self):
        db = _fresh_db()
        from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
        repo = CashierSessionRepository(db=db)
        svc = _make_svc(db)

        s = svc.open_session(day_id=1, user_id=1, station=Station.ALL, opening_float_pt=5000)
        db.commit()
        repo.close_session(
            session_id=s.id,
            counted_cash_pt=5000,
            expected_cash_pt=5000,
            variance_pt=0,
        )
        db.commit()

        with pytest.raises(ValueError, match="مغلقة"):
            repo.close_session(
                session_id=s.id,
                counted_cash_pt=5000,
                expected_cash_pt=5000,
                variance_pt=0,
            )

    def test_raises_when_session_does_not_exist(self):
        db = _fresh_db()
        from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
        repo = CashierSessionRepository(db=db)

        with pytest.raises(ValueError, match="غير موجودة"):
            repo.close_session(
                session_id=9999,
                counted_cash_pt=0,
                expected_cash_pt=0,
                variance_pt=0,
            )


class TestSessionControllerUsesPublicAPI:
    """SessionController.get_all_sessions() must not access private _sessions."""

    def test_get_all_sessions_does_not_access_private_attribute(self):
        """
        Verify SessionController.get_all_sessions() calls the public
        CashierSessionService.get_all_sessions_for_day() instead of
        bypassing it via _sessions.

        Strategy: mock the service so _sessions raises AttributeError
        if accessed, while get_all_sessions_for_day() works normally.
        """

        mock_svc = MagicMock(spec=CashierSessionService)
        mock_svc.get_all_sessions_for_day.return_value = []

        # Make private attribute access raise to catch regressions
        type(mock_svc)._sessions = property(
            lambda self: (_ for _ in ()).throw(
                AttributeError("Private _sessions accessed — use get_all_sessions_for_day()")
            )
        )

        mock_day = MagicMock()
        ctrl = SessionController(session_service=mock_svc, business_day_service=mock_day, auth_service=None)
        result = ctrl.get_all_sessions(day_id=1)

        assert result == []
        mock_svc.get_all_sessions_for_day.assert_called_once_with(1)
