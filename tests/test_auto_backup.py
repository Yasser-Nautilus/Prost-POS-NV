# ruff: noqa: F811
"""Daily automatic backup at day close."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from test_e2e_user_flows import qapp, reset_db_singleton  # noqa: F401

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.operations.auto_backup import BACKUP_DIR_NAME, run_day_close_backup


def _make_db(tmp_path):
    path = tmp_path / "live.db"
    db = DatabaseConnection(str(path))
    initialise_database(db)
    db.commit()
    return path, db


def test_backup_is_created_valid_and_pruned(tmp_path):
    path, db = _make_db(tmp_path)
    base = datetime(2026, 11, 1, 23, 0, 0)
    made = [run_day_close_backup(path, keep=3, now=base + timedelta(days=i)) for i in range(5)]
    assert all(p is not None for p in made)
    folder = tmp_path / BACKUP_DIR_NAME
    kept = sorted(p.name for p in folder.glob("*.db"))
    assert len(kept) == 3
    assert kept[-1] == made[-1].name
    check = sqlite3.connect(made[-1])
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()
    db.close()


def test_backup_failure_never_raises(tmp_path):
    assert run_day_close_backup(":memory:") is None
    assert run_day_close_backup(tmp_path / "missing.db") is None
    path, db = _make_db(tmp_path)
    blocker = tmp_path / BACKUP_DIR_NAME
    blocker.write_text("a file where the folder should be")
    assert run_day_close_backup(path) is None
    db.close()


def _close_day(c):
    r = c.call("session.close", {"session_id": c.session_id, "counted_cash_egp": 500.0,
                                 "manager_pin": "1234", "variance_reason": "test"})
    assert r["success"], r
    c.call("logout")
    c.call("login", {"pin": "1234"})
    assert c.call("print_shift_summary")["success"]
    return c.call("close_shift")


def test_closing_the_day_triggers_the_backup(qapp, monkeypatch):
    from test_batch_workflow_e2e import _setup
    calls = []
    import broast_pos.operations.auto_backup as ab
    monkeypatch.setattr(ab, "run_day_close_backup", lambda path: calls.append(path))
    c, db, shift, _ = _setup(qapp)
    assert _close_day(c)["success"]
    assert len(calls) == 1


def test_a_failing_backup_does_not_block_day_close(qapp, monkeypatch):
    from test_batch_workflow_e2e import _setup

    import broast_pos.operations.auto_backup as ab

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(ab, "backup", boom)
    c, db, shift, _ = _setup(qapp)
    # in-memory DB has no file, so force a path to reach the failing backup
    monkeypatch.setattr(type(db), "path", property(lambda self: __file__))
    assert _close_day(c)["success"]
    assert db.fetch_one("SELECT is_active FROM shifts WHERE id=?", (shift,))["is_active"] == 0
