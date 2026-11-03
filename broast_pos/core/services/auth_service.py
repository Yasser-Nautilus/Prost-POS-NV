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
import os
import secrets
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

# Secret pepper mixed into every salted PIN hash. Kept OUT of the database so a
# stolen DB file alone cannot brute-force short PINs via rainbow tables.
# Override in production via the BROAST_PIN_PEPPER environment variable.
_PIN_PEPPER: str = os.environ.get("BROAST_PIN_PEPPER", "broast-pos-default-pepper-change-me")


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
        Action.MANAGE_USERS,
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

        if not self._verify_pin(user, pin):
            self._record_failure(key, user_id=user_id, reason="wrong PIN")
            raise ValueError("PIN غير صحيح")

        self._reset_throttle(key)
        self._upgrade_if_legacy(user, pin)
        self._current_user = user
        return user

    def login_by_pin(self, pin: str) -> User:
        """Authenticate by PIN only — no user_id required.

        B-08: throttled by a stable key derived from the entered PIN.
        Looks up the user by PIN hash directly. Any active role can log in.
        Raises:
            ValueError: if PIN not found, user is inactive, or throttled.
        """
        # Use first 8 chars of the legacy hash as the throttle key
        # (stable across hashing schemes, not reversible)
        pin_hash = self.hash_pin(pin)
        key = f"pin:{pin_hash[:8]}"
        self._check_throttle(key)

        user = self._find_user_by_pin(pin)
        if user is None or not user.is_active:
            self._record_failure(key, user_id=None, reason="wrong PIN (pin-only login)")
            raise ValueError("رمز PIN غير صحيح أو المستخدم غير نشط")

        self._reset_throttle(key)
        self._upgrade_if_legacy(user, pin)
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

        user = self._find_user_by_pin(pin)

        if user is None:
            self._record_failure(key, user_id=None, reason="wrong override PIN")
            return None

        # Only managers and admins can authorize overrides
        if user.role not in (UserRole.MANAGER, UserRole.ADMIN):
            self._record_failure(key, user_id=user.id, reason="wrong role for override")
            return None

        self._reset_throttle(key)
        self._upgrade_if_legacy(user, pin)
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

        if self._pin_in_use(pin):
            raise ValueError("رمز PIN مستخدم بالفعل لمستخدم آخر")

        salt = self._make_salt()
        pin_hash = self._hash_secure(pin, salt)

        user = User(
            id=None,
            username=username,
            display_name=display_name,
            role=role,
            pin_hash=pin_hash,
            pin_salt=salt,
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
            if self._pin_in_use(pin, exclude_user_id=user_id):
                raise ValueError("رمز PIN مستخدم بالفعل لمستخدم آخر")
            salt = self._make_salt()
            user.pin_salt = salt
            user.pin_hash = self._hash_secure(pin, salt)

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
        """Legacy unsalted SHA-256 hash of a PIN.

        Kept for backward compatibility: it still verifies pre-v6 users and
        is used as a stable throttle key. New/changed PINs are stored with
        a per-user salt + pepper via ``_hash_secure``.
        """
        return hashlib.sha256(raw_pin.encode("utf-8")).hexdigest()

    @staticmethod
    def _make_salt() -> str:
        """Generate a random per-user salt (128 bits, hex-encoded)."""
        return secrets.token_hex(16)

    @staticmethod
    def _hash_secure(raw_pin: str, salt: str) -> str:
        """Salted + peppered SHA-256 hash. Used for all PINs from v6 on."""
        return hashlib.sha256((_PIN_PEPPER + salt + raw_pin).encode("utf-8")).hexdigest()

    def _verify_pin(self, user: User, raw_pin: str) -> bool:
        """Return True if *raw_pin* matches *user*'s stored hash (either scheme)."""
        if user.pin_salt:
            return user.pin_hash == self._hash_secure(raw_pin, user.pin_salt)
        return user.pin_hash == self.hash_pin(raw_pin)

    def _upgrade_if_legacy(self, user: User, raw_pin: str) -> None:
        """Transparently migrate a legacy (unsalted) user to a salted hash.

        Called after a successful authentication. Non-fatal: a failure here
        never blocks the login.
        """
        if user.pin_salt:
            return
        try:
            salt = self._make_salt()
            user.pin_salt = salt
            user.pin_hash = self._hash_secure(raw_pin, salt)
            self._users.save(user)
        except Exception:
            logger.exception("PIN upgrade failed for user id=%s", getattr(user, "id", "?"))

    def _find_user_by_pin(self, raw_pin: str) -> Optional[User]:
        """Resolve a user from a PIN alone, across both hashing schemes.

        Fast path: legacy unsalted hash lookup (covers not-yet-upgraded users).
        Fallback: iterate active users and verify salted hashes individually —
        per-user salts make a direct hash lookup impossible.
        """
        user = self._users.get_by_pin(self.hash_pin(raw_pin))
        if user is not None:
            return user
        try:
            for cand in self._users.get_all_active():
                if cand.pin_salt and self._verify_pin(cand, raw_pin):
                    return cand
        except (TypeError, AttributeError):
            # Repo without a usable get_all_active (e.g. a unit-test mock)
            return None
        return None

    def _pin_in_use(self, raw_pin: str, exclude_user_id: Optional[int] = None) -> bool:
        """True if *raw_pin* already authenticates some other active user."""
        if self._users.pin_exists(self.hash_pin(raw_pin), exclude_user_id=exclude_user_id):
            return True
        try:
            for cand in self._users.get_all_active():
                if cand.id == exclude_user_id:
                    continue
                if cand.pin_salt and self._verify_pin(cand, raw_pin):
                    return True
        except (TypeError, AttributeError):
            return False
        return False

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
