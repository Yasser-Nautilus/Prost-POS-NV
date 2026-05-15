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
    2. Write a ``_migrate_vN_to_vN+1(db)`` function.
    3. Register it in ``_MIGRATIONS``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from broast_pos.data.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Version tracking
# ---------------------------------------------------------------------------
LATEST_VERSION = 1  # Bump this when adding migrations

# Ordered dict of (from_version → migration function).
# Each function signature: fn(db: DatabaseConnection) -> None
_MIGRATIONS: dict[int, callable] = {
    # Example for future use:
    # 1: _migrate_v1_to_v2,
}

# ---------------------------------------------------------------------------
# Path to the schema file (sibling of this module)
# ---------------------------------------------------------------------------
_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def initialise_database(db: "DatabaseConnection") -> None:
    """Create tables (if missing) and run any pending migrations.

    Call this once at application startup, right after obtaining the
    ``DatabaseConnection`` singleton.

    Parameters
    ----------
    db : DatabaseConnection
        The singleton database connection.
    """
    _apply_schema(db)
    _ensure_version_row(db)
    _run_pending_migrations(db)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _apply_schema(db: "DatabaseConnection") -> None:
    """Execute ``schema.sql`` to create all tables and indexes.

    Every statement uses ``IF NOT EXISTS``, so this is safe to re-run.
    """
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    db.executescript(schema_sql)
    logger.info("Schema applied from %s", _SCHEMA_PATH.name)


def _ensure_version_row(db: "DatabaseConnection") -> None:
    """Guarantee that ``schema_version`` has exactly one row."""
    row = db.fetch_one("SELECT version FROM schema_version LIMIT 1")
    if row is None:
        db.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (LATEST_VERSION,),
        )
        db.commit()
        logger.info("Initialised schema_version to v%d (fresh install)", LATEST_VERSION)


def _get_current_version(db: "DatabaseConnection") -> int:
    """Return the current schema version number."""
    row = db.fetch_one("SELECT version FROM schema_version LIMIT 1")
    return row["version"]


def _set_version(db: "DatabaseConnection", version: int) -> None:
    """Update the stored schema version."""
    db.execute("UPDATE schema_version SET version = ?, applied_at = datetime('now')", (version,))
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
            # No migration registered — just bump the version.
            # This happens on v1 (initial schema, nothing to migrate).
            continue

        target = from_version + 1
        logger.info("  Applying migration v%d → v%d …", from_version, target)
        try:
            migration_fn(db)
            logger.info("  ✓ Migration v%d → v%d complete", from_version, target)
        except Exception:
            logger.exception(
                "  ✗ Migration v%d → v%d FAILED — rolling back",
                from_version,
                target,
            )
            db.rollback()
            raise

    _set_version(db, LATEST_VERSION)
    logger.info("Schema migrated successfully to v%d", LATEST_VERSION)


# ============================================================================
# Migration functions — add new ones here as the schema evolves
# ============================================================================

# def _migrate_v1_to_v2(db: "DatabaseConnection") -> None:
#     """Example: add a new column to an existing table."""
#     db.execute("ALTER TABLE orders ADD COLUMN tip_amount REAL NOT NULL DEFAULT 0")
#     db.commit()
