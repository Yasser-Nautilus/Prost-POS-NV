"""Consistent SQLite backup and restore-to-new-file recovery.

Usage: python -m broast_pos.operations.recovery backup|restore --source PATH --destination NEW_PATH
No command overwrites a destination. Switch an installation only after stopping
it and reviewing the restored copy, following docs/backup-recovery.md.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from broast_pos.data.database.migrations import LATEST_VERSION, initialise_database

_REQUIRED = {"users", "orders", "order_items", "shifts", "audit_log"}


def _validate(connection: sqlite3.Connection) -> int:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Database contains broken foreign key references")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not _REQUIRED.issubset(tables) or "schema_version" not in tables:
        raise ValueError("Not a versioned POS database")
    versions = connection.execute("SELECT version FROM schema_version").fetchall()
    if len(versions) != 1 or type(versions[0][0]) is not int:
        raise ValueError("Invalid POS schema version")
    version = versions[0][0]
    if not 1 <= version <= LATEST_VERSION:
        raise ValueError("Database version is unsupported by this application")
    return version


def _clone(source: str | Path, destination: str | Path, *, upgrade: bool) -> Path:
    source = Path(source).expanduser().resolve(strict=True)
    destination = Path(destination).expanduser().absolute()
    if not source.is_file():
        raise ValueError("Source must be an existing database file")
    if source == destination.resolve():
        raise ValueError("Source and destination must be different")
    # O_EXCL rejects existing files, directories, hardlinks and symlinks, even
    # when another process creates the target after an earlier existence check.
    source_db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
    owned = False
    try:
        _validate(source_db)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        owned = True
        target_db = sqlite3.connect(destination)
        try:
            # SQLite's backup API includes committed WAL data. A raw .db copy
            # could silently omit it while the POS is running.
            source_db.backup(target_db)
            _validate(target_db)
        finally:
            target_db.close()
        if upgrade:
            from broast_pos.data.database.connection import DatabaseConnection
            restored = DatabaseConnection(str(destination))
            try:
                initialise_database(restored)
            finally:
                restored.close()
            check = sqlite3.connect(destination)
            try:
                _validate(check)
            finally:
                check.close()
        with destination.open("rb") as handle:
            os.fsync(handle.fileno())
        return destination
    except BaseException:
        if owned:
            destination.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(str(destination) + suffix).unlink(missing_ok=True)
        raise
    finally:
        source_db.close()


def backup(source: str | Path, destination: str | Path) -> Path:
    """Create a validated consistent snapshot at a new explicit local path."""
    return _clone(source, destination, upgrade=False)


def restore(source: str | Path, destination: str | Path) -> Path:
    """Restore and migrate a new disposable candidate, never replace live data."""
    return _clone(source, destination, upgrade=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        result = (backup if args.operation == "backup" else restore)(args.source, args.destination)
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Recovery operation failed: {exc}\n")
    print(f"Validated {args.operation} created: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
