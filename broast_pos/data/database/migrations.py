"""
Schema migration system — version-tracked, forward-only migrations.

Runs automatically at app startup via ``initialise_database()``.  Each
migration is a plain function (``_migrate_v1_to_v2``, etc.) that receives
the database connection and applies ``ALTER TABLE`` / ``CREATE INDEX``
statements.  Data is never dropped.

Flow:
    1. Read ``schema.sql`` and execute it (idempotent — all CREATE IF NOT EXISTS).
    2. Ensure ``schema_version`` table exists and has a row.
    3. Check current version against ``LATEST_VERSION``.
    4. Apply each pending migration in order.
    5. Update ``schema_version`` to the new version.

Adding a new migration:
    1. Increment ``LATEST_VERSION``.
    2. Write a ``_migrate_vN_to_vN+1(db)`` function below.
    3. Register it in ``_MIGRATIONS`` (at the BOTTOM of the file).

Migration history:
    v1 → v2: Add order_status_history table + indexes.
    v2 → v3: Extend audit_log with entity_type, entity_id, action, reason, before_data, after_data.
    v3 → v4: Add driver_settlements table + index.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from broast_pos.data.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version tracking (bumped when a new migration is added)
# ---------------------------------------------------------------------------
LATEST_VERSION = 5

# ---------------------------------------------------------------------------
# Path to the schema file (sibling of this module)
# ---------------------------------------------------------------------------
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def initialise_database(db: "DatabaseConnection") -> None:
    """Create tables (if missing) and run any pending migrations.

    Call once at application startup, right after obtaining the singleton.
    """
    _apply_schema(db)
    _ensure_version_row(db)
    _run_pending_migrations(db)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _apply_schema(db: "DatabaseConnection") -> None:
    """Execute schema.sql to create all tables and indexes (idempotent)."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    db.executescript(schema_sql)
    logger.info("Schema applied from %s", _SCHEMA_PATH.name)


def _ensure_version_row(db: "DatabaseConnection") -> None:
    """Guarantee that schema_version has exactly one row."""
    row = db.fetch_one("SELECT version FROM schema_version LIMIT 1")
    if row is None:
        db.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (LATEST_VERSION,),
        )
        db.commit()
        logger.info("Initialised schema_version to v%d (fresh install)", LATEST_VERSION)


def _get_current_version(db: "DatabaseConnection") -> int:
    row = db.fetch_one("SELECT version FROM schema_version LIMIT 1")
    return row["version"]


def _set_version(db: "DatabaseConnection", version: int) -> None:
    db.execute(
        "UPDATE schema_version SET version = ?, applied_at = datetime('now')",
        (version,),
    )
    db.commit()


def _run_pending_migrations(db: "DatabaseConnection") -> None:
    """Apply every migration between the current version and LATEST_VERSION."""
    current = _get_current_version(db)

    if current >= LATEST_VERSION:
        logger.debug("Schema is up-to-date at v%d", current)
        return

    logger.info("Schema at v%d — migrating to v%d …", current, LATEST_VERSION)

    for from_version in range(current, LATEST_VERSION):
        migration_fn = _MIGRATIONS.get(from_version)
        if migration_fn is None:
            # No migration registered for this step — skip (e.g. initial install)
            continue

        target = from_version + 1
        logger.info("  Applying migration v%d → v%d …", from_version, target)
        try:
            migration_fn(db)
            logger.info("  ✓ Migration v%d → v%d complete", from_version, target)
        except Exception:
            logger.exception(
                "  ✗ Migration v%d → v%d FAILED — rolling back", from_version, target,
            )
            db.rollback()
            raise

    _set_version(db, LATEST_VERSION)
    logger.info("Schema migrated successfully to v%d", LATEST_VERSION)


# ============================================================================
# Migration functions (defined BEFORE _MIGRATIONS dict)
# ============================================================================

def _migrate_v1_to_v2(db: "DatabaseConnection") -> None:
    """v1 → v2: Add order_status_history table and its indexes."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS order_status_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id         INTEGER NOT NULL REFERENCES orders(id),
            old_status       TEXT,
            new_status       TEXT    NOT NULL,
            changed_by_id    INTEGER,
            changed_by_name  TEXT,
            reason           TEXT,
            changed_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_order_status_history_order
        ON order_status_history(order_id)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_order_status_history_changed_at
        ON order_status_history(changed_at)
    """)
    db.commit()


def _migrate_v2_to_v3(db: "DatabaseConnection") -> None:
    """v2 → v3: Extend audit_log with entity and before/after fields.

    All new columns are nullable — existing rows stay valid.
    """
    new_columns = [
        ("entity_type", "TEXT"),
        ("entity_id",   "INTEGER"),
        ("action",      "TEXT"),
        ("reason",      "TEXT"),
        ("before_data", "TEXT"),
        ("after_data",  "TEXT"),
    ]
    for col_name, col_type in new_columns:
        try:
            db.execute(
                f"ALTER TABLE audit_log ADD COLUMN {col_name} {col_type}"
            )
        except Exception as exc:
            if "duplicate column name" in str(exc).lower():
                logger.debug("audit_log.%s already exists — skipping", col_name)
            else:
                raise
    db.commit()


def _migrate_v3_to_v4(db: "DatabaseConnection") -> None:
    """v3 → v4: Add driver_settlements table and index."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS driver_settlements (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id           INTEGER NOT NULL,
            driver_name         TEXT    NOT NULL,
            settlement_date     TEXT    NOT NULL,
            trip_count          INTEGER NOT NULL DEFAULT 0,
            order_count         INTEGER NOT NULL DEFAULT 0,
            total_order_value   REAL    NOT NULL DEFAULT 0,
            cash_collected      REAL    NOT NULL DEFAULT 0,
            online_paid         REAL    NOT NULL DEFAULT 0,
            total_delivery_fees REAL    NOT NULL DEFAULT 0,
            settled_by_id       INTEGER NOT NULL,
            settled_by_name     TEXT    NOT NULL,
            notes               TEXT,
            settled_at          TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_driver_settlements_driver_date
        ON driver_settlements(driver_id, settlement_date)
    """)
    db.commit()


def _migrate_v4_to_v5(db: "DatabaseConnection") -> None:
    """v4 → v5: Add cashier_sessions + cash_ledger tables (Phase 1 of v2)."""

    # ── 1. Extend shifts table with business-date + close metadata ────
    # SQLite does not support ADD COLUMN IF NOT EXISTS, so we check first.
    existing_cols = {row["name"] for row in db.fetch_all("PRAGMA table_info(shifts)")}

    for col_def in (
        ("business_date",     "TEXT"),
        ("opened_float_note", "TEXT"),
        ("closed_reason",     "TEXT"),
    ):
        col_name, col_type = col_def
        if col_name not in existing_cols:
            db.execute(f"ALTER TABLE shifts ADD COLUMN {col_name} {col_type}")

    # Back-fill business_date for all existing rows
    db.execute(
        "UPDATE shifts SET business_date = date(opened_at, 'localtime') WHERE business_date IS NULL"
    )

    # ── 2. cashier_sessions ───────────────────────────────────────────
    db.execute("""
        CREATE TABLE IF NOT EXISTS cashier_sessions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id                INTEGER NOT NULL REFERENCES shifts(id),
            user_id               INTEGER NOT NULL REFERENCES users(id),
            station               TEXT    NOT NULL
                                    CHECK (station IN ('ALL','COUNTER','DELIVERY')),
            is_open               INTEGER NOT NULL DEFAULT 1
                                    CHECK (is_open IN (0, 1)),
            opened_at             TEXT    NOT NULL,
            closed_at             TEXT,
            opening_float_pt      INTEGER NOT NULL DEFAULT 0
                                    CHECK (opening_float_pt >= 0),
            counted_cash_pt       INTEGER,
            expected_cash_pt      INTEGER,
            variance_pt           INTEGER,
            variance_approved_by  INTEGER REFERENCES users(id),
            variance_reason       TEXT,
            handover_to_session   INTEGER REFERENCES cashier_sessions(id)
        )
    """)

    # At most one open session per station per day
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_open_station
        ON cashier_sessions(day_id, station) WHERE is_open = 1
    """)

    # ALL station cannot coexist with COUNTER or DELIVERY (and vice-versa)
    # Checked here at the service layer with a clear Arabic message;
    # the trigger is a second line of defence.
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_station_exclusive
        BEFORE INSERT ON cashier_sessions
        WHEN NEW.is_open = 1
          AND EXISTS (
              SELECT 1 FROM cashier_sessions s
              WHERE s.day_id = NEW.day_id
                AND s.is_open = 1
                AND (
                    NEW.station = 'ALL'
                    OR s.station = 'ALL'
                )
          )
        BEGIN
            SELECT RAISE(ABORT, 'station_conflict:لا يمكن فتح وردية الكل مع وردية تخصص في نفس اليوم');
        END
    """)

    # ── 3. cash_ledger ────────────────────────────────────────────────
    db.execute("""
        CREATE TABLE IF NOT EXISTS cash_ledger (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id            INTEGER NOT NULL REFERENCES shifts(id),
            session_id        INTEGER NOT NULL REFERENCES cashier_sessions(id),
            entry_type        TEXT NOT NULL CHECK (entry_type IN (
                'OPENING_FLOAT','HANDOVER_IN','HANDOVER_OUT','SALE_CASH',
                'DRIVER_REMITTANCE','DRIVER_FEE_PAYOUT','EXPENSE',
                'CASH_DROP','REVERSAL','ADJUSTMENT'
            )),
            amount_pt         INTEGER NOT NULL,
            order_id          INTEGER REFERENCES orders(id),
            trip_id           INTEGER REFERENCES delivery_trips(id),
            expense_id        INTEGER,
            reverses_entry_id INTEGER REFERENCES cash_ledger(id),
            actor_id          INTEGER NOT NULL REFERENCES users(id),
            approved_by       INTEGER REFERENCES users(id),
            reason            TEXT,
            created_at        TEXT NOT NULL
        )
    """)

    # Indexes for performance
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_session
        ON cash_ledger(session_id)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_day
        ON cash_ledger(day_id)
    """)

    # Append-only enforcement: no UPDATE or DELETE ever
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS cash_ledger_no_update
        BEFORE UPDATE ON cash_ledger
        BEGIN SELECT RAISE(ABORT, 'cash_ledger is append-only'); END
    """)
    db.execute("""
        CREATE TRIGGER IF NOT EXISTS cash_ledger_no_delete
        BEFORE DELETE ON cash_ledger
        BEGIN SELECT RAISE(ABORT, 'cash_ledger is append-only'); END
    """)

    # Idempotency: one SALE_CASH per order, one DRIVER_REMITTANCE per trip
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_sale
        ON cash_ledger(order_id) WHERE entry_type = 'SALE_CASH'
    """)
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_remit
        ON cash_ledger(trip_id) WHERE entry_type = 'DRIVER_REMITTANCE'
    """)

    db.commit()


# ---------------------------------------------------------------------------
# Migration registry — maps from_version → migration function
# NOTE: Must be defined AFTER all migration functions are declared.
# ---------------------------------------------------------------------------
_MIGRATIONS: dict = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}
