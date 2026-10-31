"""
Auth service — login, session, permissions, and manager override.

PIN-based auth: users are identified by PIN alone (SHA-256 hash).
Manager override: verify_pin returns the user if PIN matches MANAGER or ADMIN.
No fast-switch — full logout/login every time.

B-08 Hardening:
  - PIN minimum length: 4 characters enforced at create/update.
  - Brute-force throttle: 5 failures → 30-second lockout per identifier.
    Identifier = user_id (for login) or truncated pin_hash (for pin-only paths).
  - Failed login attempts are logged to the audit trail.
"""

from __future__ import annotations

import hashlib
import logging
import time
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from broast_pos.core.models.user import User, UserRole
from broast_pos.data.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# B-08 constants
_PIN_MIN_LENGTH: int = 4
_MAX_ATTEMPTS: int = 5      # failures before lockout
_LOCKOUT_SECONDS: int = 30  # lockout window


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
        # B-08: in-memory throttle store — {identifier: (failure_count, first_failure_ts)}
        # Identifier: str(user_id) for login(), pin_hash[:8] for pin-only paths.
        # Resets on process restart (acceptable for a local POS).
        self._throttle: Dict[str, Tuple[int, float]] = {}
        # Optional audit repository for recording failed attempts
        self._audit = None  # injected via set_audit() after construction

    def set_audit(self, audit_repo) -> None:
        """Inject audit repository for recording failed login attempts (B-08)."""
        self._audit = audit_repo

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def get_all_users(self) -> List[User]:
        """Return all active users for the login screen tiles."""
        return self._users.get_all_active()

    def login(self, user_id: int, pin: str) -> User:
        """Authenticate user by ID + PIN.

        B-08: throttled — 5 failures → 30s lockout.
        Returns the logged-in user.
        Raises:
            ValueError: if user not found, PIN wrong, or throttled.
        """
        key = f"uid:{user_id}"
        self._check_throttle(key)

        user = self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            self._record_failure(key, user_id=user_id, reason="user not found")
            raise ValueError("المستخدم غير موجود")

        pin_hash = self.hash_pin(pin)
        if user.pin_hash != pin_hash:
            self._record_failure(key, user_id=user_id, reason="wrong PIN")
            raise ValueError("PIN غير صحيح")

        self._reset_throttle(key)
        self._current_user = user
        return user

    def login_by_pin(self, pin: str) -> User:
        """Authenticate by PIN only — no user_id required.

        B-08: throttled by a stable key derived from the entered PIN.
        Looks up the user by PIN hash directly. Any active role can log in.
        Raises:
            ValueError: if PIN not found, user is inactive, or throttled.
        """
        # Use first 8 chars of hash as the throttle key (stable, not reversible)
        pin_hash = self.hash_pin(pin)
        key = f"pin:{pin_hash[:8]}"
        self._check_throttle(key)

        user = self._users.get_by_pin(pin_hash)
        if user is None or not user.is_active:
            self._record_failure(key, user_id=None, reason="wrong PIN (pin-only login)")
            raise ValueError("رمز PIN غير صحيح أو المستخدم غير نشط")

        self._reset_throttle(key)
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

        B-08: throttled to prevent manager-PIN brute-force during overrides.
        Used for override actions: cashier types the manager's PIN,
        system identifies the manager and authorizes the action.

        Returns:
            The manager/admin User if PIN is valid, None otherwise.
        """
        pin_hash = self.hash_pin(pin)
        key = f"override:{pin_hash[:8]}"
        self._check_throttle(key)

        user = self._users.get_by_pin(pin_hash)

        if user is None:
            self._record_failure(key, user_id=None, reason="wrong override PIN")
            return None

        # Only managers and admins can authorize overrides
        if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
            self._record_failure(key, user_id=user.id, reason="wrong role for override")
            return None

        self._reset_throttle(key)
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
    # User management (admin only)
    # ------------------------------------------------------------------

    def get_users_for_management(self) -> List[User]:
        """Return all users (active and inactive) for admin management."""
        return self._users.get_all()

    def create_user(
        self,
        username: str,
        display_name: str,
        role: UserRole,
        pin: str,
        cashier_slot: Optional[int] = None,
        avatar_path: Optional[str] = None,
    ) -> User:
        """Create a new user. Validates username and unique PIN."""
        username = username.strip()
        display_name = display_name.strip()
        if not username:
            raise ValueError("اسم المستخدم مطلوب")
        if not display_name:
            raise ValueError("الاسم المعروض مطلوب")
        if not pin:
            raise ValueError("رمز PIN مطلوب")
        # B-08: enforce minimum PIN length
        if len(pin) < _PIN_MIN_LENGTH:
            raise ValueError(
                f"رمز PIN يجب أن يكون {_PIN_MIN_LENGTH} أرقام على الأقل"
            )

        pin_hash = self.hash_pin(pin)
        if self._users.pin_exists(pin_hash):
            raise ValueError("رمز PIN مستخدم بالفعل لمستخدم آخر")

        user = User(
            id=None,
            username=username,
            display_name=display_name,
            role=role,
            pin_hash=pin_hash,
            cashier_slot=cashier_slot,
            avatar_path=avatar_path,
            is_active=True,
        )
        return self._users.save(user)

    def update_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        role: Optional[UserRole] = None,
        pin: Optional[str] = None,
        cashier_slot: Optional[int] = -1,  # use -1 as sentinel
        avatar_path: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        """Update an existing user. Validates unique PIN if changed."""
        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("المستخدم غير موجود")

        if username is not None:
            username = username.strip()
            if not username:
                raise ValueError("اسم المستخدم مطلوب")
            user.username = username

        if display_name is not None:
            display_name = display_name.strip()
            if not display_name:
                raise ValueError("الاسم المعروض مطلوب")
            user.display_name = display_name

        if role is not None:
            user.role = role

        if pin is not None:
            pin = pin.strip()
            if not pin:
                raise ValueError("رمز PIN لا يمكن أن يكون فارغاً")
            # B-08: enforce minimum PIN length on update too
            if len(pin) < _PIN_MIN_LENGTH:
                raise ValueError(
                    f"رمز PIN يجب أن يكون {_PIN_MIN_LENGTH} أرقام على الأقل"
                )
            pin_hash = self.hash_pin(pin)
            if self._users.pin_exists(pin_hash, exclude_user_id=user_id):
                raise ValueError("رمز PIN مستخدم بالفعل لمستخدم آخر")
            user.pin_hash = pin_hash

        if cashier_slot != -1:
            user.cashier_slot = cashier_slot

        if avatar_path is not None:
            user.avatar_path = avatar_path

        if is_active is not None:
            user.is_active = is_active

        return self._users.save(user)

    # ------------------------------------------------------------------
    # PIN hashing
    # ------------------------------------------------------------------

    @staticmethod
    def hash_pin(raw_pin: str) -> str:
        """SHA-256 hash a PIN string. One-way — cannot be reversed."""
        return hashlib.sha256(raw_pin.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # B-08: Brute-force throttle (in-memory)
    # ------------------------------------------------------------------

    def _check_throttle(self, key: str) -> None:
        """Raise ValueError if the key is currently locked out.

        After _MAX_ATTEMPTS failures within the window, any attempt is blocked
        for _LOCKOUT_SECONDS seconds from the FIRST failure.
        """
        record = self._throttle.get(key)
        if record is None:
            return
        count, first_ts = record
        if count >= _MAX_ATTEMPTS:
            elapsed = time.monotonic() - first_ts
            if elapsed < _LOCKOUT_SECONDS:
                remaining = int(_LOCKOUT_SECONDS - elapsed)
                raise ValueError(
                    f"تم تجاوز عدد المحاولات المسموحة. يرجى المحاولة مرة أخرى بعد {remaining} ثانية"
                )
            else:
                # Lockout expired — reset
                del self._throttle[key]

    def _record_failure(self, key: str, user_id: Optional[int], reason: str) -> None:
        """Increment failure count and optionally log to audit."""
        now = time.monotonic()
        if key in self._throttle:
            count, first_ts = self._throttle[key]
            self._throttle[key] = (count + 1, first_ts)
        else:
            self._throttle[key] = (1, now)

        count_after = self._throttle[key][0]
        logger.warning("Auth failure [%s] attempt %d: %s", key, count_after, reason)

        # Audit trail — non-fatal
        if self._audit is not None:
            try:
                self._audit.log(
                    event_type="login_failed",
                    user_id=user_id or 0,
                    user_name="مجهول",
                    details={"reason": reason, "attempt": count_after, "key": key},
                )
            except Exception:
                pass

    def _reset_throttle(self, key: str) -> None:
        """Clear failure count after a successful authentication."""
        self._throttle.pop(key, None)

    def get_throttle_state(self, key: str) -> Tuple[int, bool]:
        """Return (attempt_count, is_locked_out) for a given key (testing/debug)."""
        record = self._throttle.get(key)
        if record is None:
            return 0, False
        count, first_ts = record
        is_locked = count >= _MAX_ATTEMPTS and (time.monotonic() - first_ts) < _LOCKOUT_SECONDS
        return count, is_locked
