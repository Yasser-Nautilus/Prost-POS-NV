"""
Regression tests — H07: session open/close atomicity.

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
        original_append = svc._ledger.append

        def _fail_append(entry):
            raise RuntimeError("injected ledger failure")

        with patch.object(svc._ledger, "append", side_effect=_fail_append):
            with pytest.raises(RuntimeError, match="injected"):
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

        original_close = svc._sessions.close_session

        def _fail_close(**kwargs):
            raise RuntimeError("injected close failure")

        with patch.object(svc._sessions, "close_session", side_effect=_fail_close):
            with pytest.raises(RuntimeError, match="injected"):
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
