# Core Services — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** Actual implementation files in `broast_pos/core/services/`

---

## Overview

The service layer contains **11 service files** implementing all business logic. Services are instantiated in `main.py` with explicit dependency injection (repositories and other services passed as constructor arguments).

---

## Services

### 1. OrderService (`order_service.py` — 893 lines)

**Status:** Implemented

The largest service, responsible for the full order lifecycle.

**Key responsibilities:**
- **Order creation** with type-aware validation (dine-in, takeaway, delivery, pickup).
- **7-state machine** with type-aware valid transitions enforced programmatically.
- **Order amendment** (modify items on non-terminal orders).
- **Order completion** with payment method recording.
- **Order cancellation** with reason tracking.
- **Cash ledger integration:** Creates `SALE_CASH` / `SALE_CARD` / `SALE_MOBILE` entries on completion; creates `REVERSAL` entries on cancellation of previously completed orders.
- **Unpaid completion policy:** Orders can be completed without prior payment flag.
- **Takeaway auto-complete:** `auto_complete_expired_takeaways()` method called by a 60-second QTimer in `main.py`.
- **Discount computation** via `compute_discount` policy.
- **Order status history** recording on every transition.
- **Audit logging** on create, amend, complete, cancel, and status change.

**Public API (key methods):**
- `create_order(order_data, user) → Order`
- `get_order(order_id) → Order`
- `get_orders(filters) → List[Order]`
- `update_order_status(order_id, new_status, user) → Order`
- `amend_order(order_id, items, user) → Order`
- `complete_order(order_id, payment_method, user) → Order`
- `cancel_order(order_id, reason, user) → Order`
- `auto_complete_expired_takeaways()`

---

### 2. AuthService (`auth_service.py` — 514 lines)

**Status:** Implemented

Handles all authentication and user management.

**Key responsibilities:**
- **PIN authentication** using PBKDF2-HMAC-SHA256 with per-user salt and application-level pepper.
- **Legacy SHA-256 auto-upgrade:** Users with `pin_salt=NULL` are verified against the legacy hash and transparently upgraded to PBKDF2 on successful login.
- **Brute-force throttling:** Tracks failed login attempts per user with configurable lockout.
- **User CRUD:** Create, update, deactivate users.
- **PIN changes** with re-hashing.
- **Role-based permission checking.**
- **Permission definitions:** Each role has a set of allowed permissions.
  - Manager permissions include `MANAGE_USERS` (line 88).

**Public API (key methods):**
- `authenticate(username, pin) → User`
- `create_user(user_data, acting_user) → User`
- `update_user(user_id, updates, acting_user) → User`
- `change_pin(user_id, new_pin, acting_user)`
- `deactivate_user(user_id, acting_user)`
- `has_permission(user, permission) → bool`
- `get_users() → List[User]`

> [!WARNING]
> There is an authorization inconsistency: `AuthService` grants Managers `MANAGE_USERS` permission, but `bridge.py` (lines 266, 284, 302) independently checks `role.value != "admin"` for user management operations, effectively restricting user management to Admin only regardless of AuthService permissions.

---

### 3. DeliveryService (`delivery_service.py` — 604 lines)

**Status:** Implemented

Manages the full delivery driver lifecycle.

**Key responsibilities:**
- **Driver attendance:** Clock in/out, status tracking (`AVAILABLE`, `ON_DELIVERY`, `OFF_DUTY`).
- **Trip management:** Assign orders to drivers, track pickup and delivery.
- **Trip completion:** Mark trips as delivered, record timestamps.
- **Settlement integration:** Works with `DriverSettlementService` for financial settlement.
- **Status changes through OrderService:** Delivery status transitions (e.g., `OUT_FOR_DELIVERY`, `DELIVERED`) route through `OrderService` for state machine validation.
- **Atomic transactions** for multi-step operations.

**Public API (key methods):**
- `clock_in(user_id) → DriverAttendance`
- `clock_out(user_id) → DriverAttendance`
- `get_available_drivers() → List[DriverAttendance]`
- `assign_trip(order_id, driver_id, user) → DeliveryTrip`
- `mark_picked_up(trip_id, user) → DeliveryTrip`
- `mark_delivered(trip_id, user) → DeliveryTrip`
- `get_driver_trips(driver_id) → List[DeliveryTrip]`
- `get_unsettled_trips(driver_id) → List[DeliveryTrip]`

> [!NOTE]
> A circular dependency exists: `main.py` line 144 sets `delivery_service._order_svc = order_service` after both services are constructed.

---

### 4. DriverSettlementService (`driver_settlement_service.py` — 543 lines)

**Status:** Implemented

Handles per-trip and daily financial settlement with drivers.

**Key responsibilities:**
- **Settlement preview:** Calculate what a driver owes/is owed before committing.
- **Per-trip settlement:** Settle individual delivery trips.
- **Daily settlement:** Batch-settle all unsettled trips for a driver.
- **Server-side amount calculation:** `amount_to_remit = amount_collected - delivery_fee`.
- **Cash ledger integration:** Creates `DRIVER_REMITTANCE` entries for each settlement.
- **Duplicate prevention:** Checks for already-settled trips.
- **In-transit guard:** Rejects settlement of trips with `OUT_FOR_DELIVERY` status.
- **Audit logging** for all settlements.

**Public API (key methods):**
- `preview_settlement(driver_id) → dict`
- `settle_trip(trip_id, user) → DriverSettlement`
- `settle_daily(driver_id, user) → List[DriverSettlement]`
- `get_driver_settlement_history(driver_id) → List[DriverSettlement]`

---

### 5. ReportService (`report_service.py` — 451 lines)

**Status:** Implemented

Generates financial and operational reports.

**Key responsibilities:**
- **Daily reports:** Sales summary for a specific date.
- **Shift-based reports (B-10 pattern):** Revenue and order counts grouped by cashier shift rather than calendar date.
- **Monthly reports:** Aggregated monthly statistics.
- **Yearly reports:** Aggregated yearly statistics.
- **Report formatting** for display and printing.

**Public API (key methods):**
- `get_daily_report(date) → dict`
- `get_shift_report(shift_id) → dict`
- `get_monthly_report(year, month) → dict`
- `get_yearly_report(year) → dict`

> [!NOTE]
> The B-10 shift-based reporting pattern queries by shift boundaries (open/close timestamps) rather than calendar dates, ensuring reports align with actual cashier sessions even when shifts cross midnight.

---

### 6. CashierSessionService (`cashier_session_service.py` — 398 lines)

**Status:** Implemented

Manages station-based cashier sessions with full ledger integration.

**Key responsibilities:**
- **Open session:** Assign a cashier to a station (ALL, COUNTER, DELIVERY) with an opening float.
- **Close session:** Record cash count, calculate expected cash, determine variance.
- **Station conflict prevention:** Prevents opening a session on a station that already has an active session.
- **Session handover:** Transfer a session from one cashier to another.
- **Ledger integration:** Creates `FLOAT` entry on open; variance entries on close.
- **Manager approval:** Sessions with significant variance may require manager approval.
- **Active session queries.**

**Public API (key methods):**
- `open_session(user_id, station, opening_float, user) → CashierSession`
- `close_session(session_id, closing_float, user) → CashierSession`
- `handover_session(session_id, to_user_id, user) → CashierSession`
- `get_active_sessions() → List[CashierSession]`
- `get_session(session_id) → CashierSession`

---

### 7. BusinessDayService (`business_day_service.py` — 358 lines)

**Status:** Implemented

Handles end-of-day accounting operations.

**Key responsibilities:**
- **X-Report generation:** Read-only interim report of current business day activity.
- **Z-Report generation:** Final end-of-day report that freezes the business day.
- **Business-day close:** Validates all sessions are closed, generates Z-Report, records closing.
- **Open-session guard:** Prevents closing the business day while cashier sessions are active.
- **Cashier session snapshots:** Includes per-session summaries in reports.
- **Driver fee payout entries:** Generates batch `DRIVER_FEE_PAYOUT` ledger entries during business-day close.
- **Ledger-based reconciliation:** Reports are built from cash ledger data for accuracy.

**Public API (key methods):**
- `generate_x_report() → dict`
- `generate_z_report(user) → dict`
- `close_business_day(user) → dict`

---

### 8. FinancialService (`financial_service.py` — 320 lines)

**Status:** Implemented

Manages the legacy shift lifecycle and cash transactions.

**Key responsibilities:**
- **Shift lifecycle:** Open, close, transfer shifts.
- **4 close guards:** Validates shift state before closing (open status, same user, etc.).
- **Expense recording:** Create expense entries against active shifts.
- **Invoice counter:** Sequential invoice numbering.
- **Cash transaction logging.**

**Public API (key methods):**
- `open_shift(user_id, opening_amount) → Shift`
- `close_shift(shift_id, closing_amount, user) → Shift`
- `transfer_shift(from_shift_id, to_shift_id, amount) → ShiftTransfer`
- `add_expense(shift_id, amount, description, user) → CashTransaction`
- `get_next_invoice_number() → str`

> [!NOTE]
> The legacy `ShiftDialog` in the frontend still uses `FinancialService`. The newer `CashierSessionService` is intended to replace it, but both coexist in the current codebase.

---

### 9. CustomerService (`customer_service.py` — 251 lines)

**Status:** Implemented

Manages customer records, addresses, and delivery zones.

**Key responsibilities:**
- **Phone-based lookup** for returning customers.
- **Customer CRUD.**
- **Address management** with default address selection.
- **Zone configuration** for delivery fee calculation.
- **Customer history/statistics** queries.

**Public API (key methods):**
- `find_by_phone(phone) → Customer`
- `create_customer(data) → Customer`
- `update_customer(customer_id, data) → Customer`
- `add_address(customer_id, address_data) → CustomerAddress`
- `get_zones() → List[Zone]`
- `get_customer_history(customer_id) → dict`
- `get_customer_statistics(customer_id) → dict`

---

### 10. ProductService (`product_service.py` — 195 lines)

**Status:** Implemented

Manages product catalog and categories.

**Key responsibilities:**
- **Product CRUD** with availability toggling.
- **Category CRUD** with activation/deactivation.
- **Search** by name (English and Arabic).
- **Sort order management.**

**Public API (key methods):**
- `get_products(category_id=None) → List[Product]`
- `create_product(data) → Product`
- `update_product(product_id, data) → Product`
- `get_categories() → List[Category]`
- `create_category(data) → Category`
- `update_category(category_id, data) → Category`
- `search_products(query) → List[Product]`

---

### 11. AuditService (`audit_service.py` — 168 lines)

**Status:** Implemented

Provides centralized audit logging used by all other services.

**Key responsibilities:**
- **Event logging** with user identification, entity type, entity ID, and event description.
- **Before/after snapshots** for change tracking where supported by the calling service.
- **`log_from_user()` convenience** method that extracts user information from a User object.
- **Filtered queries** by event type, date range, and entity.
- **Date-based and order-based queries** for the audit trail viewer.

**Public API (key methods):**
- `log(event_type, user_id, username, entity_type, entity_id, description, old_value, new_value)`
- `log_from_user(event_type, user, entity_type, entity_id, description, old_value, new_value)`
- `get_audit_log(filters) → List[dict]`
- `get_audit_log_for_order(order_id) → List[dict]`
- `get_audit_log_for_date(date) → List[dict]`

---

## Dependency Graph

```
OrderService
  ├── order_repository
  ├── order_status_history_repository
  ├── cash_ledger_repository
  ├── audit_service
  └── discount policy

AuthService
  └── user_repository

DeliveryService
  ├── delivery_repository
  ├── order_service (circular, set post-construction)
  └── audit_service

DriverSettlementService
  ├── driver_settlement_repository
  ├── delivery_repository
  ├── cash_ledger_repository
  └── audit_service

CashierSessionService
  ├── cashier_session_repository
  ├── cash_ledger_repository
  └── audit_service

BusinessDayService
  ├── cashier_session_service
  ├── cash_ledger_repository
  ├── delivery_repository
  └── audit_service

FinancialService
  ├── financial_repository
  └── audit_service

ReportService
  └── report_repository

CustomerService
  └── customer_repository

ProductService
  └── product_repository

AuditService
  └── audit_repository
```

---

## Summary

| Service | File | Lines | Status |
|---|---|---|---|
| OrderService | `order_service.py` | 893 | Implemented |
| AuthService | `auth_service.py` | 514 | Implemented |
| DeliveryService | `delivery_service.py` | 604 | Implemented |
| DriverSettlementService | `driver_settlement_service.py` | 543 | Implemented |
| ReportService | `report_service.py` | 451 | Implemented |
| CashierSessionService | `cashier_session_service.py` | 398 | Implemented |
| BusinessDayService | `business_day_service.py` | 358 | Implemented |
| FinancialService | `financial_service.py` | 320 | Implemented |
| CustomerService | `customer_service.py` | 251 | Implemented |
| ProductService | `product_service.py` | 195 | Implemented |
| AuditService | `audit_service.py` | 168 | Implemented |
| **Total** | **11 files** | **4,696** | |
