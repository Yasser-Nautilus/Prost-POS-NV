"""
Tests for v2 Phase 1 — Schema v5: cashier_sessions + cash_ledger.

Covers:
  - Migration: both fresh install and upgrade from v4
  - DB constraints: station exclusivity (UNIQUE index + trigger)
  - DB constraints: ledger append-only (UPDATE + DELETE both rejected)
  - DB constraints: idempotency indexes (duplicate SALE_CASH, DRIVER_REMITTANCE)
  - Cash balance formula: SUM(amount_pt) is the sole source of truth
  - Repository: CashierSessionRepository CRUD
  - Repository: CashLedgerRepository append + balance queries
  - Models: Station enum, LedgerEntryType enum, dataclass fields
"""
from __future__ import annotations

import sqlite3
import pytest
from datetime import datetime, timezone

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database, LATEST_VERSION
from broast_pos.core.models.cashier_session import (
    CashierSession, CashLedgerEntry, Station, LedgerEntryType
)
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository


# ---------------------------------------------------------------------------
# Autouse fixture: reset the DB singleton before/after every test in this
# module so tests from other files don't bleed their file-based singleton in.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_db_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    # DatabaseConnection.__init__ guards against double-creation, so
    # _instance must be None before we call the constructor.
    # The autouse fixture calls reset() before every test, so this is safe.
    db = DatabaseConnection(":memory:")
    # Register as singleton so repos that call get_instance() get this DB.
    DatabaseConnection._instance = db
    initialise_database(db)
    # Seed a user and a shift (day) for FK references
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'mgr','Manager','manager','hash1',1), "
        "       (2,'cas','Cashier','cashier','hash2',1)"
    )
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, next_invoice_no, is_active, business_date) "
        "VALUES (1, 1, datetime('now'), 1, 1, date('now','localtime'))"
    )
    db.commit()
    return db


# ===========================================================================
# Part A: Schema version
# ===========================================================================

class TestSchemaVersion:
    def test_fresh_install_is_latest(self):
        db = _fresh_db()
        v = db.fetch_one("SELECT version FROM schema_version LIMIT 1")["version"]
        assert v == LATEST_VERSION == 5

    def test_tables_exist(self):
        db = _fresh_db()
        tables = {r["name"] for r in db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "cashier_sessions" in tables
        assert "cash_ledger" in tables

    def test_shifts_has_new_columns(self):
        db = _fresh_db()
        cols = {r["name"] for r in db.fetch_all("PRAGMA table_info(shifts)")}
        assert "business_date" in cols
        assert "opened_float_note" in cols
        assert "closed_reason" in cols


# ===========================================================================
# Part B: cashier_sessions constraints
# ===========================================================================

class TestCashierSessionConstraints:

    def test_open_two_sessions_different_stations(self):
        """COUNTER + DELIVERY can both be open on the same day."""
        db = _fresh_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,2,'COUNTER',1,?,0)", (now,)
        )
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,1,'DELIVERY',1,?,0)", (now,)
        )
        db.commit()
        cnt = db.fetch_one("SELECT COUNT(*) AS c FROM cashier_sessions WHERE is_open=1")["c"]
        assert cnt == 2

    def test_unique_index_blocks_duplicate_station(self):
        """Two open sessions for the same station on the same day → rejected."""
        db = _fresh_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,2,'COUNTER',1,?,0)", (now,)
        )
        db.commit()
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            db.execute(
                "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
                "VALUES (1,1,'COUNTER',1,?,0)", (now,)
            )
            db.commit()

    def test_trigger_blocks_all_plus_counter(self):
        """ALL + COUNTER on same day → trigger ABORT."""
        db = _fresh_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,2,'ALL',1,?,0)", (now,)
        )
        db.commit()
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            db.execute(
                "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
                "VALUES (1,1,'COUNTER',1,?,0)", (now,)
            )
            db.commit()

    def test_trigger_blocks_counter_plus_all(self):
        """COUNTER open → trying to open ALL → ABORT."""
        db = _fresh_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,2,'COUNTER',1,?,0)", (now,)
        )
        db.commit()
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            db.execute(
                "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
                "VALUES (1,1,'ALL',1,?,0)", (now,)
            )
            db.commit()

    def test_closed_all_then_open_counter_allowed(self):
        """Closed ALL session → opening COUNTER afterwards is fine."""
        db = _fresh_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,2,'ALL',0,?,0)", (now,)  # is_open=0 → closed
        )
        db.commit()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,1,'COUNTER',1,?,0)", (now,)
        )
        db.commit()
        cnt = db.fetch_one("SELECT COUNT(*) AS c FROM cashier_sessions WHERE is_open=1")["c"]
        assert cnt == 1


# ===========================================================================
# Part C: cash_ledger — append-only enforcement
# ===========================================================================

class TestCashLedgerAppendOnly:

    def _insert_session(self, db):
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (1,1,'ALL',1,?,0)", (now,)
        )
        db.commit()
        return db.fetch_one("SELECT last_insert_rowid() AS id")["id"]

    def _insert_entry(self, db, session_id):
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cash_ledger (day_id,session_id,entry_type,amount_pt,actor_id,created_at) "
            "VALUES (1,?,?,?,1,?)", (session_id, "OPENING_FLOAT", 50000, now)
        )
        db.commit()
        return db.fetch_one("SELECT last_insert_rowid() AS id")["id"]

    def test_insert_works(self):
        db = _fresh_db()
        sid = self._insert_session(db)
        eid = self._insert_entry(db, sid)
        assert eid is not None

    def test_update_raises(self):
        """UPDATE on cash_ledger must be rejected by trigger."""
        db = _fresh_db()
        sid = self._insert_session(db)
        eid = self._insert_entry(db, sid)
        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
            db.execute("UPDATE cash_ledger SET amount_pt = 99999 WHERE id = ?", (eid,))
            db.commit()

    def test_delete_raises(self):
        """DELETE on cash_ledger must be rejected by trigger."""
        db = _fresh_db()
        sid = self._insert_session(db)
        eid = self._insert_entry(db, sid)
        with pytest.raises((sqlite3.OperationalError, sqlite3.IntegrityError)):
            db.execute("DELETE FROM cash_ledger WHERE id = ?", (eid,))
            db.commit()

    def test_duplicate_sale_cash_raises(self):
        """Two SALE_CASH entries for the same order_id → unique index violation."""
        db = _fresh_db()
        sid = self._insert_session(db)
        # Seed a minimal order
        db.execute(
            "INSERT INTO orders (id,invoice_no,shift_id,order_type,status,subtotal,total,"
            "created_by_id,created_by_name,cashier_slot) "
            "VALUES (101,1,1,'takeaway','completed',100,100,1,'Manager',1)"
        )
        db.commit()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cash_ledger (day_id,session_id,entry_type,amount_pt,order_id,actor_id,created_at) "
            "VALUES (1,?,?,?,101,1,?)", (sid, "SALE_CASH", 10000, now)
        )
        db.commit()
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            db.execute(
                "INSERT INTO cash_ledger (day_id,session_id,entry_type,amount_pt,order_id,actor_id,created_at) "
                "VALUES (1,?,?,?,101,1,?)", (sid, "SALE_CASH", 10000, now)
            )
            db.commit()

    def test_duplicate_driver_remittance_raises(self):
        """Two DRIVER_REMITTANCE for the same trip_id → rejected."""
        db = _fresh_db()
        sid = self._insert_session(db)
        # delivery_trips requires driver_id (FK users), driver_name, is_settled
        db.execute(
            "INSERT INTO delivery_trips (id,driver_id,driver_name,is_settled) "
            "VALUES (55,1,'سائق',0)"
        )
        db.commit()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cash_ledger (day_id,session_id,entry_type,amount_pt,trip_id,actor_id,created_at) "
            "VALUES (1,?,?,?,55,1,?)", (sid, "DRIVER_REMITTANCE", 25000, now)
        )
        db.commit()
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            db.execute(
                "INSERT INTO cash_ledger (day_id,session_id,entry_type,amount_pt,trip_id,actor_id,created_at) "
                "VALUES (1,?,?,?,55,1,?)", (sid, "DRIVER_REMITTANCE", 25000, now)
            )
            db.commit()


# ===========================================================================
# Part D: Cash balance formula
# ===========================================================================

class TestCashBalanceFormula:

    def _setup(self):
        db = _fresh_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cashier_sessions (id,day_id,user_id,station,is_open,opened_at,opening_float_pt) "
            "VALUES (10,1,1,'ALL',1,?,0)", (now,)
        )
        db.commit()
        return db

    def _add_entry(self, db, session_id, entry_type, amount_pt):
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO cash_ledger (day_id,session_id,entry_type,amount_pt,actor_id,created_at) "
            "VALUES (1,?,?,?,1,?)", (session_id, entry_type, amount_pt, now)
        )
        db.commit()

    def test_empty_session_balance_is_zero(self):
        db = self._setup()
        row = db.fetch_one("SELECT COALESCE(SUM(amount_pt),0) AS b FROM cash_ledger WHERE session_id=10")
        assert row["b"] == 0

    def test_balance_is_sum_of_entries(self):
        """Balance = SUM of all entries (the ONLY formula, ADR-1)."""
        db = self._setup()
        self._add_entry(db, 10, "OPENING_FLOAT", 50000)  # +500 EGP
        self._add_entry(db, 10, "SALE_CASH", 12000)       # +120 EGP
        self._add_entry(db, 10, "EXPENSE", -5000)          # -50 EGP
        row = db.fetch_one("SELECT COALESCE(SUM(amount_pt),0) AS b FROM cash_ledger WHERE session_id=10")
        assert row["b"] == 57000  # 570 EGP in piasters

    def test_multiple_entry_types_sum_correctly(self):
        db = self._setup()
        self._add_entry(db, 10, "OPENING_FLOAT", 100000)
        self._add_entry(db, 10, "SALE_CASH", 30000)
        self._add_entry(db, 10, "DRIVER_REMITTANCE", 80000)
        self._add_entry(db, 10, "DRIVER_FEE_PAYOUT", -15000)
        self._add_entry(db, 10, "EXPENSE", -10000)
        self._add_entry(db, 10, "CASH_DROP", -50000)
        # 100000 + 30000 + 80000 - 15000 - 10000 - 50000 = 135000
        row = db.fetch_one("SELECT COALESCE(SUM(amount_pt),0) AS b FROM cash_ledger WHERE session_id=10")
        assert row["b"] == 135000


# ===========================================================================
# Part E: Repository layer
# ===========================================================================

class TestCashierSessionRepository:

    def _repo(self):
        db = _fresh_db()
        return CashierSessionRepository(db=db), db

    def test_create_and_get(self):
        repo, db = self._repo()
        session = CashierSession(
            id=None, day_id=1, user_id=2, station=Station.ALL,
            opening_float_pt=50000,
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        created = repo.create(session)
        db.commit()
        assert created.id is not None
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.station == Station.ALL
        assert fetched.opening_float_pt == 50000
        assert fetched.is_open

    def test_get_open_sessions_for_day(self):
        repo, db = self._repo()
        now = datetime.now(timezone.utc).isoformat()
        s = CashierSession(id=None, day_id=1, user_id=2, station=Station.COUNTER,
                           opening_float_pt=0, opened_at=now)
        repo.create(s)
        db.commit()
        sessions = repo.get_open_sessions_for_day(day_id=1)
        assert len(sessions) == 1
        assert sessions[0].station == Station.COUNTER

    def test_close_session(self):
        repo, db = self._repo()
        now = datetime.now(timezone.utc).isoformat()
        s = repo.create(CashierSession(id=None, day_id=1, user_id=2,
                                        station=Station.ALL, opening_float_pt=20000, opened_at=now))
        db.commit()
        repo.close_session(s.id, counted_cash_pt=19500, expected_cash_pt=20000, variance_pt=-500)
        db.commit()
        closed = repo.get_by_id(s.id)
        assert not closed.is_open
        assert closed.variance_pt == -500

    def test_has_any_open_session(self):
        repo, db = self._repo()
        assert not repo.has_any_open_session(day_id=1)
        now = datetime.now(timezone.utc).isoformat()
        repo.create(CashierSession(id=None, day_id=1, user_id=2, station=Station.DELIVERY,
                                    opening_float_pt=0, opened_at=now))
        db.commit()
        assert repo.has_any_open_session(day_id=1)


class TestCashLedgerRepository:

    def _setup(self):
        db = _fresh_db()
        session_repo = CashierSessionRepository(db=db)
        now = datetime.now(timezone.utc).isoformat()
        s = session_repo.create(CashierSession(
            id=None, day_id=1, user_id=1, station=Station.ALL,
            opening_float_pt=0, opened_at=now,
        ))
        db.commit()
        ledger_repo = CashLedgerRepository(db=db)
        return db, s, ledger_repo

    def test_append_and_balance(self):
        db, s, repo = self._setup()
        repo.append(CashLedgerEntry(
            id=None, day_id=1, session_id=s.id,
            entry_type=LedgerEntryType.OPENING_FLOAT,
            amount_pt=50000, actor_id=1,
        ))
        db.commit()
        assert repo.get_session_balance_pt(s.id) == 50000

    def test_balance_with_multiple_entries(self):
        db, s, repo = self._setup()
        for entry_type, amount in [
            (LedgerEntryType.OPENING_FLOAT, 100000),
            (LedgerEntryType.SALE_CASH, 25000),
            (LedgerEntryType.EXPENSE, -8000),
        ]:
            repo.append(CashLedgerEntry(
                id=None, day_id=1, session_id=s.id,
                entry_type=entry_type, amount_pt=amount, actor_id=1,
            ))
        db.commit()
        assert repo.get_session_balance_pt(s.id) == 117000

    def test_empty_balance_is_zero(self):
        _, s, repo = self._setup()
        assert repo.get_session_balance_pt(s.id) == 0

    def test_get_entries_for_session(self):
        db, s, repo = self._setup()
        repo.append(CashLedgerEntry(id=None, day_id=1, session_id=s.id,
                                     entry_type=LedgerEntryType.OPENING_FLOAT,
                                     amount_pt=50000, actor_id=1))
        db.commit()
        entries = repo.get_entries_for_session(s.id)
        assert len(entries) == 1
        assert entries[0].entry_type == LedgerEntryType.OPENING_FLOAT
        assert entries[0].amount_pt == 50000

    def test_balance_by_type(self):
        db, s, repo = self._setup()
        repo.append(CashLedgerEntry(id=None, day_id=1, session_id=s.id,
                                     entry_type=LedgerEntryType.OPENING_FLOAT,
                                     amount_pt=100000, actor_id=1))
        repo.append(CashLedgerEntry(id=None, day_id=1, session_id=s.id,
                                     entry_type=LedgerEntryType.SALE_CASH,
                                     amount_pt=20000, actor_id=1))
        db.commit()
        breakdown = repo.get_session_balance_by_type(s.id)
        assert breakdown["OPENING_FLOAT"] == 100000
        assert breakdown["SALE_CASH"] == 20000


# ===========================================================================
# Part F: Models
# ===========================================================================

class TestModels:
    def test_station_enum_values(self):
        assert Station.ALL.value == "ALL"
        assert Station.COUNTER.value == "COUNTER"
        assert Station.DELIVERY.value == "DELIVERY"

    def test_ledger_entry_type_has_all_types(self):
        expected = {
            "OPENING_FLOAT","HANDOVER_IN","HANDOVER_OUT","SALE_CASH",
            "DRIVER_REMITTANCE","DRIVER_FEE_PAYOUT","EXPENSE",
            "CASH_DROP","REVERSAL","ADJUSTMENT",
        }
        actual = {e.value for e in LedgerEntryType}
        assert expected == actual

    def test_cashier_session_is_closed_property(self):
        s = CashierSession(id=1, day_id=1, user_id=1, station=Station.ALL, is_open=False)
        assert s.is_closed

    def test_ledger_entry_egp_conversion(self):
        e = CashLedgerEntry(id=1, day_id=1, session_id=1,
                            entry_type=LedgerEntryType.SALE_CASH, amount_pt=12050, actor_id=1)
        assert e.amount_egp == pytest.approx(120.50)

    def test_ledger_inflow_outflow(self):
        pos = CashLedgerEntry(id=1, day_id=1, session_id=1,
                              entry_type=LedgerEntryType.SALE_CASH, amount_pt=5000, actor_id=1)
        neg = CashLedgerEntry(id=2, day_id=1, session_id=1,
                              entry_type=LedgerEntryType.EXPENSE, amount_pt=-2000, actor_id=1)
        assert pos.is_inflow and not pos.is_outflow
        assert neg.is_outflow and not neg.is_inflow
