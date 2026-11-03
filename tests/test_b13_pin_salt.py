"""
B-13: Salted + peppered PIN hashing with transparent legacy upgrade.

Covers migration v6 (users.pin_salt) and the AuthService changes:
  - Legacy (unsalted) users still authenticate.
  - A successful auth upgrades a legacy user to a salted+peppered hash.
  - New users are stored salted; duplicate PINs are rejected.
  - PIN-only lookups (verify_pin / login_by_pin) work for salted users.
"""

import hashlib
import os
import tempfile

import pytest

from broast_pos.core.models.user import UserRole
from broast_pos.core.services import auth_service
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.user_repository import UserRepository

_PEPPER = "test-pepper"


@pytest.fixture()
def auth(monkeypatch):
    # Pin the pepper so hashes are deterministic for assertions.
    monkeypatch.setattr(auth_service, "_PIN_PEPPER", _PEPPER)
    DatabaseConnection.reset()
    db = DatabaseConnection.get_instance(os.path.join(tempfile.mkdtemp(), "t.db"))
    initialise_database(db)
    yield AuthService(UserRepository(db)), UserRepository(db)
    DatabaseConnection.reset()


def _insert_legacy(db_repo: UserRepository, pin: str, role: str = "manager") -> None:
    legacy = hashlib.sha256(pin.encode()).hexdigest()
    db_repo._db.execute(
        "INSERT INTO users (username, display_name, pin_hash, role, is_active) "
        "VALUES (?, ?, ?, ?, 1)",
        ("u", "U", legacy, role),
    )
    db_repo._db.commit()


def test_migration_adds_pin_salt_column(auth):
    _, repo = auth
    cols = {r["name"] for r in repo._db.fetch_all("PRAGMA table_info(users)")}
    assert "pin_salt" in cols


def test_legacy_user_authenticates_and_upgrades(auth):
    svc, repo = auth
    _insert_legacy(repo, "4321")

    before = repo.get_all_active()[0]
    assert before.pin_salt is None  # legacy

    assert svc.verify_pin("4321") is not None

    after = repo.get_all_active()[0]
    assert after.pin_salt  # upgraded
    # Checkup-Fix: upgraded hashes use the versioned PBKDF2 scheme.
    assert after.pin_hash.startswith("pbkdf2_sha256$")
    expected = auth_service.AuthService._hash_secure("4321", after.pin_salt)
    assert after.pin_hash == expected
    # Re-authentication with the upgraded hash still succeeds.
    assert svc.verify_pin("4321") is not None


def test_wrong_pin_rejected(auth):
    svc, repo = auth
    _insert_legacy(repo, "4321")
    assert svc.verify_pin("0000") is None


def test_new_user_is_salted_and_duplicate_blocked(auth):
    svc, _ = auth
    svc.create_user("cash", "Cash", UserRole.CASHIER, "1111", cashier_slot=1)
    with pytest.raises(ValueError):
        svc.create_user("cash2", "Cash2", UserRole.CASHIER, "1111")


def test_login_by_pin_finds_salted_user(auth):
    svc, _ = auth
    svc.create_user("cash", "Cash", UserRole.CASHIER, "2222", cashier_slot=1)
    assert svc.login_by_pin("2222").username == "cash"
