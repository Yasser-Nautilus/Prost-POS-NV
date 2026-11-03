# 🔐 feature/user_permissions — PROGRESS

## 🎯 Goal

Enforce **role-based actions** with manager PIN overrides. Prevent unauthorized access to sensitive operations (cancel, discount, management screens).

---

## ✅ Tasks

### 1. Role Model

- **What**: Define clear role hierarchy with permissions
- **Details**:
  - **Cashier**: create orders, view tracking, view delivery status
  - **Manager**: all cashier permissions + cancel orders, apply discounts, view reports, manage products, settle drivers
  - **Admin**: all manager permissions + manage users, system configuration
  - Roles stored in `UserRole` enum
- **Why**: Cashiers should never be able to cancel orders or apply discounts without supervision. This prevents revenue leakage.
- **Touches**: `core/models/user.py`, `core/services/auth_service.py`
- **Status**: `Done`
  - `UserRole` enum (CASHIER, MANAGER, ADMIN) in `core/models/user.py`
  - Permission helpers: `has_manager_access`, `can_cancel_order`, `can_authorise_discount`
  - `Action` enum with 10 restricted actions in `auth_service.py`
  - `_PERMISSIONS` dict mapping roles → allowed actions

### 2. PIN Storage (Hashed)

- **What**: Store user PINs as hashed values, never plain text
- **Details**:
  - Use SHA-256 hash for PIN storage
  - `hash_pin(raw_pin) → hashed_pin` utility function
  - Comparison: hash the input PIN and compare to stored hash
  - No way to recover a forgotten PIN — admin must reset it
- **Why**: Even for a local restaurant system, plain text PINs are a security gap. If the database file is copied or accessed, PINs should be unreadable.
- **Touches**: `core/services/auth_service.py`, `data/repositories/user_repository.py`
- **Status**: `Done`
  - `AuthService.hash_pin()` — SHA-256 hex digest
  - `UserRepository.get_by_pin(pin_hash)` — lookup by hashed PIN
  - `UserRepository.pin_exists(pin_hash, exclude_user_id)` — uniqueness validation
  - Seed data hashes PINs at insert time

### 3. Manager Override Flow

- **What**: PIN dialog system for restricted actions
- **Details**:
  - Cashier triggers restricted action (cancel, discount)
  - System shows PIN dialog (modal)
  - Cashier enters manager's PIN (not their own)
  - System verifies: PIN valid + user has manager/admin role
  - If valid: action proceeds with audit trail
  - If invalid: show error, action blocked
  - The override is per-action — it doesn't change the logged-in user
- **Why**: This is the standard "manager override" pattern in production POS systems. The manager doesn't need to log in — they just enter their PIN when a cashier requests approval.
- **Touches**: `ui/components/pin_dialog.py`, `core/services/order_service.py`
- **Status**: `Done`
  - `AuthService.verify_pin(pin)` — returns manager/admin user or None
  - `PermissionsController.request_override(pin, action)` — orchestrates verification + permission check
  - `OrderService._verify_manager_pin()` — used by cancel, discount, item removal
  - `FinancialService._verify_manager_pin()` — used by shift transfer/close
  - UI component (`pin_dialog.py`) deferred to `ui/components` phase

### 4. Audit Logging

- **What**: Log every sensitive action with user identity and timestamp
- **Details**:
  - Events to log:
    - Order cancelled: who, when, which order, reason
    - Discount applied: who approved, amount, which order
    - Shift opened/closed: who, when, amounts
    - User created/modified: who changed what
  - Storage: dedicated `audit_log` table in SQLite
  - Fields: event_type, user_id, user_name, order_id (if applicable), details (JSON), timestamp
  - Viewable by admin in a future audit screen
- **Why**: When the manager asks "who cancelled order #1234?" or "who applied a discount today?", the audit log has the answer. Without it, there's no accountability.
- **Touches**: `data/repositories/audit_repository.py`, `core/services/order_service.py`, `core/services/financial_service.py`
- **Status**: `Done`
  - `AuditRepository.log()` — write-only, immutable
  - `AuditRepository.get_logs_for_date()`, `get_logs_for_order()`, `get_logs_by_user()`, `get_logs_by_event_type()` — query methods
  - `OrderService` logs: order_cancelled, discount_applied, item_removed
  - `FinancialService` logs: shift_opened, shift_closed, shift_transferred, expense_recorded
  - `PermissionsController` logs: user_created, user_updated, user_deactivated, pin_reset

### 5. Navigation Access Control

- **What**: Show/hide navigation items based on user role
- **Details**:
  - Cashier sees: POS, Tracking, Delivery
  - Manager sees: + Reports, Products, Financial
  - Admin sees: + Users
  - Implemented in `main_window.py` sidebar based on `current_user.role`
- **Why**: Cashiers don't need to see management screens — it reduces confusion and prevents accidental changes.
- **Touches**: `ui/windows/main_window.py`
- **Status**: `Done`
  - `PermissionsController.get_allowed_views(role)` — returns view identifiers per role
  - `PermissionsController.get_allowed_views_for_current_user()` — convenience method
  - `_VIEW_ACCESS` dict: role → [view_ids]
  - UI wiring deferred to `main_window.py` build phase

---

## 📝 Notes

- Prevent revenue leakage via uncontrolled discounts and cancellations
- Manager override does NOT change the active session — it's a one-time approval
- Audit logs are write-only in normal operation — no deletion
- User management operations require ADMIN role specifically (not just MANAGER)
- PIN dialog UI component (`pin_dialog.py`) will be built in the `ui/components` phase
- Navigation sidebar filtering will be wired in `main_window.py` build phase
