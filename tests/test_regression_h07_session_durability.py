"""
Regression tests — H07: session open/close/handover atomicity.

Root cause: open_session() and close_session() each make two separate DB
writes without wrapping them in db.transaction(), so a Python exception
between the first and second write leaves partial state:
  - open_session:  session row created, OPENING_FLOAT ledger entry missing
  - close_session: ADJUSTMENT entry written, session row still marked is_open

Fixes verified here:
  - open_session success: both session row and OPENING_FLOAT entry survive
    a connection close+reopen (file-backed DB).
  - open_session failure: injected error after session INSERT → both writes
    are rolled back; no orphan session row remains.
  - close_session failure: injected error after ADJUSTMENT INSERT → both
    writes are rolled back; session remains open, adjustment gone.
  - handover failure: injected error after close_session in handover → all
    writes are rolled back; outgoing session remains open, no new session.
  - audit failure: simulated mandatory audit entry failure → all writes
    are rolled back; no partial state remains.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from broast_pos.core.models.cashier_session import LedgerEntryType, Station
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _seed(db: DatabaseConnection) -> None:
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'cashier1','كاشير 1','cashier','h1',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.commit()


def _make_svc(db: DatabaseConnection) -> CashierSessionService:
    return CashierSessionService(
        session_repo=CashierSessionRepository(db=db),
        ledger_repo=CashLedgerRepository(db=db),
    )


class TestH07SessionDurability:

    def test_open_session_persists_across_reconnect(self):
        """Both session row and OPENING_FLOAT entry survive a connection reset."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            # First connection: create + seed + open session
            db = DatabaseConnection(path)
            DatabaseConnection._instance = db
            initialise_database(db)
            _seed(db)

            svc = _make_svc(db)
            session = svc.open_session(
                day_id=1, user_id=1, station=Station.ALL,
                opening_float_pt=10_000, actor_id=1,
            )
            session_id = session.id

            DatabaseConnection.reset()

            # Reopen and verify both rows are present
            db2 = DatabaseConnection(path)
            DatabaseConnection._instance = db2

            row = db2.fetch_one(
                "SELECT * FROM cashier_sessions WHERE id = ?", (session_id,)
            )
            assert row is not None, "Session row must survive reconnect"
            assert row["is_open"] == 1

            ledger_rows = db2.fetch_all(
                "SELECT * FROM cash_ledger WHERE session_id = ? AND entry_type = ?",
                (session_id, LedgerEntryType.OPENING_FLOAT.value),
            )
            assert len(ledger_rows) == 1, "OPENING_FLOAT entry must survive reconnect"
        finally:
            DatabaseConnection.reset()
            try:
                os.unlink(path)
            except OSError:
                pass

    def test_open_session_rollback_on_ledger_failure(self):
        """If ledger.append fails during open, the session INSERT is rolled back."""
        db = DatabaseConnection(":memory:")
        DatabaseConnection._instance = db
        initialise_database(db)
        _seed(db)

        svc = _make_svc(db)

        def _fail_append(entry):
            raise RuntimeError("injected ledger failure")

        with (
            patch.object(svc._ledger, "append", side_effect=_fail_append),
            pytest.raises(RuntimeError, match="injected"),
        ):
            svc.open_session(
                day_id=1, user_id=1, station=Station.ALL,
                opening_float_pt=10_000, actor_id=1,
            )

        # After rollback, no orphan session row must exist
        rows = db.fetch_all("SELECT * FROM cashier_sessions WHERE day_id = 1")
        assert len(rows) == 0, (
            f"Rolled-back open_session must leave no orphan session row, found {len(rows)}"
        )

    def test_close_session_rollback_on_repo_failure(self):
        """If close_session repo call fails, the ADJUSTMENT entry is rolled back."""
        db = DatabaseConnection(":memory:")
        DatabaseConnection._instance = db
        initialise_database(db)
        _seed(db)

        svc = _make_svc(db)

        # Open a session normally
        session = svc.open_session(
            day_id=1, user_id=1, station=Station.ALL,
            opening_float_pt=10_000, actor_id=1,
        )

        def _fail_close(**kwargs):
            raise RuntimeError("injected close failure")

        with (
            patch.object(svc._sessions, "close_session", side_effect=_fail_close),
            pytest.raises(RuntimeError, match="injected"),
        ):
            # counted_cash_pt != expected → triggers ADJUSTMENT entry first
            svc.close_session(
                session_id=session.id,
                counted_cash_pt=12_000,   # EGP 20 more than the float
                actor_id=1,
            )

        # Session must still be open (close_session repo was never reached / rolled back)
        reloaded = CashierSessionRepository(db=db).get_by_id(session.id)
        assert reloaded.is_open is True, "Session must remain open after rolled-back close"

        # ADJUSTMENT entry must not exist (also rolled back)
        adj_rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE session_id = ? AND entry_type = ?",
            (session.id, LedgerEntryType.ADJUSTMENT.value),
        )
        assert len(adj_rows) == 0, (
            f"Rolled-back ADJUSTMENT entry must not persist, found {len(adj_rows)}"
        )

    # ------------------------------------------------------------------
    # Handover rollback
    # ------------------------------------------------------------------

    def test_handover_rollback_on_new_session_failure(self):
        """If creating the incoming session fails during handover, all writes
        (ADJUSTMENT, HANDOVER_OUT, outgoing close) are rolled back.

        The outgoing session must remain open and no ledger entries from the
        handover may persist.
        """
        db = DatabaseConnection(":memory:")
        DatabaseConnection._instance = db
        initialise_database(db)
        _seed(db)
        # Add a second user for the incoming session
        db.execute(
            "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
            "VALUES (2, 'cashier2', 'كاشير 2', 'cashier', 'h2', 1)"
        )
        db.commit()

        svc = _make_svc(db)

        # Open a session normally
        session = svc.open_session(
            day_id=1, user_id=1, station=Station.ALL,
            opening_float_pt=10_000, actor_id=1,
        )

        # Count ledger entries before handover
        ledger_before = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE day_id = 1"
        )

        def _fail_create(s):
            raise RuntimeError("injected create failure in handover")

        with (
            patch.object(svc._sessions, "create", side_effect=_fail_create),
            pytest.raises(RuntimeError, match="injected create failure"),
        ):
            svc.do_handover(
                from_session_id=session.id,
                to_user_id=2,
                station=Station.ALL,
                actor_id=1,
            )

        # Outgoing session must still be open (close was rolled back)
        reloaded = CashierSessionRepository(db=db).get_by_id(session.id)
        assert reloaded.is_open is True, (
            "Outgoing session must remain open after handover rollback"
        )

        # No new session must exist
        all_sessions = db.fetch_all("SELECT * FROM cashier_sessions WHERE day_id = 1")
        assert len(all_sessions) == 1, (
            f"Only the original session should exist, found {len(all_sessions)}"
        )

        # Ledger must be unchanged (no HANDOVER_OUT, ADJUSTMENT, etc.)
        ledger_after = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE day_id = 1"
        )
        assert len(ledger_after) == len(ledger_before), (
            f"Ledger entries must be unchanged after rollback: "
            f"before={len(ledger_before)} after={len(ledger_after)}"
        )

    def test_handover_rollback_on_handover_link_failure(self):
        """If set_handover_link fails, the entire handover is rolled back.

        No orphan sessions, no leaked ledger entries.
        """
        db = DatabaseConnection(":memory:")
        DatabaseConnection._instance = db
        initialise_database(db)
        _seed(db)
        db.execute(
            "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
            "VALUES (2, 'cashier2', 'كاشير 2', 'cashier', 'h2', 1)"
        )
        db.commit()

        svc = _make_svc(db)

        session = svc.open_session(
            day_id=1, user_id=1, station=Station.ALL,
            opening_float_pt=10_000, actor_id=1,
        )

        ledger_before = db.fetch_all("SELECT * FROM cash_ledger WHERE day_id = 1")

        def _fail_link(from_id, to_id):
            raise RuntimeError("injected handover link failure")

        with (
            patch.object(svc._sessions, "set_handover_link", side_effect=_fail_link),
            pytest.raises(RuntimeError, match="injected handover link"),
        ):
            svc.do_handover(
                from_session_id=session.id,
                to_user_id=2,
                station=Station.ALL,
                actor_id=1,
            )

        # Outgoing must still be open
        reloaded = CashierSessionRepository(db=db).get_by_id(session.id)
        assert reloaded.is_open is True

        # Only original session
        all_sessions = db.fetch_all("SELECT * FROM cashier_sessions WHERE day_id = 1")
        assert len(all_sessions) == 1

        # Ledger unchanged
        ledger_after = db.fetch_all("SELECT * FROM cash_ledger WHERE day_id = 1")
        assert len(ledger_after) == len(ledger_before)

    # ------------------------------------------------------------------
    # Mandatory audit entry failure
    # ------------------------------------------------------------------

    def test_open_session_rollback_on_audit_failure(self):
        """Simulated audit / mandatory ledger entry failure during open_session:
        both session row and any ledger writes are rolled back completely.

        This covers the H07 requirement that a mandatory audit entry failure
        must leave zero partial state.
        """
        db = DatabaseConnection(":memory:")
        DatabaseConnection._instance = db
        initialise_database(db)
        _seed(db)

        svc = _make_svc(db)

        def _fail_on_audit(entry):
            raise RuntimeError("mandatory audit entry failed")

        with (
            patch.object(svc._ledger, "append", side_effect=_fail_on_audit),
            pytest.raises(RuntimeError, match="mandatory audit"),
        ):
            svc.open_session(
                day_id=1, user_id=1, station=Station.ALL,
                opening_float_pt=10_000, actor_id=1,
            )

        # Zero partial state: no session row, no ledger entries
        sessions = db.fetch_all("SELECT * FROM cashier_sessions WHERE day_id = 1")
        assert len(sessions) == 0, (
            f"No session must exist after audit failure, found {len(sessions)}"
        )

        ledger = db.fetch_all("SELECT * FROM cash_ledger WHERE day_id = 1")
        assert len(ledger) == 0, (
            f"No ledger entries must exist after audit failure, found {len(ledger)}"
        )

    def test_close_session_rollback_on_audit_failure(self):
        """Simulated audit failure during close_session: the ADJUSTMENT entry
        and the session close are both rolled back.

        The session must remain open, and no ADJUSTMENT entry persists.
        """
        db = DatabaseConnection(":memory:")
        DatabaseConnection._instance = db
        initialise_database(db)
        _seed(db)

        svc = _make_svc(db)

        # Open normally
        session = svc.open_session(
            day_id=1, user_id=1, station=Station.ALL,
            opening_float_pt=10_000, actor_id=1,
        )

        ledger_before = db.fetch_all("SELECT * FROM cash_ledger WHERE day_id = 1")

        # Inject failure on the ADJUSTMENT ledger append (which acts as the
        # mandatory audit entry for close). We need to fail only on the
        # second append (ADJUSTMENT), not on the OPENING_FLOAT that already
        # succeeded during open_session.
        original_append = svc._ledger.append

        def _fail_adjustment(entry):
            if entry.entry_type == LedgerEntryType.ADJUSTMENT:
                raise RuntimeError("mandatory audit entry failed on close")
            return original_append(entry)

        with (
            patch.object(svc._ledger, "append", side_effect=_fail_adjustment),
            pytest.raises(RuntimeError, match="mandatory audit"),
        ):
            svc.close_session(
                session_id=session.id,
                counted_cash_pt=12_000,  # variance to trigger ADJUSTMENT
                actor_id=1,
            )

        # Session must still be open
        reloaded = CashierSessionRepository(db=db).get_by_id(session.id)
        assert reloaded.is_open is True, (
            "Session must remain open after audit failure during close"
        )

        # No ADJUSTMENT entry
        adj_rows = db.fetch_all(
            "SELECT * FROM cash_ledger WHERE session_id = ? AND entry_type = ?",
            (session.id, LedgerEntryType.ADJUSTMENT.value),
        )
        assert len(adj_rows) == 0, (
            f"ADJUSTMENT must not persist after audit failure, found {len(adj_rows)}"
        )

        # Ledger count unchanged from before close attempt
        ledger_after = db.fetch_all("SELECT * FROM cash_ledger WHERE day_id = 1")
        assert len(ledger_after) == len(ledger_before)
