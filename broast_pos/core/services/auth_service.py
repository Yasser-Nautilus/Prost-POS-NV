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

from broast_pos.config import config
from broast_pos.core.models.audit import AuditEventType
from broast_pos.core.models.user import User, UserRole
from broast_pos.core.phone import INVALID_PHONE_MSG, normalize_egyptian_mobile
from broast_pos.data.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# B-08 constants
_PIN_MIN_LENGTH: int = 4
_MAX_ATTEMPTS: int = 5      # failures before lockout
_LOCKOUT_SECONDS: int = 30  # lockout window

# Secret pepper mixed into every salted PIN hash. Kept OUT of the database so a
# stolen DB file alone cannot brute-force short PINs via rainbow tables.
# Override in production via the BROAST_PIN_PEPPER environment variable.
_DEFAULT_PEPPER = config.DEV_FALLBACK_PEPPER
_PIN_PEPPER: str = config.get_pin_pepper()

# Hashes created by earlier development builds used the default pepper below.
# Keep it as a verification-only fallback; successful authentication rehashes
# the PIN with the currently configured pepper.
_LEGACY_DEV_PEPPER = os.environ.get(
    "BROAST_PIN_PEPPER_LEGACY", "broast-pos-default-pepper-change-me"
)


def _get_pepper() -> str:
    """Return the active pepper string.

    If _PIN_PEPPER was monkeypatched to a custom test value, honor it.
    Otherwise, retrieve the current configured pepper dynamically from config.
    """
    global _PIN_PEPPER
    if _PIN_PEPPER != _DEFAULT_PEPPER and _PIN_PEPPER is not None:
        return _PIN_PEPPER
    return config.get_pin_pepper()


# Hard-fail on import if production is configured with missing or placeholder secrets
config.validate_production_secrets()

# Checkup-Fix: PBKDF2 statt Single-Round-SHA-256 — macht das Durchprobieren
# aller 10k vierstelligen PINs teuer. Versioniertes Format erlaubt es, alte
# (bare-hex) und neue Hashes nebeneinander zu verifizieren.
_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 100_000
_PBKDF2_PREFIX = "pbkdf2_sha256$"


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
_PERMISSIONS: dict[UserRole, set[Action]] = {
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
        # MANAGE_USERS is intentionally admin-only (canonical policy).
    },
    UserRole.ADMIN: set(Action),  # Admin can do everything
}


class AuthService:
    """Login, session management, permission checks, and manager override."""

    def __init__(self, user_repo: UserRepository | None = None) -> None:
        if config.is_production():
            config.validate_production_secrets()
        self._users = user_repo or UserRepository()
        self._current_user: User | None = None
        # H20: PIN fingerprint the active session logged in with
        self._session_credential: tuple[str, str | None] | None = None
        # B-08: in-memory throttle store — {identifier: (failure_count, first_failure_ts)}
        # H18: identifier is a stable, non-guess-derived label — str(user_id)
        # for login(), a fixed per-surface label for the pin-only paths
        # (never a hash of the guessed PIN; see login_by_pin/verify_pin).
        # Resets on process restart (acceptable for a local POS).
        self._throttle: dict[str, tuple[int, float]] = {}
        # Optional audit repository for authentication and user creation events
        self._audit = None  # injected via set_audit() after construction

    def set_audit(self, audit_repo) -> None:
        """Inject the strict persistence boundary for security audit events."""
        self._audit = audit_repo

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def get_all_users(self) -> list[User]:
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
        self._start_session(user)
        return user

    def login_by_pin(self, pin: str) -> User:
        """Authenticate by PIN only — no user_id required.

        H18: throttled by a single key for this whole login surface, NOT by
        the guessed PIN — a guess-derived key lets an attacker reset their
        attempt count just by trying a different wrong PIN each time. With
        no user_id known yet, the device/surface itself is the only stable
        identity to rate-limit against.
        Looks up the user by PIN hash directly. Any active role can log in.
        Raises:
            ValueError: if PIN not found, user is inactive, or throttled.
        """
        key = "pin-only-login"
        self._check_throttle(key)

        user = self._find_user_by_pin(pin)
        if user is None or not user.is_active:
            self._record_failure(key, user_id=None, reason="wrong PIN (pin-only login)")
            raise ValueError("رمز PIN غير صحيح أو المستخدم غير نشط")

        self._reset_throttle(key)
        self._upgrade_if_legacy(user, pin)
        self._start_session(user)
        return user

    def logout(self) -> None:
        """Clear the active session — return to login screen."""
        self._current_user = None
        self._session_credential = None

    # H20: a session is only valid while the user's PIN is unchanged -----

    @staticmethod
    def _credential_fingerprint(user: User) -> tuple[str, str | None]:
        """Identity of a user's current PIN (hash + salt).

        Every PIN change writes a fresh salt and hash, so the pair differs
        after any change — even if the new PIN equals the old one.
        """
        return (user.pin_hash or "", user.pin_salt)

    def _start_session(self, user: User) -> None:
        """Make *user* the active session and remember the PIN it started with."""
        self._current_user = user
        self._session_credential = self._credential_fingerprint(user)

    def validate_session(self) -> bool:
        """Check the active session against the database.

        Returns False — and ends the session — when the user was deactivated
        or deleted, or when their PIN was changed after this session logged in
        (for example by another admin on another station). Call this before
        serving any protected request.
        """
        user = self._current_user
        if user is None:
            return False
        stored = self._users.get_by_id(user.id) if user.id is not None else None
        if (
            stored is None
            or not stored.is_active
            or self._credential_fingerprint(stored) != self._session_credential
        ):
            logger.info("Session of user id=%s ended: PIN changed or user inactive", user.id)
            self.logout()
            return False
        return True

    def get_current_user(self) -> User | None:
        """Return the currently logged-in user, or None."""
        return self._current_user

    def is_logged_in(self) -> bool:
        """Check if there is an active session."""
        return self._current_user is not None

    def refresh_current_user(self) -> User | None:
        """Re-fetch the logged-in user's live state (H20).

        Permission checks must never rely on a cached role/active flag —
        a deactivation, demotion, or PIN change must take effect on the
        very next request, not only the next full login. Call this before
        any privileged action. Clears the session if the user no longer
        exists or was deactivated since login.
        """
        if self._current_user is None:
            return None
        fresh = self._users.get_by_id(self._current_user.id)
        if fresh is None or not fresh.is_active:
            self._current_user = None
            return None
        self._current_user = fresh
        return fresh

    # ------------------------------------------------------------------
    # Manager override (PIN verification)
    # ------------------------------------------------------------------

    def verify_pin(self, pin: str) -> User | None:
        """Verify a PIN belongs to a MANAGER or ADMIN user.

        H18: throttled by a single key for this override surface, not by
        the guessed PIN (see login_by_pin for why a guess-derived key
        defeats the lockout). Used for override actions: cashier types the
        manager's PIN, system identifies the manager and authorizes the
        action.

        Returns:
            The manager/admin User if PIN is valid, None otherwise.
        """
        key = "manager-override"
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

    def verify_manager_pin(self, pin: str | None) -> User:
        """Verify a manager/admin PIN — raises ValueError on failure.

        Thin wrapper around verify_pin() for use by CashierSessionService
        where a missing or invalid PIN must raise rather than return None.

        Returns:
            The manager/admin User.
        Raises:
            ValueError: if PIN is None, empty, or does not match a manager/admin.
        """
        if not pin:
            raise ValueError("يجب إدخال رمز PIN للمدير")
        user = self.verify_pin(pin)
        if user is None:
            raise ValueError("PIN غير صحيح أو ليس لديك صلاحية")
        return user

    def get_manager_by_pin(self, pin: str | None) -> User | None:
        """Resolve a manager/admin user from a PIN — returns None on failure.

        Alias for verify_pin() with None-safe input handling.
        Used by CashierSessionService for optional manager identification.
        """
        if not pin:
            return None
        return self.verify_pin(pin)

    def get_user_by_id(self, user_id: int) -> User | None:
        """Public accessor to look up a user by ID.

        Provides a clean public interface so controllers don't need to
        access the private _users repository attribute directly.
        """
        return self._users.get_by_id(user_id)

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

    def get_users_for_management(self) -> list[User]:
        """Return all users (active and inactive) for admin management."""
        return self._users.get_all()

    def create_user(
        self,
        username: str,
        display_name: str,
        role: UserRole,
        pin: str,
        cashier_slot: int | None = None,
        avatar_path: str | None = None,
        phone: str | None = None,
        require_driver_phone: bool = False,
    ) -> User:
        """Create a new user. Validates username and unique PIN.

        With ``require_driver_phone`` (set by the user-management screen),
        drivers (cashier role with no cashier_slot) must have a phone number.
        """
        username = username.strip()
        display_name = display_name.strip()
        if not username:
            raise ValueError("اسم المستخدم مطلوب")
        if not display_name:
            raise ValueError("الاسم المعروض مطلوب")
        if not pin:
            raise ValueError("رمز PIN مطلوب")
        # B-08: enforce minimum PIN length
        if not isinstance(pin, str) or not pin.isascii() or not pin.isdecimal() or len(pin) < _PIN_MIN_LENGTH:
            raise ValueError(
                f"رمز PIN يجب أن يكون {_PIN_MIN_LENGTH} أرقام إنجليزية (0-9) على الأقل"
            )

        if self._pin_in_use(pin):
            raise ValueError("رمز PIN مستخدم بالفعل لمستخدم آخر")

        phone = self._normalise_phone(phone)
        if require_driver_phone and role == UserRole.CASHIER and cashier_slot is None and not phone:
            raise ValueError("رقم التليفون مطلوب للطيار")

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
            phone=phone,
        )
        from contextlib import nullcontext
        db = getattr(self._users, "_db", None)
        try:
            with db.transaction() if db is not None and self._audit is not None else nullcontext():
                saved = self._users.save(user)
                if self._audit is not None:
                    actor = self._current_user
                    self._audit.log(
                        event_type=AuditEventType.USER_CREATED,
                        user_id=actor.id if actor else None,
                        user_name=(actor.display_name or actor.username) if actor else "System",
                        entity_type="user", entity_id=saved.id,
                        action="User created",
                        details={"username": saved.username, "role": saved.role.value,
                                 "cashier_slot": saved.cashier_slot},
                    )
                return saved
        except BaseException:
            user.id = None
            raise

    def update_user(
        self,
        user_id: int,
        username: str | None = None,
        display_name: str | None = None,
        role: UserRole | None = None,
        pin: str | None = None,
        cashier_slot: int | None = -1,  # use -1 as sentinel
        avatar_path: str | None = None,
        is_active: bool | None = None,
        phone: str | None = None,
        require_driver_phone: bool = False,
    ) -> User:
        """Update an existing user. Validates unique PIN if changed."""
        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("المستخدم غير موجود")

        # H20: self/last-admin protection, backend-enforced (the frontend
        # guard alone does not stop a direct bridge call).
        is_self = self._current_user is not None and self._current_user.id == user_id
        demoting_from_admin = (
            role is not None and role != UserRole.ADMIN and user.role == UserRole.ADMIN
        )
        deactivating = is_active is False and user.is_active

        if is_self and deactivating:
            raise ValueError("لا يمكنك إلغاء تفعيل حسابك الخاص")
        if is_self and demoting_from_admin:
            raise ValueError("لا يمكنك تخفيض صلاحياتك الخاصة")

        if user.role == UserRole.ADMIN and (deactivating or demoting_from_admin):
            other_active_admins = [
                u for u in self._users.get_all_active()
                if u.role == UserRole.ADMIN and u.id != user_id
            ]
            if not other_active_admins:
                raise ValueError(
                    "لا يمكن إلغاء تفعيل أو تخفيض آخر مدير نظام نشط"
                )

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
            if not isinstance(pin, str) or not pin.isascii() or not pin.isdecimal() or len(pin) < _PIN_MIN_LENGTH:
                raise ValueError(
                    f"رمز PIN يجب أن يكون {_PIN_MIN_LENGTH} أرقام إنجليزية (0-9) على الأقل"
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

        if phone is not None:
            user.phone = self._normalise_phone(phone)
        if (
            require_driver_phone
            and user.role == UserRole.CASHIER
            and user.cashier_slot is None
            and user.is_active
            and not user.phone
        ):
            raise ValueError("رقم التليفون مطلوب للطيار")

        saved = self._users.save(user)

        # H20: if the caller just changed their OWN account, refresh the
        # cached session immediately — the next privileged check must see
        # the new role/active status right away, not after another login.
        if is_self:
            self._current_user = saved if saved.is_active else None
            # H20: an own PIN change re-fingerprints this session; every
            # other session of this user is rejected by validate_session().
            if pin is not None and self._current_user is not None:
                self._start_session(saved)

        return saved

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
        """Salted + peppered PBKDF2-HMAC-SHA256 hash (versioned format).

        Checkup-Fix: ersetzt den früheren Single-Round-SHA-256. Rückgabe-Format
        ``pbkdf2_sha256$<iterations>$<hex>`` macht das Schema selbstbeschreibend.
        """
        dk = hashlib.pbkdf2_hmac(
            _PBKDF2_ALGO,
            (_get_pepper() + raw_pin).encode("utf-8"),
            salt.encode("utf-8"),
            _PBKDF2_ITERATIONS,
        )
        return f"{_PBKDF2_PREFIX}{_PBKDF2_ITERATIONS}${dk.hex()}"

    @staticmethod
    def _hash_legacy_salted(raw_pin: str, salt: str) -> str:
        """Pre-checkup salted SHA-256 hash — kept only to verify old v6 hashes."""
        return hashlib.sha256((_get_pepper() + salt + raw_pin).encode("utf-8")).hexdigest()

    @staticmethod
    def _verify_pin_with_pepper(user: User, raw_pin: str, pepper: str) -> bool:
        """Verify a salted hash using one specific pepper."""
        if user.pin_salt:
            stored = user.pin_hash or ""
            if stored.startswith(_PBKDF2_PREFIX):
                # Format: pbkdf2_sha256$<iterations>$<hex>
                try:
                    _, iter_str, expected = stored.split("$", 2)
                    iterations = int(iter_str)
                except (ValueError, AttributeError):
                    return False
                dk = hashlib.pbkdf2_hmac(
                    _PBKDF2_ALGO,
                    (pepper + raw_pin).encode("utf-8"),
                    user.pin_salt.encode("utf-8"),
                    iterations,
                )
                return secrets.compare_digest(dk.hex(), expected)
            # Legacy salted SHA-256 (will be upgraded on next successful login)
            legacy = hashlib.sha256(
                (pepper + user.pin_salt + raw_pin).encode("utf-8")
            ).hexdigest()
            return secrets.compare_digest(stored, legacy)
        # Unsalted SHA-256 predates pepper support and is pepper-independent.
        return secrets.compare_digest(user.pin_hash or "", AuthService.hash_pin(raw_pin))

    def _verify_pin(self, user: User, raw_pin: str) -> bool:
        """Verify current hashes and, in development, the previous default pepper."""
        if self._verify_pin_with_pepper(user, raw_pin, _get_pepper()):
            return True

        # Never accept a development fallback in production. This fallback
        # only preserves local development accounts across a default change.
        if config.ENVIRONMENT != "prod" and _get_pepper() != _LEGACY_DEV_PEPPER:
            return self._verify_pin_with_pepper(user, raw_pin, _LEGACY_DEV_PEPPER)
        return False

    def _upgrade_if_legacy(self, user: User, raw_pin: str) -> None:
        """Transparently migrate a user to the current PBKDF2 hash scheme.

        Checkup-Fix: upgradet jetzt sowohl unsaltete Legacy-Hashes ALS AUCH die
        alten salted-SHA-256-Hashes auf PBKDF2. Called after a successful
        authentication; non-fatal — a failure here never blocks the login.
        """
        if (
            user.pin_salt
            and (user.pin_hash or "").startswith(_PBKDF2_PREFIX)
            and self._verify_pin_with_pepper(user, raw_pin, _get_pepper())
        ):
            return  # already on the current scheme with the current pepper
        try:
            salt = self._make_salt()
            user.pin_salt = salt
            user.pin_hash = self._hash_secure(raw_pin, salt)
            self._users.save(user)
        except Exception:
            logger.exception("PIN upgrade failed for user id=%s", getattr(user, "id", "?"))

    def _find_user_by_pin(self, raw_pin: str) -> User | None:
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

    @staticmethod
    def _normalise_phone(phone: str | None) -> str | None:
        """Normalise a user/driver phone to 01XXXXXXXXX (English digits).

        Accepts pasted formats (+20, spaces, dashes). Empty means no phone.
        """
        if phone is None or not str(phone).strip():
            return None
        normalized = normalize_egyptian_mobile(phone)
        if normalized is None:
            raise ValueError(INVALID_PHONE_MSG)
        return normalized

    def _pin_in_use(self, raw_pin: str, exclude_user_id: int | None = None) -> bool:
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

    def _record_failure(self, key: str, user_id: int | None, reason: str) -> None:
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
                    event_type=AuditEventType.LOGIN_FAILED,
                    user_id=None,
                    user_name="مجهول",
                    details={"reason": reason, "attempt": count_after, "key": key, "attempted_user_id": user_id},
                    action="Authentication rejected",
                )
            except Exception:
                # Checkup-Fix: audit write is best-effort, but log the failure.
                logger.error("Audit log of failed login could not be written", exc_info=True)

    def _reset_throttle(self, key: str) -> None:
        """Clear failure count after a successful authentication."""
        self._throttle.pop(key, None)

    def get_throttle_state(self, key: str) -> tuple[int, bool]:
        """Return (attempt_count, is_locked_out) for a given key (testing/debug)."""
        record = self._throttle.get(key)
        if record is None:
            return 0, False
        count, first_ts = record
        is_locked = count >= _MAX_ATTEMPTS and (time.monotonic() - first_ts) < _LOCKOUT_SECONDS
        return count, is_locked
