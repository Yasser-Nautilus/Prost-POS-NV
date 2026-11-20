# Core Models — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** Actual implementation files in `broast_pos/core/models/`

---

## Overview

The core models define the domain types used throughout the application. All models are Python `@dataclass` classes or enums. There are **10 model files** plus **1 policy file** (`policies/discount.py`).

---

## Models

### 1. Order (`order.py` — 192 lines)

**Status:** Implemented

Defines the complete order domain:

#### OrderType (Enum — 4 values)
- `DINE_IN`
- `TAKEAWAY`
- `DELIVERY`
- `PICKUP`

#### OrderStatus (Enum — 7 values)
```
NEW → PREPARING → READY → OUT_FOR_DELIVERY → DELIVERED → COMPLETED
                                                          ↗
Any non-terminal state ──────────────────────→ CANCELLED
```

- `NEW` — Order created, not yet sent to kitchen.
- `PREPARING` — Sent to kitchen, being prepared.
- `READY` — Prepared, awaiting pickup or delivery dispatch.
- `OUT_FOR_DELIVERY` — Assigned to a delivery driver, in transit.
- `DELIVERED` — Driver confirmed delivery (delivery orders only).
- `COMPLETED` — Order finalized and paid.
- `CANCELLED` — Order cancelled at any non-terminal stage.

Valid transitions are type-aware and enforced by `OrderService`:
- Dine-in/Takeaway/Pickup: `NEW → PREPARING → READY → COMPLETED` (skip delivery states)
- Delivery: `NEW → PREPARING → READY → OUT_FOR_DELIVERY → DELIVERED → COMPLETED`
- `CANCELLED` is reachable from any non-terminal status.

#### PaymentMethod (Enum — 3 values)
- `CASH`
- `CARD`
- `MOBILE`

#### Order (Dataclass)
Key fields: `id`, `order_number`, `order_type`, `status`, `items`, `subtotal`, `discount_amount`, `discount_percentage`, `tax_amount`, `total`, `payment_method`, `customer_id`, `table_number`, `notes`, `created_at`, `updated_at`, `created_by`, `updated_by`, `is_paid`.

#### OrderItem (Dataclass)
Fields: `id`, `order_id`, `product_id`, `product_name`, `product_name_ar`, `quantity`, `unit_price`, `total_price`, `notes`, `is_printed`.

---

### 2. User (`user.py` — 63 lines)

**Status:** Implemented

#### UserRole (Enum)
- `CASHIER`
- `MANAGER`
- `ADMIN`

#### User (Dataclass)
Fields: `id`, `username`, `pin_hash`, `pin_salt`, `role`, `full_name`, `is_active`, `created_at`.

> [!NOTE]
> The `pin_salt` field supports the PBKDF2-HMAC-SHA256 hashing scheme. Users with `pin_salt=NULL` use the legacy SHA-256 hash and are auto-upgraded on next successful login.

---

### 3. Product (`product.py` — 45 lines)

**Status:** Implemented

#### Product (Dataclass)
Fields: `id`, `name`, `name_ar`, `category_id`, `price`, `is_available`, `sort_order`, `created_at`.

#### Category (Dataclass)
Fields: `id`, `name`, `name_ar`, `sort_order`, `is_active`, `created_at`.

---

### 4. Customer (`customer.py` — 60 lines)

**Status:** Implemented

#### Customer (Dataclass)
Fields: `id`, `name`, `phone`, `notes`, `created_at`.

#### CustomerAddress (Dataclass)
Fields: `id`, `customer_id`, `label`, `address_text`, `zone_id`, `is_default`, `created_at`.

#### Zone (Dataclass)
Fields: `id`, `name`, `name_ar`, `delivery_fee`, `is_active`.

---

### 5. Delivery (`delivery.py` — 82 lines)

**Status:** Implemented

#### DriverStatus (Enum)
- `AVAILABLE`
- `ON_DELIVERY`
- `OFF_DUTY`

#### DeliveryTrip (Dataclass)
Fields: `id`, `order_id`, `driver_id`, `driver_name`, `status`, `assigned_at`, `picked_up_at`, `delivered_at`, `delivery_fee`, `is_settled`, `notes`.

#### DriverAttendance (Dataclass)
Fields: `id`, `user_id`, `driver_name`, `clock_in`, `clock_out`, `status`.

---

### 6. Financial (`financial.py` — 134 lines)

**Status:** Implemented

#### Shift (Dataclass)
Fields: `id`, `user_id`, `cashier_name`, `opening_amount`, `closing_amount`, `expected_amount`, `variance`, `status`, `opened_at`, `closed_at`, `notes`.

#### ShiftTransfer (Dataclass)
Fields: `id`, `from_shift_id`, `to_shift_id`, `amount`, `transferred_at`, `notes`.

#### CashTransaction (Dataclass)
Fields: `id`, `shift_id`, `type`, `amount`, `reference`, `description`, `created_at`, `created_by`.

#### ShiftSummary (Dataclass)
Fields: `total_orders`, `cash_sales`, `card_sales`, `mobile_sales`, `total_sales`, `total_expenses`, `net_cash`.

> [!NOTE]
> `ShiftSummary` distinguishes `cash_sales` from `total_sales`, enabling cash-only reconciliation.

---

### 7. Audit (`audit.py` — 51 lines)

**Status:** Implemented

#### AuditEventType (Constants Class)
Defines string constants for all auditable events:

- Order events: `ORDER_CREATED`, `ORDER_UPDATED`, `ORDER_CANCELLED`, `ORDER_COMPLETED`, `ORDER_STATUS_CHANGED`, `ORDER_AMENDED`
- User events: `USER_CREATED`, `USER_UPDATED`, `USER_DEACTIVATED`
- Auth events: `LOGIN`, `LOGOUT`, `LOGIN_FAILED`
- Financial events: `SHIFT_OPENED`, `SHIFT_CLOSED`, `EXPENSE_ADDED`, `CASH_TRANSACTION`
- Delivery events: `DRIVER_CLOCKED_IN`, `DRIVER_CLOCKED_OUT`, `TRIP_ASSIGNED`, `TRIP_COMPLETED`
- Product events: `PRODUCT_CREATED`, `PRODUCT_UPDATED`, `CATEGORY_CREATED`, `CATEGORY_UPDATED`
- Settlement events: `DRIVER_SETTLEMENT`
- Session events: `SESSION_OPENED`, `SESSION_CLOSED`, `SESSION_HANDOVER`

> [!NOTE]
> `AuditEventType` is a constants class (not an Enum). Event types are plain string values.

---

### 8. Cashier Session (`cashier_session.py` — 131 lines)

**Status:** Implemented

#### Station (Enum — 3 values)
- `ALL` — Handles all order types.
- `COUNTER` — Handles dine-in, takeaway, and pickup orders.
- `DELIVERY` — Handles delivery orders only.

#### CashierSession (Dataclass)
Fields: `id`, `user_id`, `cashier_name`, `station`, `opening_float`, `closing_float`, `expected_cash`, `variance`, `status`, `opened_at`, `closed_at`, `closed_by`, `notes`, `handover_to_session_id`.

#### LedgerEntryType (Enum — 10 values)
- `SALE_CASH` — Cash sale recorded.
- `SALE_CARD` — Card sale recorded.
- `SALE_MOBILE` — Mobile payment sale recorded.
- `REVERSAL` — Order cancellation reversal.
- `EXPENSE` — Cash expense payout.
- `CASH_IN` — Manual cash deposit.
- `CASH_OUT` — Manual cash withdrawal.
- `FLOAT` — Opening float for a session.
- `DRIVER_REMITTANCE` — Cash collected by driver, returned to register.
- `DRIVER_FEE_PAYOUT` — Delivery fee paid to driver.

#### CashLedgerEntry (Dataclass)
Fields: `id`, `session_id`, `entry_type`, `amount_piasters`, `order_id`, `trip_id`, `expense_id`, `actor_user_id`, `actor_name`, `approval_user_id`, `approval_name`, `reference`, `notes`, `created_at`.

> [!IMPORTANT]
> `amount_piasters` uses integer storage to avoid floating-point precision errors. Positive values represent cash inflow; negative values represent cash outflow. The cash ledger table is append-only with database-level UPDATE and DELETE triggers that raise errors.

---

### 9. Driver Settlement (`driver_settlement.py` — 47 lines)

**Status:** Implemented

#### DriverSettlement (Dataclass)
Fields: `id`, `driver_id`, `driver_name`, `trip_id`, `order_id`, `order_total_piasters`, `delivery_fee_piasters`, `amount_collected_piasters`, `amount_to_remit_piasters`, `settled_by_user_id`, `settled_by_name`, `settled_at`, `notes`.

> [!NOTE]
> All monetary fields use integer piasters for consistency with the cash ledger.

---

### 10. Order Status History (`order_status_history.py` — 27 lines)

**Status:** Implemented

#### OrderStatusHistory (Dataclass)
Fields: `id`, `order_id`, `old_status`, `new_status`, `changed_by`, `changed_at`, `notes`.

Provides an immutable audit trail of every order status transition.

---

## Policies

### Discount Policy (`core/policies/discount.py` — 64 lines)

**Status:** Implemented

#### `compute_discount(subtotal, discount_percentage, discount_amount)`

Centralized discount computation with the following behavior:
- Uses `Decimal` arithmetic for precision.
- If both `discount_percentage` and `discount_amount` are provided, `discount_percentage` takes precedence.
- Returns the calculated discount amount, clamped to `[0, subtotal]`.
- Used by `OrderService` during order creation and amendment.

---

## Summary

| Model File | Types Defined | Status |
|---|---|---|
| `order.py` | Order, OrderItem, OrderType, OrderStatus, PaymentMethod | Implemented |
| `user.py` | User, UserRole | Implemented |
| `product.py` | Product, Category | Implemented |
| `customer.py` | Customer, CustomerAddress, Zone | Implemented |
| `delivery.py` | DeliveryTrip, DriverAttendance, DriverStatus | Implemented |
| `financial.py` | Shift, ShiftTransfer, CashTransaction, ShiftSummary | Implemented |
| `audit.py` | AuditEventType | Implemented |
| `cashier_session.py` | Station, CashierSession, LedgerEntryType, CashLedgerEntry | Implemented |
| `driver_settlement.py` | DriverSettlement | Implemented |
| `order_status_history.py` | OrderStatusHistory | Implemented |
| `policies/discount.py` | compute_discount function | Implemented |
