"""
Tests for v2 Phase 5 — SessionController + Bridge dispatch.

Covers:
  SessionController.open_session()     → correct dict, EGP→pt conversion
  SessionController.close_session()    → variance fields in dict
  SessionController.do_handover()      → returns {closed, new} dict
  SessionController.get_active_sessions() → list of dicts
  SessionController.get_session_balance() → pt + egp
  SessionController.generate_x_report()  → totals + sessions list
  SessionController.close_business_day() → Z-Report dict with 'type': 'Z'
  Station validation error             → Arabic message, not stack trace
  _dispatch_session in bridge          → routes correctly, returns JSON success
  _dispatch_session no ctrl            → returns Arabic error (not crash)
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.core.models.cashier_session import (
    CashierSession, CashLedgerEntry, LedgerEntryType, Station,
)
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.features.financial.session_controller import SessionController


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
    return SessionController(session_service=svc, business_day_service=day_svc)


# ===========================================================================
# Part A: SessionController unit tests
# ===========================================================================

class TestSessionController:

    def test_open_session_returns_dict(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        result = ctrl.open_session(
            day_id=1, user_id=2, station="ALL",
            opening_float_egp=500.0, actor_id=1,
        )
        db.fetch_one("SELECT 1")  # ensure commit happened via repo
        assert isinstance(result, dict)
        assert result["station"] == "ALL"
        assert result["is_open"] is True
        assert result["opening_float_egp"] == pytest.approx(500.0)
        assert result["opening_float_pt"] == 50000

    def test_open_session_egp_to_pt_conversion(self):
        """EGP amounts are converted to piasters correctly."""
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        result = ctrl.open_session(
            day_id=1, user_id=2, station="COUNTER",
            opening_float_egp=123.45,
        )
        assert result["opening_float_pt"] == 12345
        assert result["opening_float_egp"] == pytest.approx(123.45)

    def test_open_session_invalid_station_raises(self):
        """Unknown station → ValueError with Arabic message."""
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        with pytest.raises(ValueError, match="محطة غير صحيحة"):
            ctrl.open_session(day_id=1, user_id=2, station="KITCHEN", opening_float_egp=0)

    def test_close_session_returns_variance_fields(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        opened = ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=500.0)
        closed = ctrl.close_session(
            session_id=opened["id"],
            counted_cash_egp=490.0,   # EGP 10 short
            actor_id=1,
        )
        assert not closed["is_open"]
        # variance = 49000 - 50000 = -1000 pt = -10.00 EGP
        assert closed["variance_pt"] == -1000
        assert closed["variance_egp"] == pytest.approx(-10.0)

    def test_do_handover_returns_closed_and_new(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        s = ctrl.open_session(day_id=1, user_id=1, station="ALL", opening_float_egp=200.0)
        result = ctrl.do_handover(
            from_session_id=s["id"],
            to_user_id=2,
            station="ALL",
            counted_cash_egp=200.0,
            cash_drop_egp=50.0,
        )
        assert "closed" in result
        assert "new" in result
        assert not result["closed"]["is_open"]
        assert result["new"]["is_open"]
        # new opening float = 200 - 50 = 150 EGP
        assert result["new"]["opening_float_egp"] == pytest.approx(150.0)

    def test_get_active_sessions_empty(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        result = ctrl.get_active_sessions(day_id=1)
        assert result == []

    def test_get_active_sessions_list(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        ctrl.open_session(day_id=1, user_id=1, station="COUNTER", opening_float_egp=0)
        ctrl.open_session(day_id=1, user_id=2, station="DELIVERY", opening_float_egp=0)
        result = ctrl.get_active_sessions(day_id=1)
        assert len(result) == 2
        stations = {s["station"] for s in result}
        assert stations == {"COUNTER", "DELIVERY"}

    def test_get_session_balance_after_open(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        s = ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=300.0)
        bal = ctrl.get_session_balance(s["id"])
        assert bal["balance_pt"] == 30000
        assert bal["balance_egp"] == pytest.approx(300.0)
        assert bal["is_open"] is True

    def test_x_report_totals_structure(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=100.0)
        report = ctrl.generate_x_report(day_id=1)
        assert report["type"] == "X"
        assert report["day_id"] == 1
        assert "sessions" in report
        assert "totals" in report
        assert "expected_cash_egp" in report["totals"]
        assert report["totals"]["expected_cash_egp"] == pytest.approx(100.0)

    def test_x_report_breakdown_included(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        s = ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=50.0)
        report = ctrl.generate_x_report(day_id=1)
        session_snap = report["sessions"][0]
        assert "breakdown" in session_snap
        assert "OPENING_FLOAT" in session_snap["breakdown"]
        snap_float = session_snap["breakdown"]["OPENING_FLOAT"]
        assert snap_float["pt"] == 5000
        assert snap_float["egp"] == pytest.approx(50.0)

    def test_close_day_returns_z_report(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        s = ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=0)
        ctrl.close_session(session_id=s["id"], counted_cash_egp=0, actor_id=1)
        z = ctrl.close_business_day(day_id=1)
        assert z["type"] == "Z"
        assert "day_closed_at" in z
        assert "total_variance_pt" in z
        assert "total_variance_egp" in z

    def test_close_day_blocked_when_session_open(self):
        db = _fresh_db()
        ctrl = _make_ctrl(db)
        ctrl.open_session(day_id=1, user_id=2, station="ALL", opening_float_egp=0)
        with pytest.raises(ValueError, match="وردية مفتوحة"):
            ctrl.close_business_day(day_id=1)


# ===========================================================================
# Part B: Bridge _dispatch_session routing
# ===========================================================================

class TestBridgeSessionDispatch:
    """Test _dispatch_session without spinning up Qt."""

    def _make_bridge_with_ctrl(self, db: DatabaseConnection):
        """Build a minimal POSBridge with real session controller."""
        from broast_pos.infrastructure.web_bridge.bridge import POSBridge

        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)
        session_svc = CashierSessionService(session_repo=session_repo, ledger_repo=ledger_repo)
        day_svc = BusinessDayService(
            financial_service=None,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
        )
        bridge = POSBridge.__new__(POSBridge)  # skip Qt __init__
        bridge._session_ctrl = SessionController(
            session_service=session_svc,
            business_day_service=day_svc,
        )
        bridge._financial = None
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.display_name = "Manager"
        bridge._current_user = mock_user
        return bridge

    def test_dispatch_open_returns_success(self):
        db = _fresh_db()
        bridge = self._make_bridge_with_ctrl(db)
        resp = json.loads(bridge._dispatch_session("open", {
            "day_id": 1, "user_id": 2, "station": "ALL", "opening_float_egp": 100.0,
        }))
        assert resp["success"] is True
        assert resp["data"]["station"] == "ALL"

    def test_dispatch_get_active_returns_list(self):
        db = _fresh_db()
        bridge = self._make_bridge_with_ctrl(db)
        bridge._dispatch_session("open", {
            "day_id": 1, "user_id": 2, "station": "COUNTER", "opening_float_egp": 0,
        })
        resp = json.loads(bridge._dispatch_session("get_active", {"day_id": 1}))
        assert resp["success"] is True
        assert len(resp["data"]) == 1

    def test_dispatch_invalid_station_returns_arabic_error(self):
        db = _fresh_db()
        bridge = self._make_bridge_with_ctrl(db)
        resp = json.loads(bridge._dispatch_session("open", {
            "day_id": 1, "user_id": 2, "station": "KITCHEN", "opening_float_egp": 0,
        }))
        assert resp["success"] is False
        assert "محطة" in resp["error"]

    def test_dispatch_unknown_action_returns_arabic_error(self):
        db = _fresh_db()
        bridge = self._make_bridge_with_ctrl(db)
        resp = json.loads(bridge._dispatch_session("explode", {}))
        assert resp["success"] is False
        assert "غير معروف" in resp["error"]

    def test_dispatch_no_ctrl_returns_arabic_error(self):
        """If session_ctrl is None, dispatch returns Arabic message without crashing."""
        from broast_pos.infrastructure.web_bridge.bridge import POSBridge
        bridge = POSBridge.__new__(POSBridge)
        bridge._session_ctrl = None
        bridge._financial = None
        resp = json.loads(bridge._dispatch_session("open", {}))
        assert resp["success"] is False
        assert "غير مفعل" in resp["error"]

    def test_dispatch_x_report_structure(self):
        db = _fresh_db()
        bridge = self._make_bridge_with_ctrl(db)
        bridge._dispatch_session("open", {
            "day_id": 1, "user_id": 2, "station": "ALL", "opening_float_egp": 250.0,
        })
        resp = json.loads(bridge._dispatch_session("x_report", {"day_id": 1}))
        assert resp["success"] is True
        assert resp["data"]["type"] == "X"
        assert resp["data"]["totals"]["expected_cash_egp"] == pytest.approx(250.0)

    def test_dispatch_close_then_z_report(self):
        db = _fresh_db()
        bridge = self._make_bridge_with_ctrl(db)
        # open a session
        open_resp = json.loads(bridge._dispatch_session("open", {
            "day_id": 1, "user_id": 2, "station": "ALL", "opening_float_egp": 0,
        }))
        session_id = open_resp["data"]["id"]
        # close it
        bridge._dispatch_session("close", {
            "session_id": session_id, "counted_cash_egp": 0,
        })
        # close day → Z-Report
        z_resp = json.loads(bridge._dispatch_session("close_day", {"day_id": 1}))
        assert z_resp["success"] is True
        assert z_resp["data"]["type"] == "Z"
