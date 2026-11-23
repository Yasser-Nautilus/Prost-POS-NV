"""Production authentication auditing uses unknown actors, never invented users."""
from __future__ import annotations

import importlib
import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.core.models.user import UserRole
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.audit_repository import AuditRepository


@pytest.fixture
def env():
    app = QCoreApplication.instance() or QCoreApplication(["auth-audit-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)
    def call(action, payload=None, ok=True):
        result = json.loads(bridge.dispatch(action, json.dumps(payload or {})))
        assert result["success"] is ok, result
        return result.get("data")
    yield bridge, db, call
    DatabaseConnection.reset()


def test_production_main_wires_auth_audit_before_ui(env, monkeypatch):
    _, db, _ = env
    main = importlib.import_module("broast_pos.main")
    captured = []
    class ObservedAuth(AuthService):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured.append(self)
    class StopAtUI(Exception):
        pass
    application = MagicMock(side_effect=StopAtUI)
    monkeypatch.setattr(main, "AuthService", ObservedAuth)
    monkeypatch.setattr(main, "QApplication", application)
    monkeypatch.setattr(main, "_setup_logging", lambda: None)
    monkeypatch.setattr(main.config, "validate_production_secrets", lambda: None)
    monkeypatch.setattr(main, "validate_no_default_admin", lambda db: None)
    with pytest.raises(StopAtUI):
        main.main()
    assert len(captured) == 1 and captured[0]._audit is not None
    with pytest.raises(ValueError):
        captured[0].login_by_pin("bad-secret")
    assert db.fetch_one("SELECT user_id FROM audit_log WHERE event_type='login_failed'")["user_id"] is None


@pytest.mark.parametrize("kind", ["pin_only", "missing_id", "known_id", "override"])
def test_rejected_auth_is_persisted_without_claiming_attempted_user_as_actor(env, kind):
    bridge, db, _ = env
    auth = bridge._auth
    secret = "never-record-this"
    if kind == "override":
        assert auth.verify_pin(secret) is None
    else:
        with pytest.raises(ValueError):
            if kind == "pin_only":
                auth.login_by_pin(secret)
            else:
                auth.login(99999 if kind == "missing_id" else 1, secret)
    row = db.fetch_one("SELECT * FROM audit_log WHERE event_type='login_failed'")
    assert row is not None and row["user_id"] is None
    assert row["action"] == "Authentication rejected"
    details = json.loads(row["details"])
    assert details["attempt"] == 1
    assert details["attempted_user_id"] == ({"known_id": 1, "missing_id": 99999}.get(kind))
    assert secret not in str(dict(row))
    assert not db.raw_connection.in_transaction
    assert db.fetch_all("PRAGMA foreign_key_check") == []


def test_failed_login_throttle_remains_and_logs_without_guesses(env):
    bridge, db, _ = env
    for attempt in range(5):
        with pytest.raises(ValueError):
            bridge._auth.login_by_pin(f"wrong-{attempt}")
    with pytest.raises(ValueError, match="تجاوز"):
        bridge._auth.login_by_pin("1234")
    rows = db.fetch_all("SELECT * FROM audit_log WHERE event_type='login_failed'")
    assert len(rows) == 5
    assert all("wrong-" not in str(dict(row)) for row in rows)


def test_failed_audit_cannot_bypass_auth_or_leave_transaction(env, caplog):
    bridge, db, _ = env
    db.execute("CREATE TRIGGER fail_auth_audit BEFORE INSERT ON audit_log BEGIN SELECT RAISE(ABORT,'disk failure'); END")
    db.commit()
    with pytest.raises(ValueError):
        bridge._auth.login_by_pin("unknown-secret")
    assert bridge._auth.get_current_user() is None
    assert bridge._auth.get_throttle_state("pin-only-login")[0] == 1
    assert not db.raw_connection.in_transaction
    assert "Audit log of failed login could not be written" in caplog.text
    assert "unknown-secret" not in caplog.text


def test_create_user_records_real_admin_actor_and_no_credential_fields(env):
    _, db, call = env
    actor = call("login", {"pin": "1234"})
    user = call("create_user", {"username": "audited", "display_name": "Audited", "role": "cashier", "pin": "987654", "cashier_slot": 1})
    row = db.fetch_one("SELECT * FROM audit_log WHERE event_type='user_created'")
    assert row["user_id"] == actor["id"] and row["entity_id"] == user["id"]
    assert row["entity_type"] == "user" and row["action"] == "User created"
    assert json.loads(row["details"]) == {"username": "audited", "role": "cashier", "cashier_slot": 1}
    saved = db.fetch_one("SELECT pin_hash,pin_salt FROM users WHERE id=?", (user["id"],))
    for secret in ("987654", saved["pin_hash"], saved["pin_salt"]):
        assert secret not in str(dict(row))


def test_failed_user_creation_audit_rolls_back_user(env):
    bridge, db, call = env
    call("login", {"pin": "1234"})
    with patch.object(bridge._auth._audit, "log", side_effect=sqlite3.OperationalError("audit unavailable")):
        call("create_user", {"username": "rollback", "display_name": "Rollback", "role": "cashier", "pin": "987654"}, ok=False)
    assert db.fetch_one("SELECT id FROM users WHERE username='rollback'") is None
    assert not db.raw_connection.in_transaction
    assert db.fetch_one("SELECT count(*) n FROM audit_log WHERE event_type='user_created'")["n"] == 0


def test_creation_without_human_session_records_system_not_created_user(env):
    bridge, db, _ = env
    user = bridge._auth.create_user("bootstrap", "Bootstrap", UserRole.MANAGER, "987654")
    row = db.fetch_one("SELECT * FROM audit_log WHERE event_type='user_created'")
    assert row["user_id"] is None and row["user_name"] == "System"
    assert row["entity_id"] == user.id


def test_cashier_cannot_create_user_or_read_audit(env):
    bridge, _, call = env
    bridge._auth.create_user("cash", "Cash", UserRole.CASHIER, "987654", cashier_slot=1)
    call("login", {"pin": "987654"})
    call("create_user", {"username": "blocked", "display_name": "Blocked", "role": "admin", "pin": "888888"}, ok=False)
    call("get_audit_logs", ok=False)


def test_v10_audit_migration_preserves_every_field_and_fk(tmp_path):
    db = DatabaseConnection(str(tmp_path / "audit.db"))
    initialise_database(db)
    seed_database(db)
    db.execute("DROP TABLE audit_log")
    # Recreate the actual previous schema, only user_id nullability differs.
    from pathlib import Path
    schema = (Path(__file__).parents[1] / "broast_pos/data/database/schema.sql").read_text()
    ddl = schema[schema.index("CREATE TABLE IF NOT EXISTS audit_log ("):]
    ddl = ddl[:ddl.index(");") + 2].replace("user_id      INTEGER REFERENCES", "user_id      INTEGER NOT NULL REFERENCES")
    db.execute(ddl)
    db.execute("UPDATE schema_version SET version=10")
    db.commit()
    repo = AuditRepository(db)
    original = repo.log("historic", 1, "Admin", details={"x": "Arabic عربي"}, entity_type="user", entity_id=1,
                        action="old action", reason="old reason", before_data={"a": 1}, after_data={"a": 2})
    before = dict(db.fetch_one("SELECT * FROM audit_log"))
    initialise_database(db)
    initialise_database(db)
    assert dict(db.fetch_one("SELECT * FROM audit_log WHERE id=?", (original.id,))) == before
    new = repo.log("login_failed", None, "Unknown")
    assert new.id > original.id
    assert repo.get_by_id(new.id).user_id is None
    assert db.fetch_all("PRAGMA foreign_key_check") == []
    with pytest.raises(sqlite3.IntegrityError):
        repo.log("bad-reference", 99999, "Unknown")
    assert not db.raw_connection.in_transaction
    db.close()
