"""
Auth service — login, session, permissions, and manager override.

PIN-based auth: users are identified by PIN alone (SHA-256 hash).
Manager override: verify_pin returns the user if PIN matches MANAGER or ADMIN.
No fast-switch — full logout/login every time.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Dict, List, Optional, Set

from broast_pos.core.models.user import User, UserRole
from broast_pos.data.repositories.user_repository import UserRepository


class Action(str, Enum):
    """Restricted actions requiring specific roles."""
    CREATE_ORDER = "create_order"
    APPLY_DISCOUNT = "apply_discount"
    CANCEL_ORDER = "cancel_order"
    REMOVE_ORDER_ITEM = "remove_order_item"
    MANAGE_PRODUCTS = "manage_products"
    ADD_DRIVERS = "add_drivers"
    CHECK_IN_OUT_DRIVERS = "check_in_out_drivers"
    OPEN_CLOSE_SHIFT = "open_close_shift"
    VIEW_REPORTS = "view_reports"
    MANAGE_USERS = "manage_users"


# Role → allowed actions
_PERMISSIONS: Dict[UserRole, Set[Action]] = {
    UserRole.CASHIER: {
        Action.CREATE_ORDER,
        Action.CHECK_IN_OUT_DRIVERS,
    },
    UserRole.MANAGER: {
        Action.CREATE_ORDER,
        Action.APPLY_DISCOUNT,
        Action.CANCEL_ORDER,
        Action.REMOVE_ORDER_ITEM,
        Action.MANAGE_PRODUCTS,
        Action.ADD_DRIVERS,
        Action.CHECK_IN_OUT_DRIVERS,
        Action.OPEN_CLOSE_SHIFT,
        Action.VIEW_REPORTS,
    },
    UserRole.ADMIN: set(Action),  # Admin can do everything
}


class AuthService:
    """Login, session management, permission checks, and manager override."""

    def __init__(self, user_repo: Optional[UserRepository] = None) -> None:
        self._users = user_repo or UserRepository()
        self._current_user: Optional[User] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def get_all_users(self) -> List[User]:
        """Return all active users for the login screen tiles."""
        return self._users.get_all_active()

    def login(self, user_id: int, pin: str) -> User:
        """Authenticate user by ID + PIN.

        Returns the logged-in user.
        Raises:
            ValueError: if user not found or PIN is wrong.
        """
        user = self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise ValueError("المستخدم غير موجود")

        pin_hash = self.hash_pin(pin)
        if user.pin_hash != pin_hash:
            raise ValueError("PIN غير صحيح")

        self._current_user = user
        return user

    def logout(self) -> None:
        """Clear the active session — return to login screen."""
        self._current_user = None

    def get_current_user(self) -> Optional[User]:
        """Return the currently logged-in user, or None."""
        return self._current_user

    def is_logged_in(self) -> bool:
        """Check if there is an active session."""
        return self._current_user is not None

    # ------------------------------------------------------------------
    # Manager override (PIN verification)
    # ------------------------------------------------------------------

    def verify_pin(self, pin: str) -> Optional[User]:
        """Verify a PIN belongs to a MANAGER or ADMIN user.

        Used for override actions: cashier types the manager's PIN,
        system identifies the manager and authorizes the action.

        Returns:
            The manager/admin User if PIN is valid, None otherwise.
        """
        pin_hash = self.hash_pin(pin)
        user = self._users.get_by_pin(pin_hash)

        if user is None:
            return None

        # Only managers and admins can authorize overrides
        if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
            return None

        return user

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def check_permission(self, user: User, action: Action) -> bool:
        """Check if a user's role allows the given action."""
        allowed = _PERMISSIONS.get(user.role, set())
        return action in allowed

    def require_permission(self, action: Action) -> None:
        """Raise PermissionError if current user lacks permission.

        Raises:
            PermissionError: if no user logged in or action not allowed.
        """
        if self._current_user is None:
            raise PermissionError("يجب تسجيل الدخول أولاً")

        if not self.check_permission(self._current_user, action):
            raise PermissionError("ليس لديك صلاحية لهذا الإجراء")

    # ------------------------------------------------------------------
    # PIN hashing
    # ------------------------------------------------------------------

    @staticmethod
    def hash_pin(raw_pin: str) -> str:
        """SHA-256 hash a PIN string. One-way — cannot be reversed."""
        return hashlib.sha256(raw_pin.encode("utf-8")).hexdigest()
