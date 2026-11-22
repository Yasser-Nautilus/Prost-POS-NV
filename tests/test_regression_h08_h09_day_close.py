"""
Regression tests — H08/H09: day close integrity.

Root causes:
  H08: bridge "close_shift" action called financial_ctrl.close_shift() directly,
       bypassing business_day_svc._guard_all_sessions_closed(), so the day could
       be closed while cashier sessions were still open.

  H09a: FinancialService.add_expense() accepted any shift_id without checking
        whether that shift is still active, allowing expenses against closed days.

  H09b: _dispatch_session("open") allowed opening a session against a closed
        (inactive) business day_id, writing orphan rows into a frozen day.

  H09c: BusinessDayService.close_business_day() wrote DRIVER_FEE_PAYOUT entries
        BEFORE calling close_shift(). If close_shift failed, the payout entries
        were committed but the shift stayed open.

Fixes verified here:
  H08  — bridge close_shift with open sessions → rejected
  H09a — add_expense with closed shift_id → rejected
  H09b — session.open with inactive day_id → rejected
  H09c — DRIVER_FEE_PAYOUT rolled back when close_shift raises (atomicity)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from broast_pos.core.models.cashier_session import LedgerEntryType, Station
from broast_pos.core.models.user import User, UserRole
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.financial_repository import FinancialRepository
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
        "VALUES (1,'manager1','مدير','manager','h1',1),(2,'cashier1','كاشير','cashier','h2',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, "
        "business_date, summary_printed_at) VALUES "
        "(1, 1, datetime('now'), 1, 1, date('now','localtime'), datetime('now'))"
    )
    db.commit()
    return db


def _manager() -> User:
    return User(id=1, username="mgr", display_name="مدير", role=UserRole.MANAGER, pin_hash="", is_active=True)


def _make_bridge(db, current_user):
    from broast_pos.features.financial.financial_controller import FinancialController
    from broast_pos.infrastructure.web_bridge.bridge import POSBridge

    session_repo = CashierSessionRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    financial_repo = FinancialRepository(db=db)
    audit_repo = AuditRepository(db=db)

    mock_auth = MagicMock()
    mock_auth.verify_manager_pin.return_value = current_user
    mock_auth.get_manager_by_pin.return_value = current_user
    mock_auth.verify_pin.return_value = current_user

    fin_svc = FinancialService(
        financial_repo=financial_repo,
        audit_repo=audit_repo,
        auth_service=mock_auth,
    )
    session_svc = CashierSessionService(
        session_repo=session_repo, ledger_repo=ledger_repo
    )
    day_svc = BusinessDayService(
        financial_service=fin_svc,
        session_repo=session_repo,
        ledger_repo=ledger_repo,
    )
    fin_ctrl = FinancialController(
        financial_service=fin_svc,
        auth_service=mock_auth,
    )
    session_ctrl = SessionController(
        session_service=session_svc, business_day_service=day_svc
    )

    bridge = POSBridge.__new__(POSBridge)
    bridge._financial_ctrl = fin_ctrl
    bridge._financial = fin_svc
    bridge._session_ctrl = session_ctrl
    bridge._session_svc = session_svc
    bridge._current_user = current_user
    bridge._trigger_shift_status_changed = lambda: None
    return bridge


class TestH08CloseShiftRouting:

    def test_close_shift_with_open_sessions_rejected(self):
        """bridge close_shift must reject while a cashier session is still open."""
        db = _fresh_db()
        mgr = _manager()
        bridge = _make_bridge(db, mgr)

        # Open a session
        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)
        svc = CashierSessionService(session_repo=session_repo, ledger_repo=ledger_repo)
        svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0, actor_id=1)

        resp = json.loads(bridge.dispatch("close_shift", json.dumps({"manager_pin": "1234"})))
        assert resp["success"] is False, "close_shift with open sessions must be rejected"
        assert "وردية" in resp.get("error", ""), f"Unexpected error: {resp.get('error')}"

    def test_close_shift_succeeds_when_all_sessions_closed(self):
        """bridge close_shift succeeds when all sessions are already closed."""
        db = _fresh_db()
        mgr = _manager()
        bridge = _make_bridge(db, mgr)

        # No sessions open → close should succeed
        resp = json.loads(bridge.dispatch("close_shift", json.dumps({"manager_pin": "1234"})))
        assert resp["success"] is True, f"close_shift with no open sessions must succeed: {resp}"


class TestH09ClosedDayGuards:

    def test_add_expense_on_closed_shift_rejected(self):
        """Adding an expense to a closed shift_id must be rejected."""
        db = _fresh_db()
        # Close the shift directly in the DB
        db.execute("UPDATE shifts SET is_active = 0, closed_at = datetime('now') WHERE id = 1")
        db.commit()

        audit_repo = AuditRepository(db=db)
        fin_svc = FinancialService(
            financial_repo=FinancialRepository(db=db),
            audit_repo=audit_repo,
            auth_service=MagicMock(),
        )

        with pytest.raises(ValueError, match="مغلق|غير.*نشطة|مغلقة"):
            fin_svc.add_expense(
                shift_id=1, amount=50.0, description="test", category="other", user_id=1
            )

    def test_session_open_on_inactive_day_rejected(self):
        """Opening a session against a closed/inactive day_id must be rejected."""
        db = _fresh_db()
        # Close the shift
        db.execute("UPDATE shifts SET is_active = 0, closed_at = datetime('now') WHERE id = 1")
        db.commit()

        mgr = _manager()
        bridge = _make_bridge(db, mgr)

        resp = json.loads(bridge.dispatch("session.open", json.dumps({
            "day_id": 1, "station": "ALL", "opening_float_egp": 100.0,
        })))
        assert resp["success"] is False, "Session open on inactive day must be rejected"
        assert "مغلق" in resp.get("error", "") or "غير نشط" in resp.get("error", "") or \
               "مغلقة" in resp.get("error", ""), f"Unexpected error: {resp.get('error')}"


class TestH09cPayoutRollback:

    def test_payout_entries_rolled_back_when_close_shift_fails(self):
        """DRIVER_FEE_PAYOUT entries must be rolled back if close_shift raises."""
        db = _fresh_db()

        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)

        mock_fin_svc = MagicMock()
        mock_fin_svc.close_shift.side_effect = RuntimeError("injected close_shift failure")

        svc = BusinessDayService(
            financial_service=mock_fin_svc,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
        )

        # Inject fake payout rows — bypass delivery_repo by patching _batch_driver_fee_payouts
        payout_written = []

        def _patched_batch(day_id):
            # Directly write a payout entry to simulate what the method would do
            from datetime import datetime

            from broast_pos.core.models.cashier_session import (
                CashierSession,
                CashLedgerEntry,
                Station,
            )

            session = session_repo.create(CashierSession(
                id=None, day_id=day_id, user_id=1, station=Station.ALL,
                is_open=False, opened_at=datetime.now().isoformat(),
            ))
            entry = CashLedgerEntry(
                id=None, day_id=day_id, session_id=session.id,
                entry_type=LedgerEntryType.DRIVER_FEE_PAYOUT,
                amount_pt=-1000, actor_id=1,
            )
            ledger_repo.append(entry)
            payout_written.append(True)

        with patch.object(svc, "_batch_driver_fee_payouts", side_effect=_patched_batch):
            with pytest.raises(RuntimeError, match="injected"):
                svc.close_business_day(day_id=1, manager_pin="1234")

        # Payout entry must have been attempted
        assert payout_written, "Payout write was never attempted"

        # But the DRIVER_FEE_PAYOUT row must be rolled back
        rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE entry_type = ?",
            (LedgerEntryType.DRIVER_FEE_PAYOUT.value,),
        )
        assert len(rows) == 0, (
            f"Payout entries must be rolled back when close_shift fails, found {len(rows)}"
        )
