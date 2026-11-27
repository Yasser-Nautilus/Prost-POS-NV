"""
Database connection manager — singleton SQLite connection with WAL mode.

This module provides the single point of entry for all database operations.
Repositories use this connection; they never create their own.

Design decisions:
- Singleton: one connection shared across the entire application lifetime.
- WAL mode: enables concurrent reads while a write is in progress — critical
  for two cashier slots running on the same PC.
- check_same_thread=False: required because Qt signals may trigger DB calls
  from threads other than the one that created the connection.
- Foreign keys ON: SQLite disables FK enforcement by default; we force it.
- Row factory = sqlite3.Row: gives dict-like access (row["column_name"])
  without the overhead of a full ORM.
"""

import logging
import os
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from broast_pos.core.clock import configure_process_timezone

# Item 4 (batch 6): every entry point reaches the database layer, so pinning the
# timezone here makes all stored times Cairo time, not the host's timezone.
configure_process_timezone()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default database location (matches config/PROGRESS.md → Paths & Files)
# ---------------------------------------------------------------------------
_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent  # broast_pos/data/
_DEFAULT_DB_PATH = str(_DEFAULT_DB_DIR / "broast_pos.db")


class DatabaseConnection:
    """Thread-safe singleton wrapper around a single sqlite3.Connection.

    Usage::

        db = DatabaseConnection.get_instance()
        user = db.fetch_one("SELECT * FROM users WHERE id = ?", (1,))
    """

    _instance: Optional["DatabaseConnection"] = None
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls, db_path: str | None = None) -> "DatabaseConnection":
        """Return the singleton instance, creating it on first call.

        Parameters
        ----------
        db_path : str, optional
            Override the default database file path.  Only honoured on the
            **first** call (when the singleton is created).  Subsequent calls
            ignore this parameter and return the existing instance.
        """
        if cls._instance is None:
            with cls._lock:
                # Double-checked locking
                if cls._instance is None:
                    cls._instance = cls(db_path or _DEFAULT_DB_PATH)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton — used only in tests."""
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance._conn.close()
                except Exception:  # Checkup-Fix: cleanup error – log, don't hide
                    logger.debug("Closing DB connection during reset failed", exc_info=True)
                cls._instance = None

    # ------------------------------------------------------------------
    # Construction (private — use get_instance())
    # ------------------------------------------------------------------
    def __init__(self, db_path: str) -> None:
        if DatabaseConnection._instance is not None:
            raise RuntimeError(
                "DatabaseConnection is a singleton — use get_instance()"
            )

        self._operation_lock = threading.RLock()
        self._savepoint_serial = 0
        self._db_path = db_path
        self._ensure_directory()
        self._conn = self._create_connection()

    # ------------------------------------------------------------------
    # Connection setup
    # ------------------------------------------------------------------
    def _ensure_directory(self) -> None:
        """Create the parent directory for the database file if missing."""
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)

    def _create_connection(self) -> sqlite3.Connection:
        """Open the SQLite connection with production-safe pragmas."""
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

        # --- Pragmas (order matters) ---
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        # Fsync only at critical moments — good balance of speed vs safety
        conn.execute("PRAGMA synchronous = NORMAL;")
        # 2 MB page cache — keeps hot pages in memory
        conn.execute("PRAGMA cache_size = -2000;")
        # B-06: wait up to 5 seconds before raising OperationalError on a
        # locked database (concurrent writes in WAL mode).
        conn.execute("PRAGMA busy_timeout = 5000;")

        self._tx_depth: int = 0  # nesting counter for transaction()
        return conn

    # ------------------------------------------------------------------
    # Core query methods
    # ------------------------------------------------------------------
    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> sqlite3.Cursor:
        """Execute a single SQL statement and return the cursor.

        Suitable for INSERT / UPDATE / DELETE as well as DDL.  For writes
        that should be grouped, wrap with ``begin()`` … ``commit()``.
        """
        with self._operation_lock:
            return self._conn.execute(sql, params)

    def fetch_one(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> sqlite3.Row | None:
        """Execute *sql* and return the first row, or ``None``."""
        with self._operation_lock:
            return self._conn.execute(sql, params).fetchone()

    def fetch_all(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] = (),
    ) -> list[sqlite3.Row]:
        """Execute *sql* and return every matching row."""
        with self._operation_lock:
            return self._conn.execute(sql, params).fetchall()

    def executescript(self, script: str) -> None:
        """Run a multi-statement SQL script (e.g. schema creation).

        ``executescript`` implicitly issues a ``COMMIT`` before running,
        so any open transaction is committed first.
        """
        with self._operation_lock:
            if self._tx_depth:
                raise RuntimeError("executescript cannot run inside a managed transaction")
            self._conn.executescript(script)

    # ------------------------------------------------------------------
    # Transaction helpers
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Atomic operation, with real SQLite savepoints for nested scopes.

        A failed inner scope rolls back its writes even if its caller catches
        the error. Repository commit() calls cannot commit the outer scope.
        Hold a reentrant lock for the entire scope: another thread must never
        join this shared connection's transaction or commit its partial work.
        """
        with self._operation_lock:
            outermost = self._tx_depth == 0
            savepoint = None
            if outermost:
                if not self._conn.in_transaction:
                    self._conn.execute("BEGIN IMMEDIATE")
            else:
                self._savepoint_serial += 1
                savepoint = f"managed_{self._savepoint_serial}"
                self._conn.execute(f"SAVEPOINT {savepoint}")
            self._tx_depth += 1
            try:
                yield
                if outermost:
                    self._conn.commit()
                else:
                    self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            except BaseException:
                try:
                    if outermost:
                        self._conn.rollback()
                    else:
                        self._conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                        self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                except Exception:
                    logger.exception("Transaction rollback failed")
                    raise
                raise
            finally:
                self._tx_depth -= 1

    def begin(self) -> None:
        """Start an explicit transaction (DEFERRED by default in SQLite).

        Prefer ``transaction()`` context manager for new code.
        """
        with self._operation_lock:
            self._conn.execute("BEGIN")

    def commit(self) -> None:
        """Commit the current transaction.

        If called from inside a ``transaction()`` block this is a **no-op**
        so repository methods do not accidentally flush partial work.
        """
        with self._operation_lock:
            if self._tx_depth == 0:
                self._conn.commit()

    def rollback(self) -> None:
        """Roll back a legacy transaction; managed scopes own their rollback."""
        with self._operation_lock:
            if self._tx_depth:
                raise RuntimeError("Raise an exception to roll back a managed transaction")
            self._conn.rollback()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    @property
    def path(self) -> str:
        """Return the filesystem path of the database file."""
        return self._db_path

    @property
    def raw_connection(self) -> sqlite3.Connection:
        """Escape hatch — direct access to the underlying ``sqlite3.Connection``.

        Prefer the methods above.  This exists only for edge-cases like
        attaching another database or running VACUUM.
        """
        return self._conn

    def close(self) -> None:
        """Close the underlying connection.  Normally only called at app exit."""
        self._conn.close()

    def __repr__(self) -> str:
        return f"<DatabaseConnection path={self._db_path!r}>"
