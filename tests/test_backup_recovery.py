"""Recovery drills use disposable databases only, never an installation's data."""
from __future__ import annotations

import hashlib
import sqlite3
from unittest.mock import patch

import pytest

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import LATEST_VERSION, initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.operations.recovery import backup, restore


@pytest.fixture
def source(tmp_path):
    DatabaseConnection.reset()
    path = tmp_path / "source.db"
    db = DatabaseConnection(str(path))
    initialise_database(db)
    seed_database(db)
    db.execute("INSERT INTO shifts(id,opened_by,business_date) VALUES(1,1,'2026-11-22')")
    db.execute("INSERT INTO parked_order_drafts(user_id,payload) VALUES(1,'{\"test\":true}')")
    db.execute("INSERT INTO orders(id,invoice_no,shift_id,order_type,status,total,created_by_id,created_by_name,cashier_slot) VALUES(1,1,1,'takeaway','completed',70,1,'Admin',1)")
    db.execute("INSERT INTO order_items(order_id,product_id,product_name,quantity,unit_price,total_price) VALUES(1,1,'Item',1,70,70)")
    db.execute("INSERT INTO cashier_sessions(id,day_id,user_id,station,opened_at) VALUES(1,1,1,'COUNTER','2026-11-22 10:00:00')")
    db.execute("INSERT INTO cash_ledger(day_id,session_id,entry_type,amount_pt,order_id,actor_id,created_at) VALUES(1,1,'SALE_CASH',7000,1,1,'2026-11-22 10:01:00')")
    db.execute("INSERT INTO audit_log(event_type,user_id,user_name,details) VALUES('test',NULL,'Unknown','{}')")
    db.commit()
    yield path, db
    db.close()
    DatabaseConnection.reset()


def test_backup_includes_committed_wal_and_not_uncommitted_changes(source, tmp_path):
    path, db = source
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("INSERT INTO customers(name,phone) VALUES('WAL customer','01012345678')")
    db.commit()
    assert path.with_name(path.name + "-wal").stat().st_size > 0
    target = backup(path, tmp_path / "backup.db")
    check = sqlite3.connect(target)
    assert check.execute("SELECT name FROM customers").fetchone()[0] == "WAL customer"
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()
    db.execute("INSERT INTO customers(name,phone) VALUES('Uncommitted','01012345679')")
    second = backup(path, tmp_path / "second.db")
    check = sqlite3.connect(second)
    assert check.execute("SELECT count(*) FROM customers").fetchone()[0] == 1
    check.close()
    db.rollback()


def test_restore_copy_preserves_rows_and_source_and_can_be_reopened(source, tmp_path):
    path, db = source
    snapshot = backup(path, tmp_path / "backup.db")
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    target = restore(snapshot, tmp_path / "restored.db")
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
    check = sqlite3.connect(target)
    assert check.execute("SELECT count(*) FROM users").fetchone()[0] == db.fetch_one("SELECT count(*) n FROM users")["n"]
    assert check.execute("SELECT count(*) FROM parked_order_drafts").fetchone()[0] == 1
    assert check.execute("SELECT sum(amount_pt) FROM cash_ledger").fetchone()[0] == 7000
    assert check.execute("SELECT total FROM orders").fetchone()[0] == 70
    assert check.execute("SELECT quantity FROM order_items").fetchone()[0] == 1
    assert check.execute("SELECT user_id FROM audit_log WHERE event_type='test'").fetchone()[0] is None
    assert check.execute("SELECT business_date FROM shifts").fetchone()[0] == "2026-11-22"
    assert check.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_VERSION
    assert check.execute("PRAGMA foreign_key_check").fetchall() == []
    check.close()
    candidate = DatabaseConnection(str(target))
    initialise_database(candidate)
    candidate.close()


@pytest.mark.parametrize("operation", [backup, restore])
def test_never_overwrites_existing_destination_or_source(source, tmp_path, operation):
    path, _ = source
    with pytest.raises(ValueError):
        operation(path, path)
    existing = tmp_path / "live.db"
    existing.write_bytes(b"preserve existing destination")
    with pytest.raises(FileExistsError):
        operation(path, existing)
    assert existing.read_bytes() == b"preserve existing destination"
    link = tmp_path / "link.db"
    link.symlink_to(existing)
    with pytest.raises(FileExistsError):
        operation(path, link)
    assert existing.read_bytes() == b"preserve existing destination"


@pytest.mark.parametrize("kind", ["corrupt", "unrelated", "future", "broken_fk"])
def test_invalid_backup_cannot_be_restored(source, tmp_path, kind):
    path, db = source
    suspect = tmp_path / "suspect.db"
    if kind == "corrupt":
        suspect.write_bytes(b"not sqlite")
    elif kind == "unrelated":
        sqlite3.connect(suspect).close()
    else:
        backup(path, suspect)
        conn = sqlite3.connect(suspect)
        if kind == "future":
            conn.execute("UPDATE schema_version SET version=?", (LATEST_VERSION + 1,))
        else:
            conn.execute("INSERT INTO shifts(opened_by) VALUES(99999)")
        conn.commit()
        conn.close()
    target = tmp_path / "candidate.db"
    with pytest.raises((sqlite3.Error, ValueError)):
        restore(suspect, target)
    assert not target.exists()
    assert db.fetch_one("SELECT count(*) n FROM shifts")["n"] == 1


def test_migration_failure_cleans_only_new_candidate(source, tmp_path):
    path, _ = source
    target = tmp_path / "candidate.db"
    with patch("broast_pos.operations.recovery.initialise_database", side_effect=RuntimeError("migration failed")):
        with pytest.raises(RuntimeError):
            restore(path, target)
    assert not target.exists()
    assert path.exists()


def test_older_copy_upgrade_does_not_change_original(source, tmp_path):
    path, db = source
    db.execute("UPDATE schema_version SET version=11")
    db.execute("UPDATE shifts SET business_date=NULL,opened_at='2026-03-10 23:30:00'")
    db.commit()
    target = restore(path, tmp_path / "candidate.db")
    check = sqlite3.connect(target)
    assert check.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_VERSION
    assert check.execute("SELECT business_date FROM shifts").fetchone()[0] == "2026-03-10"
    check.close()
    assert db.fetch_one("SELECT version FROM schema_version")["version"] == 11
    assert db.fetch_one("SELECT business_date FROM shifts")["business_date"] is None


def test_operator_cli_backup_and_restore_on_disposable_copy(source, tmp_path):
    import subprocess
    import sys
    path, _ = source
    snapshot, candidate = tmp_path / "cli-backup.db", tmp_path / "cli-candidate.db"
    for operation, src, dest in [("backup", path, snapshot), ("restore", snapshot, candidate)]:
        result = subprocess.run([sys.executable, "-m", "broast_pos.operations.recovery", operation,
                                 "--source", str(src), "--destination", str(dest)],
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert f"Validated {operation} created" in result.stdout
    check = sqlite3.connect(candidate)
    assert check.execute("SELECT sum(amount_pt) FROM cash_ledger").fetchone()[0] == 7000
    check.close()
    refusal = subprocess.run([sys.executable, "-m", "broast_pos.operations.recovery", "restore",
                              "--source", str(snapshot), "--destination", str(path)],
                             capture_output=True, text=True, timeout=20)
    assert refusal.returncode != 0
    assert "Recovery operation failed" in refusal.stderr
