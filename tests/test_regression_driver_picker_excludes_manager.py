"""
Regression test — get_drivers() must not return manager/admin users.

Root cause: the original query filtered only on cashier_slot IS NULL.
Managers and admins also have cashier_slot = NULL when they don't operate
a register, so they appeared in the driver picker on the deliveries screen.

Fix: added AND role = 'cashier' to the query.
"""
from __future__ import annotations

import pytest

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.user_repository import UserRepository


@pytest.fixture(autouse=True)
def _reset_db_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    initialise_database(db)
    return db


def _insert_user(
    db: DatabaseConnection,
    *,
    user_id: int,
    username: str,
    role: str,
    cashier_slot: int | None,
    is_active: int = 1,
) -> None:
    db.execute(
        """INSERT INTO users
               (id, username, display_name, pin_hash, role, cashier_slot, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, username, username, f"hash{user_id}", role, cashier_slot, is_active),
    )


class TestGetDriversExcludesManagers:
    """UserRepository.get_drivers() returns only cashier-role, slot-less users."""

    def test_cashier_driver_is_returned(self):
        db = _fresh_db()
        _insert_user(db, user_id=1, username="driver1", role="cashier", cashier_slot=None)
        repo = UserRepository(db)
        ids = [u.id for u in repo.get_drivers()]
        assert 1 in ids

    def test_manager_with_no_slot_is_excluded(self):
        db = _fresh_db()
        _insert_user(db, user_id=2, username="mgr", role="manager", cashier_slot=None)
        repo = UserRepository(db)
        ids = [u.id for u in repo.get_drivers()]
        assert 2 not in ids

    def test_admin_with_no_slot_is_excluded(self):
        db = _fresh_db()
        _insert_user(db, user_id=3, username="adm", role="admin", cashier_slot=None)
        repo = UserRepository(db)
        ids = [u.id for u in repo.get_drivers()]
        assert 3 not in ids

    def test_cashier_with_slot_is_excluded(self):
        """Cashiers assigned to a register are not drivers."""
        db = _fresh_db()
        _insert_user(db, user_id=4, username="cash1", role="cashier", cashier_slot=1)
        repo = UserRepository(db)
        ids = [u.id for u in repo.get_drivers()]
        assert 4 not in ids

    def test_inactive_driver_is_excluded(self):
        db = _fresh_db()
        _insert_user(db, user_id=5, username="ex_drv", role="cashier", cashier_slot=None, is_active=0)
        repo = UserRepository(db)
        ids = [u.id for u in repo.get_drivers()]
        assert 5 not in ids

    def test_mixed_users_only_active_cashier_drivers_returned(self):
        """Only the one active cashier-role, slot-less user appears."""
        db = _fresh_db()
        _insert_user(db, user_id=10, username="driver_ok", role="cashier", cashier_slot=None)
        _insert_user(db, user_id=11, username="manager_user", role="manager", cashier_slot=None)
        _insert_user(db, user_id=12, username="admin_user", role="admin", cashier_slot=None)
        _insert_user(db, user_id=13, username="cashier_reg", role="cashier", cashier_slot=2)
        _insert_user(db, user_id=14, username="inactive_drv", role="cashier", cashier_slot=None, is_active=0)
        repo = UserRepository(db)
        ids = [u.id for u in repo.get_drivers()]
        assert ids == [10]
