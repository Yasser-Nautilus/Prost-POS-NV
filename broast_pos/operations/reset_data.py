"""Reset a POS database to a fresh-install state, keeping the setup data.

Usage (stop the POS app first):
    python -m broast_pos.operations.reset_data [--db PATH] [--yes]

Kept: the admin user, categories, products, delivery zones, schema version.
Wiped: orders, shifts and sessions, cash ledger, expenses, reports data,
audit log (history), customers, delivery trips, driver data and every user
except the admin (drivers included).

A validated backup is written next to the database before anything is
deleted. If the backup fails, nothing is changed.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from broast_pos.operations.recovery import backup

KEEP_TABLES = {"schema_version", "users", "categories", "products", "zones"}


def _data_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows if r[0] not in KEEP_TABLES]


def reset(db_path: str | Path, backup_path: str | Path | None = None) -> dict[str, int]:
    """Back up then wipe. Returns {table: rows deleted}."""
    db_path = Path(db_path).expanduser().resolve(strict=True)
    if backup_path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = db_path.with_name(f"{db_path.stem}-before-reset-{stamp}.db")
    backup(db_path, backup_path)

    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    deleted: dict[str, int] = {}
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        tables = _data_tables(conn)
        # Append-only triggers (cash ledger) would block the delete: drop them
        # inside the transaction and recreate them before it commits.
        triggers = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN (%s)"
            % ",".join("?" * len(tables)),
            tables,
        ).fetchall() if tables else []
        conn.execute("BEGIN IMMEDIATE")
        try:
            for name, _sql in triggers:
                conn.execute(f'DROP TRIGGER IF EXISTS "{name}"')
            for table in tables:
                deleted[table] = conn.execute(f'DELETE FROM "{table}"').rowcount
            deleted["users"] = conn.execute(
                "DELETE FROM users WHERE role != 'admin'"
            ).rowcount
            if tables:
                conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN (%s)" % ",".join("?" * len(tables)),
                    tables,
                )
            for _name, sql in triggers:
                conn.execute(sql)
            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.IntegrityError("foreign key check failed after reset")
            if conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] < 1:
                raise sqlite3.IntegrityError("no admin user would remain")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("VACUUM")
    finally:
        conn.close()
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="database file (default: the app database)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation question")
    args = parser.parse_args()

    from broast_pos.config import config

    db_path = Path(args.db or config.DATABASE_PATH).expanduser()
    if not db_path.is_file():
        parser.exit(1, f"Database not found: {db_path}\n")
    print(f"Database: {db_path}")
    print("This deletes ALL orders, shifts, expenses, reports, history, customers,")
    print("drivers and users except the admin. Menu, categories and zones are kept.")
    print("Close the POS app before continuing. A backup is made first.")
    if not args.yes and input("Type RESET to continue: ").strip() != "RESET":
        print("Cancelled. Nothing changed.")
        return 1
    try:
        result = reset(db_path)
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f"Reset failed, database unchanged: {exc}\n")
    print("Done. Rows deleted:")
    for table, count in sorted(result.items()):
        if count:
            print(f"  {table}: {count}")
    backups = sorted(db_path.parent.glob(f"{db_path.stem}-before-reset-*.db"))
    if backups:
        print(f"Backup: {backups[-1]}")
        print("To undo: stop the app and restore that file over the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
