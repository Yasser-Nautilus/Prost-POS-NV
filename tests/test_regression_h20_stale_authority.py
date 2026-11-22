"""
Regression tests — H20: deactivating/demoting a user did not revoke the
active in-memory authority.

Root cause:
  Permission checks used the bridge's/AuthService's CACHED current-user
  object. update_user() loaded and saved a SEPARATELY fetched User, so
  changing account status/role never touched the cached session — a
  logged-in admin who was deactivated (or demoted) kept full authority
  until they logged out and back in. There was also no backend-side
  protection against self-deactivation/self-demotion or removing the
  last active admin.

Fix verified here:
  - A logged-in admin deactivated through update_user() loses admin
    authority on the very next dispatched action (bridge revalidates
    from DB state every call via AuthService.refresh_current_user()).
  - Same for a role demotion (admin -> cashier).
  - An admin cannot deactivate or demote their own account.
  - The last active admin cannot be deactivated or demoted by anyone.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.user import UserRole
from broast_pos.core.services.auth_service import AuthService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.infrastructure.web_bridge.bridge import POSBridge


@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'admin1','مدير 1','admin','h1',1), (2,'admin2','مدير 2','admin','h2',1)"
    )
    db.commit()
    return db


def _make_bridge(db: DatabaseConnection, current_user_id: int) -> POSBridge:
    user_repo = UserRepository(db)
    auth = AuthService(user_repo=user_repo)
    auth._current_user = user_repo.get_by_id(current_user_id)

    bridge = POSBridge.__new__(POSBridge)
    bridge._auth = auth
    bridge._current_user = auth._current_user
    bridge._order_ctrl = None
    bridge._delivery_ctrl = None
    bridge._financial_ctrl = None
    bridge._reports_ctrl = None
    def _fake_create_category(**kw):
        cat = MagicMock()
        cat.id = 1
        cat.name = kw.get("name")
        cat.sort_order = kw.get("sort_order", 0)
        cat.is_active = True
        return cat

    products = MagicMock()
    products.create_category.side_effect = _fake_create_category
    bridge._product = products
    return bridge


class TestH20StaleAuthorityRevoked:

    def test_deactivated_admin_loses_authority_on_next_action(self):
        db = _fresh_db()
        bridge = _make_bridge(db, current_user_id=1)

        # Admin 1 deactivates themself... no wait, admin 2 deactivates admin 1
        # while admin 1's session is the one still cached in the bridge.
        admin2_bridge = _make_bridge(db, current_user_id=2)
        resp = json.loads(admin2_bridge.dispatch("update_user", json.dumps({
            "user_id": 1, "is_active": False,
        })))
        assert resp["success"] is True

        # Admin 1's own bridge still has the OLD cached user — but the very
        # next action must revalidate from the DB and reject.
        resp2 = json.loads(bridge.dispatch("create_category", json.dumps({
            "name": "فئة جديدة", "sort_order": 1,
        })))
        assert resp2["success"] is False, (
            "H20 regression: a deactivated admin could still perform "
            "privileged actions using the stale cached session"
        )

    def test_demoted_admin_loses_authority_on_next_action(self):
        db = _fresh_db()
        bridge = _make_bridge(db, current_user_id=1)
        admin2_bridge = _make_bridge(db, current_user_id=2)

        resp = json.loads(admin2_bridge.dispatch("update_user", json.dumps({
            "user_id": 1, "role": "cashier",
        })))
        assert resp["success"] is True

        resp2 = json.loads(bridge.dispatch("create_category", json.dumps({
            "name": "فئة جديدة", "sort_order": 1,
        })))
        assert resp2["success"] is False, (
            "H20 regression: a demoted admin could still perform admin "
            "actions using the stale cached session"
        )


class TestH20SelfAndLastAdminProtection:

    def test_cannot_deactivate_own_account(self):
        db = _fresh_db()
        bridge = _make_bridge(db, current_user_id=1)

        resp = json.loads(bridge.dispatch("update_user", json.dumps({
            "user_id": 1, "is_active": False,
        })))
        assert resp["success"] is False

        still_active = UserRepository(db).get_by_id(1)
        assert still_active.is_active is True

    def test_cannot_demote_own_account(self):
        db = _fresh_db()
        bridge = _make_bridge(db, current_user_id=1)

        resp = json.loads(bridge.dispatch("update_user", json.dumps({
            "user_id": 1, "role": "cashier",
        })))
        assert resp["success"] is False

        still_admin = UserRepository(db).get_by_id(1)
        assert still_admin.role == UserRole.ADMIN

    def test_cannot_deactivate_last_active_admin(self):
        db = _fresh_db()
        # Only one active admin remains after demoting/removing admin2 first.
        db.execute("UPDATE users SET role = 'cashier' WHERE id = 2")
        db.commit()
        # admin2 (now cashier) tries to deactivate admin1 — blocked separately
        # by not being admin at all, so use a direct service call instead to
        # isolate the last-admin rule.
        user_repo = UserRepository(db)
        auth = AuthService(user_repo=user_repo)
        admin2 = user_repo.get_by_id(2)
        auth._current_user = admin2  # acting as someone other than admin1

        with pytest.raises(ValueError):
            auth.update_user(user_id=1, is_active=False)

        still_active = user_repo.get_by_id(1)
        assert still_active.is_active is True

    def test_can_deactivate_admin_when_another_active_admin_remains(self):
        db = _fresh_db()
        bridge = _make_bridge(db, current_user_id=2)  # acting as admin2

        resp = json.loads(bridge.dispatch("update_user", json.dumps({
            "user_id": 1, "is_active": False,
        })))
        assert resp["success"] is True, (
            "Deactivating a non-self admin must still work when another "
            "active admin remains"
        )

    def test_refresh_current_user_clears_session_when_deactivated(self):
        db = _fresh_db()
        user_repo = UserRepository(db)
        auth = AuthService(user_repo=user_repo)
        auth._current_user = user_repo.get_by_id(1)

        db.execute("UPDATE users SET is_active = 0 WHERE id = 1")
        db.commit()

        refreshed = auth.refresh_current_user()
        assert refreshed is None
        assert auth.get_current_user() is None

    def test_refresh_current_user_picks_up_role_change(self):
        db = _fresh_db()
        user_repo = UserRepository(db)
        auth = AuthService(user_repo=user_repo)
        auth._current_user = user_repo.get_by_id(2)

        db.execute("UPDATE users SET role = 'cashier' WHERE id = 2")
        db.commit()

        refreshed = auth.refresh_current_user()
        assert refreshed is not None
        assert refreshed.role == UserRole.CASHIER
