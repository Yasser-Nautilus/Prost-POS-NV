# User Permissions — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** `auth_service.py`, `user.py`, `permissions_controller.py`, `bridge.py`

---

## Overview

The user permissions system provides PIN-based authentication with PBKDF2 hashing, role-based access control, brute-force protection, and user management.

---

## Authentication

### PIN Hashing

**Status:** Implemented

| Property | Detail |
|---|---|
| Algorithm | PBKDF2-HMAC-SHA256 |
| Salt | Per-user random salt stored in `users.pin_salt` |
| Pepper | Application-level secret from `BROAST_PIN_PEPPER` environment variable |
| Legacy Support | Auto-upgrade from SHA-256 on successful login |

**Legacy auto-upgrade flow:**
1. User attempts login.
2. If `pin_salt` is `NULL`, verify against legacy SHA-256 hash.
3. On success, generate a new random salt, hash the PIN with PBKDF2 + salt + pepper, and update the user record.
4. Subsequent logins use PBKDF2 directly.

### Brute-Force Throttling

**Status:** Implemented

- Tracks failed login attempts per user.
- Configurable lockout after repeated failures.
- Prevents rapid PIN guessing attacks.

---

## Roles & Permissions

### UserRole (Enum)

| Role | Description |
|---|---|
| `CASHIER` | Basic POS operations |
| `MANAGER` | Extended access including reports, settlement, products, audit |
| `ADMIN` | Full system access including user management |

### Navigation Access (from `App.tsx`)

| Tab | Cashier | Manager | Admin |
|---|---|---|---|
| POS | ✅ | ✅ | ✅ |
| Delivery | ✅ | ✅ | ✅ |
| Tracking | ✅ | ✅ | ✅ |
| Settlement | ❌ | ✅ | ✅ |
| Reports | ❌ | ✅ | ✅ |
| Products | ❌ | ✅ | ✅ |
| Audit | ❌ | ✅ | ✅ |
| Users | ❌ | ❌ | ✅ |

### Manager Permissions

As defined in `AuthService` (line 88), Manager permissions include:
- `VIEW_REPORTS`
- `MANAGE_PRODUCTS`
- `VIEW_AUDIT`
- `MANAGE_USERS` ← Defined in AuthService
- Other operational permissions

> [!WARNING]
> **Authorization Inconsistency:** `AuthService` grants Managers the `MANAGE_USERS` permission, but `bridge.py` (lines 266, 284, 302) independently checks `self._current_user.role.value != "admin"` for user management operations (create, update, deactivate). This bridge-level check overrides the AuthService permission, effectively restricting user management to Admin only. The `PermissionsController` and `UsersView` frontend tab also enforce Admin-only access. This inconsistency should be resolved by either:
> 1. Removing `MANAGE_USERS` from Manager permissions in AuthService, or
> 2. Updating the bridge and frontend to allow Manager access to user management.

---

## User Management

### PermissionsController (`permissions_controller.py` — 437 lines)

**Status:** Implemented

**Key actions:**
- User CRUD (create, update, deactivate).
- PIN changes.
- Authentication (login/logout).
- Audit log queries for user operations.
- Navigation access control based on role.

### Bridge Authorization Guard

**Status:** Implemented

The `POSBridge` checks `self._current_user` before dispatching most actions. Unauthenticated requests are rejected with an error response.

---

## Frontend Integration

### LoginView

**Status:** Implemented

- PIN-based login with numeric keypad.
- User selection.

### UsersView

**Status:** Implemented

- User list with role and status.
- Create/edit/deactivate users.
- PIN change functionality.
- Access restricted to Admin role.

### PinDialog

**Status:** Implemented

- Reusable PIN entry component used for authentication and PIN changes.

---

## Seed Admin

The default admin user is seeded with a legacy SHA-256 hash (no salt). The hash is auto-upgraded to PBKDF2 on first login.

> [!CAUTION]
> The default admin PIN should be changed immediately after first deployment. The seed uses a legacy hash without salt, which is less secure than the PBKDF2 scheme used for all other operations.

---

## Summary

| Feature | Status | Notes |
|---|---|---|
| PBKDF2-HMAC-SHA256 hashing | Implemented | With per-user salt and app pepper |
| Legacy SHA-256 auto-upgrade | Implemented | Transparent on login |
| Brute-force throttling | Implemented | Per-user tracking |
| Role-based access control | Implemented | Cashier / Manager / Admin |
| Navigation access by role | Implemented | Enforced in App.tsx |
| User CRUD | Implemented | Admin only (see inconsistency) |
| PIN changes | Implemented | |
| Audit log queries | Implemented | |
| Login/Logout | Implemented | |
| Frontend (LoginView) | Implemented | |
| Frontend (UsersView) | Implemented | Admin only |
| Bridge auth guard | Implemented | |
| Manager MANAGE_USERS | **Partially Implemented** | Defined in AuthService but blocked by bridge |
