"""
Regression tests — H05: session action authorization.

Root causes:
  1. _dispatch_session "close" action: no ownership check — cashier 2 could
     close cashier 1's session by supplying any session_id.
  2. _dispatch_session "open" action: user_id taken from payload, so a
     cashier could open a session for a different user.
  3. _dispatch_session "get_balance" action: no blind-count protection —
     a cashier could read their own open session's expected cash before
     entering the counted amount (revealing the target they should hit).

Fixes verified here:
  - Cashier 2 tries to close cashier 1's open session → rejected, session unchanged
  - Cashier reads own open session balance → rejected (blind count protection)
  - Manager can close another cashier's session (cross-drawer access preserved)
  - Manager can read any session balance (cross-drawer access preserved)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.user import User, UserRole
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
        "VALUES "
        "(1,'manager1','مدير 1','manager','h1',1),"
        "(2,'cashier1','كاشير 1','cashier','h2',1),"
        "(3,'cashier2','كاشير 2','cashier','h3',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.commit()
    return db


def _make_bridge(db: DatabaseConnection, current_user: User):
    """Build a minimal POSBridge with real session controller and given actor."""
    from broast_pos.infrastructure.web_bridge.bridge import POSBridge

    session_repo = CashierSessionRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    session_svc = CashierSessionService(session_repo=session_repo, ledger_repo=ledger_repo)
    day_svc = BusinessDayService(
        financial_service=None,
        session_repo=session_repo,
        ledger_repo=ledger_repo,
    )
    bridge = POSBridge.__new__(POSBridge)
    bridge._session_ctrl = SessionController(
        session_service=session_svc,
        business_day_service=day_svc,
    )
    bridge._session_svc = session_svc
    bridge._financial = None
    bridge._current_user = current_user
    return bridge


def _cashier(uid: int, name: str) -> User:
    return User(id=uid, username=name, display_name=name, role=UserRole.CASHIER, pin_hash="", is_active=True)


def _manager(uid: int) -> User:
    return User(id=uid, username="mgr", display_name="مدير", role=UserRole.MANAGER, pin_hash="", is_active=True)


def _open_cashier1_session(bridge_as_cashier1) -> int:
    resp = json.loads(bridge_as_cashier1._dispatch_session("open", {
        "day_id": 1, "station": "ALL", "opening_float_egp": 100.0,
    }))
    assert resp["success"], resp
    return resp["data"]["id"]


class TestH05SessionAuthz:

    def test_cashier2_cannot_close_cashier1_session(self):
        """Cashier 2 must be rejected when trying to close cashier 1's session."""
        db = _fresh_db()
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_cashier1_session(bridge_cas1)

        # Now act as cashier 2 against cashier 1's session
        bridge_cas2 = _make_bridge(db, _cashier(3, "cashier2"))
        resp = json.loads(bridge_cas2._dispatch_session("close", {
            "session_id": session_id,
            "counted_cash_egp": 100.0,
        }))
        assert resp["success"] is False, "Cashier 2 must not close cashier 1's session"

        # Verify session is still open (no state change)
        session_repo = CashierSessionRepository(db=db)
        session = session_repo.get_by_id(session_id)
        assert session is not None
        assert session.is_open is True, "Session must remain open after unauthorized close attempt"

    def test_cashier_cannot_read_own_open_session_balance(self):
        """Cashier must not see expected cash of their own open session (blind count)."""
        db = _fresh_db()
        bridge = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_cashier1_session(bridge)

        resp = json.loads(bridge._dispatch_session("get_balance", {
            "session_id": session_id,
        }))
        assert resp["success"] is False, "Cashier must not read own open session balance"
        assert "جرد" in resp.get("error", "") or "رصيد" in resp.get("error", ""), \
            f"Unexpected error message: {resp.get('error')}"

    def test_manager_can_close_any_session(self):
        """Manager retains cross-drawer access to close any session."""
        db = _fresh_db()
        bridge_cas = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_cashier1_session(bridge_cas)

        bridge_mgr = _make_bridge(db, _manager(1))
        resp = json.loads(bridge_mgr._dispatch_session("close", {
            "session_id": session_id,
            "counted_cash_egp": 100.0,
        }))
        assert resp["success"] is True, f"Manager must be able to close any session: {resp}"

    def test_manager_can_read_any_session_balance(self):
        """Manager can see expected cash of any open session."""
        db = _fresh_db()
        bridge_cas = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_cashier1_session(bridge_cas)

        bridge_mgr = _make_bridge(db, _manager(1))
        resp = json.loads(bridge_mgr._dispatch_session("get_balance", {
            "session_id": session_id,
        }))
        assert resp["success"] is True, f"Manager must read balance of any session: {resp}"
