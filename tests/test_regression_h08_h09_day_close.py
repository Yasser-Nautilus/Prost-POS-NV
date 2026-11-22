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
    # Seed a category and product for order tests (FK: order_items.product_id → products.id)
    db.execute("INSERT INTO categories (id, name, sort_order, is_active) VALUES (1, 'وجبات', 0, 1)")
    db.execute(
        "INSERT INTO products (id, name, price, category_id, is_active) "
        "VALUES (1, 'الوجبة', 100.0, 1, 1)"
    )
    # Seed delivery trips referenced by payout tests (FK: cash_ledger.trip_id → delivery_trips.id)
    db.execute(
        "INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled, total_delivery_fees) "
        "VALUES (10, 2, 'سائق', 1, 35.0), (42, 2, 'سائق', 1, 25.0), "
        "(77, 2, 'سائق', 1, 30.0), (99, 2, 'سائق', 1, 50.0)"
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
        cashier_session_repo=session_repo,
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

    def test_legacy_close_shift_without_session_ctrl_rejects_open_sessions(self):
        """H08: Even when session_ctrl is None (legacy fallback in bridge or direct
        FinancialService.close_shift call), open cashier sessions must block shift close.
        """
        db = _fresh_db()
        mgr = _manager()
        bridge = _make_bridge(db, mgr)

        # Open a session in the DB
        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)
        svc = CashierSessionService(session_repo=session_repo, ledger_repo=ledger_repo)
        svc.open_session(day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0, actor_id=1)

        # Force legacy fallback by clearing _session_ctrl
        bridge._session_ctrl = None

        resp = json.loads(bridge.dispatch("close_shift", json.dumps({"manager_pin": "1234"})))
        assert resp["success"] is False, "Legacy close_shift must reject when cashier session is open"
        assert "وردية" in resp.get("error", "")

    def test_payment_on_closed_day_rejected(self):
        """H08: Completing/paying an order on a closed shift must be rejected."""
        from broast_pos.core.models.order import (
            Order,
            OrderItem,
            OrderStatus,
            OrderType,
            PaymentMethod,
        )
        from broast_pos.core.services.order_service import OrderService
        from broast_pos.data.repositories.order_repository import OrderRepository

        db = _fresh_db()
        order_repo = OrderRepository(db=db)
        fin_repo = FinancialRepository(db=db)
        fin_svc = FinancialService(financial_repo=fin_repo)
        order_svc = OrderService(order_repo=order_repo, financial_service=fin_svc)

        # Create an order on shift 1
        order = Order(
            id=None,
            invoice_no=1,
            shift_id=1,
            order_type=OrderType.TAKEAWAY,
            status=OrderStatus.NEW,
            items=[OrderItem(product_id=1, product_name="الوجبة", unit_price=100.0, quantity=1)],
            subtotal=100.0,
            total=100.0,
            created_by_id=1,
            created_by_name="كاشير",
            cashier_slot=1,
        )
        saved = order_repo.save(order)

        # Close shift 1
        db.execute("UPDATE shifts SET is_active = 0, closed_at = datetime('now') WHERE id = 1")
        db.commit()

        # Attempt to complete payment on the closed shift's order
        with pytest.raises(ValueError, match="مغلقة"):
            order_svc.complete_order(
                order_id=saved.id,
                payment_method=PaymentMethod.CASH,
                amount_received=100.0,
            )

    def test_session_open_below_bridge_on_closed_day_rejected(self):
        """H08: CashierSessionService.open_session directly rejects opening on closed day."""
        db = _fresh_db()
        # Close shift 1
        db.execute("UPDATE shifts SET is_active = 0, closed_at = datetime('now') WHERE id = 1")
        db.commit()

        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)
        svc = CashierSessionService(session_repo=session_repo, ledger_repo=ledger_repo)

        with pytest.raises(ValueError, match="مغلق"):
            svc.open_session(
                day_id=1, user_id=2, station=Station.ALL, opening_float_pt=0, actor_id=1
            )


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

        with (
            patch.object(svc, "_batch_driver_fee_payouts", side_effect=_patched_batch),
            pytest.raises(RuntimeError, match="injected"),
        ):
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


class TestH09DriverPayoutSafeguards:
    """Verifies H09 requirements:
    1. Berechtigung und Voraussetzungen vor Buchungen prüfen (Fehler lässt Ledger/Kasse unverändert).
    2. Auszahlung der richtigen Kasse zuordnen.
    3. Doppelte Auszahlung zuverlässig verhindern (Wiederholung zahlt nicht zweimal aus).
    4. DB partial unique index blocks duplicate payout at SQL level.
    """

    def test_payout_not_booked_if_manager_pin_invalid(self):
        """Invalid manager PIN rejects BEFORE any payout booking — ledger stays empty."""
        db = _fresh_db()
        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)

        mock_auth = MagicMock()
        mock_auth.verify_manager_pin.side_effect = PermissionError("PIN غير صحيح")

        mock_deliv = MagicMock()
        mock_deliv.get_settled_trip_fees_for_shift.return_value = [
            {"trip_id": 10, "total_delivery_fees": 35.0}
        ]

        svc = BusinessDayService(
            financial_service=MagicMock(),
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            auth_service=mock_auth,
            delivery_repo=mock_deliv,
        )

        with pytest.raises(PermissionError, match="PIN"):
            svc.close_business_day(day_id=1, manager_pin="wrong_pin")

        # Ledger must remain completely empty (no payouts booked)
        rows = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(rows) == 0, "No payout should be booked when authorization fails"

    def test_payout_not_booked_if_prerequisites_fail(self):
        """If shift prerequisites (e.g. summary not printed) fail, no payout is booked."""
        db = _fresh_db()
        # Reset summary_printed_at to NULL so prerequisite fails
        db.execute("UPDATE shifts SET summary_printed_at = NULL WHERE id = 1")
        db.commit()

        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)
        fin_repo = FinancialRepository(db=db)
        mock_auth = MagicMock()
        mock_auth.verify_manager_pin.return_value = _manager()
        fin_svc = FinancialService(financial_repo=fin_repo, auth_service=mock_auth)

        mock_deliv = MagicMock()
        mock_deliv.get_settled_trip_fees_for_shift.return_value = [
            {"trip_id": 10, "total_delivery_fees": 35.0}
        ]

        svc = BusinessDayService(
            financial_service=fin_svc,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            delivery_repo=mock_deliv,
            auth_service=mock_auth,
        )

        with pytest.raises(ValueError, match="تقرير"):
            svc.close_business_day(day_id=1, manager_pin="1234")

        # Ledger must be untouched
        rows = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(rows) == 0, "No payout should be booked when shift prerequisites fail"

    def test_payout_assigned_to_open_delivery_session(self):
        """Payout must be assigned to the open delivery session if one is active."""
        from broast_pos.core.models.cashier_session import CashierSession
        db = _fresh_db()
        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)

        # Create an open DELIVERY session
        open_session = session_repo.create(CashierSession(
            id=None, day_id=1, user_id=2, station=Station.DELIVERY,
            is_open=True, opened_at="2026-11-22T20:00:00",
        ))

        mock_deliv = MagicMock()
        mock_deliv.get_settled_trip_fees_for_shift.return_value = [
            {"trip_id": 42, "total_delivery_fees": 25.0}
        ]

        svc = BusinessDayService(
            financial_service=None,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            delivery_repo=mock_deliv,
        )

        count = svc._batch_driver_fee_payouts(day_id=1)
        assert count == 1

        entries = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(entries) == 1
        assert entries[0]["session_id"] == open_session.id
        assert entries[0]["amount_pt"] == -2500

    def test_payout_repetition_does_not_pay_twice(self):
        """Repeating the batch payout for the same day/trips does NOT create duplicates."""
        from broast_pos.core.models.cashier_session import CashierSession
        db = _fresh_db()
        session_repo = CashierSessionRepository(db=db)
        ledger_repo = CashLedgerRepository(db=db)

        # Create session
        session_repo.create(CashierSession(
            id=None, day_id=1, user_id=1, station=Station.ALL,
            is_open=True, opened_at="2026-11-22T20:00:00",
        ))

        mock_deliv = MagicMock()
        mock_deliv.get_settled_trip_fees_for_shift.return_value = [
            {"trip_id": 99, "total_delivery_fees": 50.0}
        ]

        svc = BusinessDayService(
            financial_service=None,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            delivery_repo=mock_deliv,
        )

        first_count = svc._batch_driver_fee_payouts(day_id=1)
        assert first_count == 1

        # Second run (repetition)
        second_count = svc._batch_driver_fee_payouts(day_id=1)
        assert second_count == 0, "Repeated payout batch must not pay again"

        entries = db.fetch_all("SELECT * FROM cash_ledger WHERE entry_type = 'DRIVER_FEE_PAYOUT'")
        assert len(entries) == 1, "Exactly one payout entry must exist"

    def test_db_unique_index_prevents_duplicate_driver_payout(self):
        """Database constraint uq_ledger_driver_payout blocks duplicate entry for same trip_id."""
        import sqlite3

        from broast_pos.core.models.cashier_session import CashierSession
        db = _fresh_db()
        session_repo = CashierSessionRepository(db=db)
        session = session_repo.create(CashierSession(
            id=None, day_id=1, user_id=1, station=Station.ALL,
            is_open=True, opened_at="2026-11-22T20:00:00",
        ))

        # First insert
        db.execute(
            """INSERT INTO cash_ledger (day_id, session_id, entry_type, amount_pt, trip_id, actor_id, reason, created_at)
               VALUES (1, ?, 'DRIVER_FEE_PAYOUT', -3000, 77, 1, 'payout 1', datetime('now', 'localtime'))""",
            (session.id,),
        )
        db.commit()

        # Second insert for identical trip_id must fail at DB constraint level
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO cash_ledger (day_id, session_id, entry_type, amount_pt, trip_id, actor_id, reason, created_at)
                   VALUES (1, ?, 'DRIVER_FEE_PAYOUT', -3000, 77, 1, 'payout 2', datetime('now', 'localtime'))""",
                (session.id,),
            )
            db.commit()
