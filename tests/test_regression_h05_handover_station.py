"""
Regression test — H05 follow-up: handover station must come from the
outgoing session, never from the client.

Root cause:
  bridge.py's "handover" action read the recipient's new session station
  from payload.get("station", "ALL") — a client-supplied value, defaulting
  to "ALL" regardless of what station the outgoing session actually ran.
  A handover changes who is responsible for a drawer, never which drawer
  it is, so the new session must inherit the outgoing session's station.

Fix verified here:
  - A handover of a DELIVERY-station session produces a new session still
    on DELIVERY, even when the caller supplies a different (or no)
    station in the payload.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.cashier_session import Station
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
from broast_pos.infrastructure.web_bridge.bridge import POSBridge


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
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active, cashier_slot) "
        "VALUES (1,'cashier1','كاشير 1','cashier','h1',1,1),"
        "(2,'cashier2','كاشير 2','cashier','h2',1,2)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.commit()
    return db


def _make_bridge(db: DatabaseConnection, current_user: User) -> POSBridge:
    session_repo = CashierSessionRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    session_svc = CashierSessionService(session_repo=session_repo, ledger_repo=ledger_repo)
    day_svc = BusinessDayService(
        financial_service=None, session_repo=session_repo, ledger_repo=ledger_repo,
    )
    bridge = POSBridge.__new__(POSBridge)
    bridge._session_ctrl = SessionController(
        session_service=session_svc, business_day_service=day_svc,
    )
    bridge._session_svc = session_svc
    bridge._financial = None
    auth = MagicMock()
    auth.refresh_current_user.return_value = current_user
    auth.get_user_by_id.return_value = current_user
    bridge._auth = auth
    bridge._current_user = current_user
    return bridge


def _cashier(uid: int) -> User:
    return User(
        id=uid, username=f"c{uid}", display_name=f"c{uid}", role=UserRole.CASHIER,
        pin_hash="", is_active=True, cashier_slot=uid,
    )


class TestH05HandoverInheritsOutgoingStation:

    def test_handover_keeps_delivery_station_despite_client_payload(self):
        db = _fresh_db()
        bridge = _make_bridge(db, _cashier(1))

        opened = json.loads(bridge.dispatch("session.open", json.dumps({
            "day_id": 1, "station": "DELIVERY", "opening_float_egp": 100.0,
        })))
        assert opened["success"], opened
        from_session_id = opened["data"]["id"]

        # Client tries to supply (or omit) a different station — must be ignored.
        resp = json.loads(bridge.dispatch("session.handover", json.dumps({
            "from_session_id": from_session_id,
            "to_user_id": 1,
            "station": "ALL",  # manipulated/incorrect client value
            "counted_cash_egp": 100.0,
        })))
        assert resp["success"] is True, resp
        assert resp["data"]["new"]["station"] == Station.DELIVERY.value, (
            "H05 regression: the recipient's new session must stay on the "
            "same station as the outgoing one, not whatever the client sent"
        )
