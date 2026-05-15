"""
User repository — all user/authentication database queries.

PIN-based auth: users are identified by PIN alone (SHA-256 hash is UNIQUE).
Manager override: verify_pin returns the user if PIN matches a MANAGER or ADMIN.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from broast_pos.core.models.user import User, UserRole
from broast_pos.data.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """CRUD and query operations for users."""

    # ------------------------------------------------------------------
    # Core contract
    # ------------------------------------------------------------------

    def get_by_id(self, entity_id: int) -> Optional[User]:
        row = self._db.fetch_one("SELECT * FROM users WHERE id = ?", (entity_id,))
        return self._row_to_user(row) if row else None

    def save(self, entity: User) -> User:
        if entity.id is None:
            return self._insert(entity)
        return self._update(entity)

    def delete(self, entity_id: int) -> None:
        """Soft-delete: deactivate user."""
        self._db.execute(
            "UPDATE users SET is_active = 0 WHERE id = ?", (entity_id,)
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_by_username(self, username: str) -> Optional[User]:
        """Lookup user by username (for login screen)."""
        row = self._db.fetch_one(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        )
        return self._row_to_user(row) if row else None

    def get_by_pin(self, pin_hash: str) -> Optional[User]:
        """PIN verification — returns user if hash matches.

        Used for manager overrides: manager types their PIN on any device,
        system identifies them by PIN alone.
        """
        row = self._db.fetch_one(
            "SELECT * FROM users WHERE pin_hash = ? AND is_active = 1",
            (pin_hash,),
        )
        return self._row_to_user(row) if row else None

    def get_all_active(self) -> List[User]:
        """All active users — for user management screen."""
        rows = self._db.fetch_all(
            "SELECT * FROM users WHERE is_active = 1 ORDER BY display_name"
        )
        return [self._row_to_user(r) for r in rows]

    def get_drivers(self) -> List[User]:
        """All active users with cashier_slot IS NULL (drivers).

        Drivers don't have a cashier slot assigned — they don't print receipts.
        """
        rows = self._db.fetch_all(
            """SELECT * FROM users
               WHERE is_active = 1 AND cashier_slot IS NULL
               ORDER BY display_name"""
        )
        return [self._row_to_user(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Map a database row to a User object."""
        return User(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            avatar_path=row["avatar_path"],
            pin_hash=row["pin_hash"],
            role=UserRole(row["role"]),
            cashier_slot=row["cashier_slot"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )

    def _insert(self, user: User) -> User:
        """Insert a new user."""
        self._db.execute(
            """INSERT INTO users
                   (username, display_name, avatar_path, pin_hash,
                    role, cashier_slot, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user.username, user.display_name, user.avatar_path,
                user.pin_hash, user.role.value, user.cashier_slot,
                1 if user.is_active else 0,
            ),
        )
        user.id = self._last_insert_id()
        self._db.commit()
        return user

    def _update(self, user: User) -> User:
        """Update an existing user."""
        self._db.execute(
            """UPDATE users SET
                   username = ?, display_name = ?, avatar_path = ?,
                   pin_hash = ?, role = ?, cashier_slot = ?, is_active = ?
               WHERE id = ?""",
            (
                user.username, user.display_name, user.avatar_path,
                user.pin_hash, user.role.value, user.cashier_slot,
                1 if user.is_active else 0,
                user.id,
            ),
        )
        self._db.commit()
        return user
