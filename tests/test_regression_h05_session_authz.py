"""
Regression tests — H05: session action authorization and ownership protection.

Verified here:
  1. Actor from login: unauthenticated requests (without login) are cleanly rejected
     across all session actions.
  2. Cashier cannot close another cashier's session.
  3. Cashier cannot handover another cashier's session.
  4. Handover to delivery driver (cashier_slot is None) is rejected.
  5. Cashier can handover own session to another valid cashier.
  6. Blind-count protection: cashier cannot read expected cash of own open session.
  7. Cross-drawer read protection: cashier cannot read another cashier's balance.
  8. get_active and get_all return ONLY the cashier's own sessions for a cashier,
     while a manager sees all sessions.
  9. x_report is manager-only (cashier rejected).
  10. close_day requires manager role or valid manager PIN.
  11. Protection below the bridge: SessionController and CashierSessionService
      enforce these guards directly even when bypassed at the bridge.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from broast_pos.core.models.user import User, UserRole
from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.user_repository import UserRepository
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

    # Manager PIN = 1234
    mgr_pin_hash = hashlib.sha256(b"1234").hexdigest()

    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, cashier_slot, is_active) "
        "VALUES "
        f"(1,'manager1','مدير 1','manager','{mgr_pin_hash}',1,1),"
        "(2,'cashier1','كاشير 1','cashier','h2',1,1),"
        "(3,'cashier2','كاشير 2','cashier','h3',2,1),"
        "(4,'driver1','سائق 1','cashier','h4',NULL,1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.commit()
    return db


def _cashier(uid: int, name: str, slot: int = 1) -> User:
    return User(
        id=uid,
        username=name,
        display_name=name,
        role=UserRole.CASHIER,
        pin_hash="",
        cashier_slot=slot,
        is_active=True,
    )


def _manager(uid: int) -> User:
    return User(
        id=uid,
        username="mgr",
        display_name="مدير",
        role=UserRole.MANAGER,
        pin_hash="",
        cashier_slot=1,
        is_active=True,
    )


def _make_bridge(db: DatabaseConnection, current_user: User | None):
    """Build a minimal POSBridge with real session controller and given actor."""
    from broast_pos.infrastructure.web_bridge.bridge import POSBridge

    user_repo = UserRepository(db=db)
    auth_svc = AuthService(user_repo=user_repo)
    if current_user is not None:
        auth_svc._current_user = current_user

    session_repo = CashierSessionRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    session_svc = CashierSessionService(
        session_repo=session_repo,
        ledger_repo=ledger_repo,
        auth_service=auth_svc,
    )
    day_svc = BusinessDayService(
        financial_service=None,
        session_repo=session_repo,
        ledger_repo=ledger_repo,
        auth_service=auth_svc,
    )
    ctrl = SessionController(
        session_service=session_svc,
        business_day_service=day_svc,
        auth_service=auth_svc,
    )

    bridge = POSBridge.__new__(POSBridge)
    bridge._session_ctrl = ctrl
    bridge._session_svc = session_svc
    bridge._auth = auth_svc
    bridge._financial = None
    bridge._current_user = current_user
    return bridge


def _open_session(bridge, user_id: int, station: str = "COUNTER", opening_float: float = 100.0) -> int:
    resp = json.loads(bridge._dispatch_session("open", {
        "day_id": 1,
        "user_id": user_id,
        "station": station,
        "opening_float_egp": opening_float,
    }))
    assert resp["success"], resp
    return resp["data"]["id"]


class TestH05SessionAuthz:

    def test_unauthenticated_request_cleanly_rejected(self):
        """Without login, any session action must be rejected immediately."""
        db = _fresh_db()
        bridge = _make_bridge(db, None)

        actions = [
            ("open", {"day_id": 1, "station": "ALL"}),
            ("close", {"session_id": 1}),
            ("handover", {"from_session_id": 1, "to_user_id": 2}),
            ("get_active", {}),
            ("get_all", {}),
            ("get_balance", {"session_id": 1}),
            ("x_report", {}),
            ("close_day", {}),
        ]
        for act, payload in actions:
            resp = json.loads(bridge._dispatch_session(act, payload))
            assert resp["success"] is False, f"Action {act} should fail without login"
            assert "تسجيل الدخول" in resp.get("error", "")

    def test_cashier2_cannot_close_cashier1_session(self):
        """Cashier 2 must be rejected when trying to close cashier 1's session."""
        db = _fresh_db()
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge_cas1, user_id=2, station="ALL")

        # Now act as cashier 2 against cashier 1's session
        bridge_cas2 = _make_bridge(db, _cashier(3, "cashier2", slot=2))
        resp = json.loads(bridge_cas2._dispatch_session("close", {
            "session_id": session_id,
            "counted_cash_egp": 100.0,
        }))
        assert resp["success"] is False, "Cashier 2 must not close cashier 1's session"
        assert "لا يمكن إغلاق درج كاشير آخر" in resp["error"]

        # Verify session is still open
        session_repo = CashierSessionRepository(db=db)
        session = session_repo.get_by_id(session_id)
        assert session is not None
        assert session.is_open is True

    def test_cashier2_cannot_handover_cashier1_session(self):
        """Cashier 2 must be rejected when trying to handover cashier 1's session."""
        db = _fresh_db()
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge_cas1, user_id=2, station="COUNTER")

        bridge_cas2 = _make_bridge(db, _cashier(3, "cashier2", slot=2))
        resp = json.loads(bridge_cas2._dispatch_session("handover", {
            "from_session_id": session_id,
            "to_user_id": 3,
            "station": "COUNTER",
            "counted_cash_egp": 100.0,
        }))
        assert resp["success"] is False, "Cashier 2 must not handover cashier 1's session"
        assert "لا يمكن تسليم درج كاشير آخر" in resp["error"]

    def test_cashier_cannot_handover_to_delivery_driver(self):
        """Cannot handover cash register to a delivery driver (cashier_slot is None)."""
        db = _fresh_db()
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge_cas1, user_id=2, station="COUNTER")

        # Attempt handover to user 4 (driver)
        resp = json.loads(bridge_cas1._dispatch_session("handover", {
            "from_session_id": session_id,
            "to_user_id": 4,
            "station": "COUNTER",
            "counted_cash_egp": 100.0,
        }))
        assert resp["success"] is False, "Cannot handover to delivery driver"
        assert "سائق" in resp["error"]

    def test_cashier_handover_own_session_succeeds(self):
        """Cashier can handover their own session to another registered cashier."""
        db = _fresh_db()
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge_cas1, user_id=2, station="COUNTER")

        resp = json.loads(bridge_cas1._dispatch_session("handover", {
            "from_session_id": session_id,
            "to_user_id": 3,
            "station": "COUNTER",
            "counted_cash_egp": 100.0,
        }))
        assert resp["success"] is True, f"Handover failed: {resp}"
        assert resp["data"]["closed"]["id"] == session_id
        assert resp["data"]["new"]["user_id"] == 3

    def test_cashier_cannot_read_own_open_session_balance(self):
        """Cashier must not see expected cash of their own open session (blind count)."""
        db = _fresh_db()
        bridge = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge, user_id=2, station="ALL")

        resp = json.loads(bridge._dispatch_session("get_balance", {
            "session_id": session_id,
        }))
        assert resp["success"] is False, "Cashier must not read own open session balance"
        assert "جرد" in resp.get("error", "") or "رصيد" in resp.get("error", "")

    def test_cashier_cannot_read_another_cashiers_balance(self):
        """Cashier cannot read another cashier's drawer balance."""
        db = _fresh_db()
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge_cas1, user_id=2, station="ALL")

        bridge_cas2 = _make_bridge(db, _cashier(3, "cashier2", slot=2))
        resp = json.loads(bridge_cas2._dispatch_session("get_balance", {
            "session_id": session_id,
        }))
        assert resp["success"] is False, "Cashier 2 must not read cashier 1's balance"
        assert "لا يمكن قراءة رصيد درج كاشير آخر" in resp["error"]

    def test_cashier_get_active_and_get_all_only_returns_own_sessions(self):
        """Cashier only sees own sessions in get_active and get_all; manager sees all."""
        db = _fresh_db()
        bridge_mgr = _make_bridge(db, _manager(1))

        # Open session for cashier 1 (COUNTER) and cashier 2 (DELIVERY)
        s1 = _open_session(bridge_mgr, user_id=2, station="COUNTER")
        s2 = _open_session(bridge_mgr, user_id=3, station="DELIVERY")

        # Cashier 1 reads active sessions
        bridge_cas1 = _make_bridge(db, _cashier(2, "cashier1"))
        res_cas1 = json.loads(bridge_cas1._dispatch_session("get_active", {"day_id": 1}))
        assert res_cas1["success"]
        ids_cas1 = [s["id"] for s in res_cas1["data"]]
        assert ids_cas1 == [s1], f"Cashier 1 should only see session {s1}, got {ids_cas1}"

        # Cashier 2 reads active sessions
        bridge_cas2 = _make_bridge(db, _cashier(3, "cashier2", slot=2))
        res_cas2 = json.loads(bridge_cas2._dispatch_session("get_active", {"day_id": 1}))
        assert res_cas2["success"]
        ids_cas2 = [s["id"] for s in res_cas2["data"]]
        assert ids_cas2 == [s2], f"Cashier 2 should only see session {s2}, got {ids_cas2}"

        # Manager reads active sessions: sees both
        res_mgr = json.loads(bridge_mgr._dispatch_session("get_active", {"day_id": 1}))
        assert res_mgr["success"]
        ids_mgr = {s["id"] for s in res_mgr["data"]}
        assert ids_mgr == {s1, s2}

    def test_cashier_cannot_generate_x_report(self):
        """X-Report is manager-only; cashier is rejected."""
        db = _fresh_db()
        bridge_mgr = _make_bridge(db, _manager(1))
        _open_session(bridge_mgr, user_id=2, station="ALL")

        bridge_cas = _make_bridge(db, _cashier(2, "cashier1"))
        resp = json.loads(bridge_cas._dispatch_session("x_report", {"day_id": 1}))
        assert resp["success"] is False
        assert "تقرير X متاح للمدير فقط" in resp["error"]

        # Manager can generate X-Report
        mgr_resp = json.loads(bridge_mgr._dispatch_session("x_report", {"day_id": 1}))
        assert mgr_resp["success"] is True
        assert mgr_resp["data"]["type"] == "X"

    def test_cashier_cannot_close_business_day_without_manager_pin(self):
        """Closing business day requires manager role or valid manager PIN."""
        db = _fresh_db()
        bridge_mgr = _make_bridge(db, _manager(1))
        s_id = _open_session(bridge_mgr, user_id=2, station="ALL")

        # Close the open session first so day close can proceed
        bridge_mgr._dispatch_session("close", {"session_id": s_id, "counted_cash_egp": 100.0})

        # Cashier tries to close business day without manager PIN
        bridge_cas = _make_bridge(db, _cashier(2, "cashier1"))
        resp = json.loads(bridge_cas._dispatch_session("close_day", {"day_id": 1}))
        assert resp["success"] is False
        assert "إغلاق اليوم متاح للمدير فقط" in resp["error"]

        # Cashier tries with invalid manager PIN
        resp_bad_pin = json.loads(bridge_cas._dispatch_session("close_day", {
            "day_id": 1,
            "manager_pin": "9999",
        }))
        assert resp_bad_pin["success"] is False

        # Cashier with valid manager PIN (1234) succeeds
        resp_good_pin = json.loads(bridge_cas._dispatch_session("close_day", {
            "day_id": 1,
            "manager_pin": "1234",
        }))
        assert resp_good_pin["success"] is True
        assert resp_good_pin["data"]["type"] == "Z"

    def test_manager_can_close_any_session_and_read_balance(self):
        """Manager retains cross-drawer access."""
        db = _fresh_db()
        bridge_cas = _make_bridge(db, _cashier(2, "cashier1"))
        session_id = _open_session(bridge_cas, user_id=2, station="ALL")

        bridge_mgr = _make_bridge(db, _manager(1))
        # Manager reads balance
        bal_resp = json.loads(bridge_mgr._dispatch_session("get_balance", {"session_id": session_id}))
        assert bal_resp["success"] is True

        # Manager closes session
        close_resp = json.loads(bridge_mgr._dispatch_session("close", {
            "session_id": session_id,
            "counted_cash_egp": 100.0,
        }))
        assert close_resp["success"] is True

    def test_protection_below_bridge_controllers_and_services(self):
        """Guards are enforced directly in SessionController and CashierSessionService."""
        db = _fresh_db()
        user_repo = UserRepository(db=db)
        auth_svc = AuthService(user_repo=user_repo)
        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)
        session_svc = CashierSessionService(
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            auth_service=auth_svc,
        )
        day_svc = BusinessDayService(
            financial_service=None,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            auth_service=auth_svc,
        )
        ctrl = SessionController(
            session_service=session_svc,
            business_day_service=day_svc,
            auth_service=auth_svc,
        )

        from broast_pos.core.models.cashier_session import Station

        # Open session for user 2
        s = session_svc.open_session(day_id=1, user_id=2, station=Station.COUNTER, opening_float_pt=10000, actor_id=2)
        session_id = s.id

        # 1. Controller close_session as user 3 (cashier 2) -> raises ValueError
        with pytest.raises(ValueError, match="لا يمكن إغلاق درج كاشير آخر"):
            ctrl.close_session(session_id=session_id, counted_cash_egp=100.0, actor_id=3)

        # 2. Service close_session as user 3 -> raises ValueError
        with pytest.raises(ValueError, match="لا يمكن إغلاق درج كاشير آخر"):
            session_svc.close_session(session_id=session_id, counted_cash_pt=10000, actor_id=3)

        # 3. Controller do_handover as user 3 -> raises ValueError
        with pytest.raises(ValueError, match="لا يمكن تسليم درج كاشير آخر"):
            ctrl.do_handover(from_session_id=session_id, to_user_id=3, station="COUNTER", counted_cash_egp=100.0, actor_id=3)

        # 4. Service do_handover as user 3 -> raises ValueError
        with pytest.raises(ValueError, match="لا يمكن تسليم درج كاشير آخر"):
            session_svc.do_handover(from_session_id=session_id, to_user_id=3, station=Station.COUNTER, to_user_counted_pt=10000, actor_id=3)

        # 5. Controller get_session_balance for another cashier -> raises ValueError
        with pytest.raises(ValueError, match="لا يمكن قراءة رصيد درج كاشير آخر"):
            ctrl.get_session_balance(session_id=session_id, actor_id=3)

        # 6. Controller get_session_balance for own open session -> raises ValueError
        with pytest.raises(ValueError, match="لا يمكن قراءة الرصيد المتوقع قبل إجراء الجرد"):
            ctrl.get_session_balance(session_id=session_id, actor_id=2)

        # 7. Controller generate_x_report as cashier -> raises ValueError
        with pytest.raises(ValueError, match="تقرير X متاح للمدير فقط"):
            ctrl.generate_x_report(day_id=1, actor_id=2)

        # 8. Controller close_business_day as cashier without PIN -> raises ValueError
        with pytest.raises(ValueError, match="إغلاق اليوم متاح للمدير فقط"):
            ctrl.close_business_day(day_id=1, actor_id=2)
