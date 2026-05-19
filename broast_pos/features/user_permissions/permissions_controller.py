"""
Permissions controller — user management, auth orchestration, and audit trail.

Orchestrates AuthService, UserRepository, and AuditRepository to provide:
- User CRUD with validation and audit logging
- PIN management (set, reset, validate uniqueness)
- Manager override flow for restricted actions
- Navigation access control per role
- Audit log queries for admin/manager viewing
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from broast_pos.core.models.user import User, UserRole
from broast_pos.core.services.auth_service import Action, AuthService
from broast_pos.data.repositories.audit_repository import AuditEntry, AuditRepository
from broast_pos.data.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# View identifiers used by the navigation sidebar.
# Mapped to roles in _VIEW_ACCESS below.
VIEW_POS = "pos"
VIEW_TRACKING = "tracking"
VIEW_DELIVERY = "delivery"
VIEW_REPORTS = "reports"
VIEW_PRODUCTS = "products"
VIEW_FINANCIAL = "financial"
VIEW_USERS = "users"

_VIEW_ACCESS: Dict[UserRole, List[str]] = {
    UserRole.CASHIER: [VIEW_POS, VIEW_TRACKING, VIEW_DELIVERY],
    UserRole.MANAGER: [
        VIEW_POS, VIEW_TRACKING, VIEW_DELIVERY,
        VIEW_REPORTS, VIEW_PRODUCTS, VIEW_FINANCIAL,
    ],
    UserRole.ADMIN: [
        VIEW_POS, VIEW_TRACKING, VIEW_DELIVERY,
        VIEW_REPORTS, VIEW_PRODUCTS, VIEW_FINANCIAL,
        VIEW_USERS,
    ],
}


class PermissionsController:
    """Feature controller for user management and access control.

    This controller is the single integration point that the UI layer
    calls for anything related to users, permissions, or audit trails.
    """

    def __init__(
        self,
        auth_service: Optional[AuthService] = None,
        user_repo: Optional[UserRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
    ) -> None:
        self._auth = auth_service or AuthService()
        self._users = user_repo or UserRepository()
        self._audit = audit_repo or AuditRepository()

    # ==================================================================
    # Session management (delegates to AuthService)
    # ==================================================================

    def get_login_users(self) -> List[Dict[str, Any]]:
        """Return active users for the login screen tile grid.

        Returns a list of dicts with id, display_name, avatar_path, and role
        (only the fields the login screen needs).
        """
        users = self._auth.get_all_users()
        return [
            {
                "id": u.id,
                "display_name": u.display_name,
                "avatar_path": u.avatar_path,
                "role": u.role.value,
            }
            for u in users
        ]

    def login(self, user_id: int, pin: str) -> User:
        """Authenticate user by ID + PIN.

        Returns the logged-in User.
        Raises ValueError if credentials are invalid.
        """
        return self._auth.login(user_id, pin)

    def logout(self) -> None:
        """End the current session — return to login screen."""
        self._auth.logout()

    def get_current_user(self) -> Optional[User]:
        """Return the currently logged-in user, or None."""
        return self._auth.get_current_user()

    def is_logged_in(self) -> bool:
        """Check if there is an active session."""
        return self._auth.is_logged_in()

    # ==================================================================
    # Manager override flow
    # ==================================================================

    def request_override(self, pin: str, action: Action) -> Dict[str, Any]:
        """Verify a manager/admin PIN for a restricted action.

        This is the method the PinDialog calls. It verifies the PIN,
        checks permission for the specific action, and returns a result
        dict that the UI can use.

        Returns:
            {
                "authorized": True,
                "manager_id": int,
                "manager_name": str,
            }

        Raises:
            PermissionError: if PIN is invalid or user lacks the permission.
        """
        manager = self._auth.verify_pin(pin)
        if manager is None:
            raise PermissionError("PIN غير صحيح أو ليس لديك صلاحية")

        # Check if this specific manager has the required action permission
        if not self._auth.check_permission(manager, action):
            raise PermissionError(
                f"المستخدم {manager.display_name} ليس لديه صلاحية لهذا الإجراء"
            )

        logger.info(
            "Override authorized: %s by %s (id=%d)",
            action.value, manager.display_name, manager.id,
        )

        return {
            "authorized": True,
            "manager_id": manager.id,
            "manager_name": manager.display_name,
        }

    # ==================================================================
    # Navigation access control
    # ==================================================================

    def get_allowed_views(self, role: UserRole) -> List[str]:
        """Return the view identifiers a role is allowed to access.

        Used by main_window.py to show/hide sidebar navigation items.
        """
        return _VIEW_ACCESS.get(role, [VIEW_POS])

    def get_allowed_views_for_current_user(self) -> List[str]:
        """Convenience: allowed views for the logged-in user."""
        user = self._auth.get_current_user()
        if user is None:
            return []
        return self.get_allowed_views(user.role)

    # ==================================================================
    # User management (admin-only operations)
    # ==================================================================

    def get_all_users(self) -> List[User]:
        """Return all active users for the user management screen."""
        return self._users.get_all_active()

    def get_users_by_role(self, role: UserRole) -> List[User]:
        """Return active users filtered by role."""
        return self._users.get_by_role(role)

    def create_user(
        self,
        username: str,
        display_name: str,
        pin: str,
        role: str,
        admin_pin: str,
        cashier_slot: Optional[int] = None,
        avatar_path: Optional[str] = None,
    ) -> User:
        """Create a new user — requires admin PIN.

        Args:
            role: "cashier", "manager", or "admin".
            cashier_slot: 1 or 2 (None for drivers).

        Returns:
            The created User with id set.

        Raises:
            PermissionError: if admin PIN is invalid.
            ValueError: if username taken, PIN taken, or invalid role.
        """
        # Verify admin authorization
        admin = self._verify_admin_pin(admin_pin)

        # Validate role
        try:
            user_role = UserRole(role)
        except ValueError:
            raise ValueError(
                f"الدور غير صحيح — يجب أن يكون: cashier, manager, admin"
            )

        # Validate username uniqueness
        existing = self._users.get_by_username(username)
        if existing is not None:
            raise ValueError(f"اسم المستخدم '{username}' مستخدم بالفعل")

        # Validate PIN uniqueness
        pin_hash = self._auth.hash_pin(pin)
        if self._users.pin_exists(pin_hash):
            raise ValueError("رمز PIN مستخدم بالفعل — يجب أن يكون فريداً")

        # Create user
        user = User(
            username=username,
            display_name=display_name,
            pin_hash=pin_hash,
            role=user_role,
            cashier_slot=cashier_slot,
            avatar_path=avatar_path,
            is_active=True,
        )
        saved = self._users.save(user)

        # Audit trail
        self._audit.log(
            event_type="user_created",
            user_id=admin.id,
            user_name=admin.display_name,
            details={
                "created_user_id": saved.id,
                "username": username,
                "display_name": display_name,
                "role": role,
                "cashier_slot": cashier_slot,
            },
        )

        logger.info("User created: %s (id=%d) by %s", username, saved.id, admin.display_name)
        return saved

    def update_user(
        self,
        user_id: int,
        admin_pin: str,
        display_name: Optional[str] = None,
        role: Optional[str] = None,
        cashier_slot: Optional[int] = None,
        avatar_path: Optional[str] = None,
    ) -> User:
        """Update user fields — requires admin PIN.

        Only provided (non-None) fields are updated.

        Raises:
            PermissionError: if admin PIN is invalid.
            ValueError: if user not found or invalid role.
        """
        admin = self._verify_admin_pin(admin_pin)

        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("المستخدم غير موجود")

        changes: Dict[str, Any] = {}

        if display_name is not None:
            changes["display_name"] = (user.display_name, display_name)
            user.display_name = display_name

        if role is not None:
            try:
                new_role = UserRole(role)
            except ValueError:
                raise ValueError("الدور غير صحيح")
            changes["role"] = (user.role.value, role)
            user.role = new_role

        if cashier_slot is not None:
            changes["cashier_slot"] = (user.cashier_slot, cashier_slot)
            user.cashier_slot = cashier_slot

        if avatar_path is not None:
            changes["avatar_path"] = (user.avatar_path, avatar_path)
            user.avatar_path = avatar_path

        if not changes:
            return user  # Nothing to update

        saved = self._users.save(user)

        # Audit trail
        self._audit.log(
            event_type="user_updated",
            user_id=admin.id,
            user_name=admin.display_name,
            details={
                "updated_user_id": user_id,
                "username": user.username,
                "changes": {k: {"from": v[0], "to": v[1]} for k, v in changes.items()},
            },
        )

        logger.info("User updated: %s (id=%d) by %s", user.username, user_id, admin.display_name)
        return saved

    def deactivate_user(self, user_id: int, admin_pin: str) -> None:
        """Soft-delete a user — requires admin PIN.

        Raises:
            PermissionError: if admin PIN is invalid.
            ValueError: if user not found or trying to deactivate self.
        """
        admin = self._verify_admin_pin(admin_pin)

        if admin.id == user_id:
            raise ValueError("لا يمكنك تعطيل حسابك الخاص")

        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("المستخدم غير موجود")

        self._users.delete(user_id)

        # Audit trail
        self._audit.log(
            event_type="user_deactivated",
            user_id=admin.id,
            user_name=admin.display_name,
            details={
                "deactivated_user_id": user_id,
                "username": user.username,
                "display_name": user.display_name,
            },
        )

        logger.info(
            "User deactivated: %s (id=%d) by %s",
            user.username, user_id, admin.display_name,
        )

    def reset_pin(self, user_id: int, new_pin: str, admin_pin: str) -> None:
        """Reset a user's PIN — requires admin PIN.

        No way to recover a forgotten PIN. Admin must set a new one.

        Raises:
            PermissionError: if admin PIN is invalid.
            ValueError: if user not found or new PIN already taken.
        """
        admin = self._verify_admin_pin(admin_pin)

        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValueError("المستخدم غير موجود")

        new_pin_hash = self._auth.hash_pin(new_pin)

        # Check uniqueness (exclude this user's own current hash)
        if self._users.pin_exists(new_pin_hash, exclude_user_id=user_id):
            raise ValueError("رمز PIN مستخدم بالفعل — يجب أن يكون فريداً")

        user.pin_hash = new_pin_hash
        self._users.save(user)

        # Audit trail (do NOT log the PIN itself)
        self._audit.log(
            event_type="pin_reset",
            user_id=admin.id,
            user_name=admin.display_name,
            details={
                "target_user_id": user_id,
                "username": user.username,
            },
        )

        logger.info(
            "PIN reset for %s (id=%d) by %s",
            user.username, user_id, admin.display_name,
        )

    # ==================================================================
    # Audit log queries
    # ==================================================================

    def get_audit_logs(self, date_str: str) -> List[AuditEntry]:
        """All audit entries for a date (YYYY-MM-DD)."""
        return self._audit.get_logs_for_date(date_str)

    def get_user_audit_trail(self, user_id: int, limit: int = 50) -> List[AuditEntry]:
        """Audit trail for a specific user."""
        return self._audit.get_logs_by_user(user_id, limit)

    def get_order_audit_trail(self, order_id: int) -> List[AuditEntry]:
        """Audit trail for a specific order."""
        return self._audit.get_logs_for_order(order_id)

    def get_audit_by_event_type(
        self,
        event_type: str,
        date_str: Optional[str] = None,
    ) -> List[AuditEntry]:
        """All audit entries of a specific type, optionally for a date."""
        return self._audit.get_logs_by_event_type(event_type, date_str)

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _verify_admin_pin(self, pin: str) -> User:
        """Verify a PIN belongs to an ADMIN user.

        User management requires ADMIN role specifically,
        not just MANAGER.

        Returns the admin User.
        Raises PermissionError if invalid.
        """
        pin_hash = self._auth.hash_pin(pin)
        user = self._users.get_by_pin(pin_hash)

        if user is None:
            raise PermissionError("PIN غير صحيح")

        if user.role != UserRole.ADMIN:
            raise PermissionError("هذا الإجراء يتطلب صلاحيات مدير النظام (Admin)")

        return user
