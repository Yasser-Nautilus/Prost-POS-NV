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
- **Status**: `Not started`

### 2. PIN Storage (Hashed)

- **What**: Store user PINs as hashed values, never plain text
- **Details**:
  - Use SHA-256 hash for PIN storage
  - `hash_pin(raw_pin) → hashed_pin` utility function
  - Comparison: hash the input PIN and compare to stored hash
  - No way to recover a forgotten PIN — admin must reset it
- **Why**: Even for a local restaurant system, plain text PINs are a security gap. If the database file is copied or accessed, PINs should be unreadable.
- **Touches**: `core/services/auth_service.py`, `data/repositories/user_repository.py`
- **Status**: `Not started`

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
- **Status**: `Not started`

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
- **Status**: `Not started`

### 5. Navigation Access Control

- **What**: Show/hide navigation items based on user role
- **Details**:
  - Cashier sees: POS, Tracking, Delivery
  - Manager sees: + Reports, Products, Financial
  - Admin sees: + Users
  - Implemented in `main_window.py` sidebar based on `current_user.role`
- **Why**: Cashiers don't need to see management screens — it reduces confusion and prevents accidental changes.
- **Touches**: `ui/windows/main_window.py`
- **Status**: `Not started`

---

## 📝 Notes

- Prevent revenue leakage via uncontrolled discounts and cancellations
- Manager override does NOT change the active session — it's a one-time approval
- Audit logs are write-only in normal operation — no deletion
- Future: audit log viewer screen for admin
