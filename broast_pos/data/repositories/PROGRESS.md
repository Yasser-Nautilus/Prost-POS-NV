# Repositories — Progress

> **Last Updated:** 2026-11-26
> **Source of Truth:** Actual implementation files in `broast_pos/data/repositories/`

---

## Overview

The repository layer contains **12 repository files** (plus `base_repository.py`) providing persistence for all domain models. All repositories extend `BaseRepository`, which provides access to the shared `DatabaseConnection` singleton.

---

## Repositories

### 1. OrderRepository (`order_repository.py` — 509 lines)

**Status:** Implemented

The largest repository, handling full order persistence.

**Key responsibilities:**
- Full CRUD for orders and order items.
- **Batch item loading:** `_load_items_for_orders()` loads items for multiple orders in a single query, avoiding N+1 queries.
- **Shift-based report queries:** Queries filtered by shift open/close timestamps rather than calendar dates.
- **Business-date handling:** Date-range queries for reporting.
- **Status filtering** and pagination.
- **Order number generation.**

**Key methods:**
- `create(order) → Order`
- `update(order) → Order`
- `get_by_id(order_id) → Order`
- `get_all(filters) → List[Order]`
- `get_orders_for_shift(shift_id, opened_at, closed_at) → List[Order]`
- `get_orders_by_date_range(start, end) → List[Order]`
- `get_next_order_number() → int`

---

### 2. ProductRepository (`product_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- Product and category CRUD.
- Product search by name (English and Arabic).
- Sort order management.
- Availability toggling.

---

### 3. CustomerRepository (`customer_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- Customer CRUD.
- Phone-based lookup.
- Address management (create, update, delete, set default).
- Zone CRUD.

---

### 4. UserRepository (`user_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- User CRUD.
- Username-based lookup for authentication.
- PIN hash and salt updates.
- Active/inactive user filtering.

---

### 5. DeliveryRepository (`delivery_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- Delivery trip CRUD.
- Driver attendance (clock in/out) records.
- Trip status updates.
- Unsettled trip queries.
- Driver availability queries.

---

### 6. FinancialRepository (`financial_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- Shift CRUD.
- Shift transfer records.
- Cash transaction persistence.
- Active shift queries.

---

### 7. ReportRepository (`report_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- Aggregated sales queries by date, shift, month, and year.
- Order count and revenue summaries.
- Payment method breakdowns.

---

### 8. AuditRepository (`audit_repository.py`)

**Status:** Implemented

**Key responsibilities:**
- Audit log entry persistence.
- Filtered queries by event type, date range, and entity.
- Order-specific audit trail queries.

---

### 9. CashLedgerRepository (`cash_ledger_repository.py` — 204 lines)

**Status:** Implemented

**Key responsibilities:**
- **Append-only insertion:** Only INSERT operations; UPDATE and DELETE are blocked by database triggers.
- **Balance calculations:** Sum ledger entries by session, actor, or date range.
- **Idempotency queries:** Check for existing entries before creating duplicates.
- **Entry type filtering:** Query by `LedgerEntryType`.
- **Session-scoped queries:** Get all entries for a specific cashier session.

**Key methods:**
- `create(entry) → CashLedgerEntry`
- `get_balance_for_session(session_id) → int`
- `get_entries_for_session(session_id) → List[CashLedgerEntry]`
- `exists_for_order(order_id, entry_type) → bool`
- `exists_for_trip(trip_id, entry_type) → bool`
- `get_entries_by_date_range(start, end) → List[CashLedgerEntry]`

---

### 10. CashierSessionRepository (`cashier_session_repository.py` — 164 lines)

**Status:** Implemented

**Key responsibilities:**
- Cashier session CRUD.
- **Station-aware queries:** Find active sessions by station type.
- **Active session lookup** by user or station.
- **Session close** with cash count and variance recording.
- **Handover** linking sessions via `handover_to_session_id`.

**Key methods:**
- `create(session) → CashierSession`
- `update(session) → CashierSession`
- `get_by_id(session_id) → CashierSession`
- `get_active_sessions() → List[CashierSession]`
- `get_active_session_for_station(station) → CashierSession`
- `get_active_session_for_user(user_id) → CashierSession`

---

### 11. DriverSettlementRepository (`driver_settlement_repository.py` — 131 lines)

**Status:** Implemented

**Key responsibilities:**
- **INSERT-only persistence** for settlement records.
- Settlement queries by driver, date, or trip.
- Settlement history retrieval.

**Key methods:**
- `create(settlement) → DriverSettlement`
- `get_by_trip_id(trip_id) → DriverSettlement`
- `get_by_driver_id(driver_id) → List[DriverSettlement]`
- `get_settlements_for_date(date) → List[DriverSettlement]`

---

### 12. OrderStatusHistoryRepository (`order_status_history_repository.py` — 121 lines)

**Status:** Implemented

**Key responsibilities:**
- **INSERT-only persistence** for status transition records.
- History retrieval by order ID.
- Provides an immutable audit trail of all order status changes.

**Key methods:**
- `create(entry) → OrderStatusHistory`
- `get_by_order_id(order_id) → List[OrderStatusHistory]`

---

## Base Repository (`base_repository.py`)

All repositories extend `BaseRepository`, which provides:
- Access to `DatabaseConnection.get_instance()`.
- Shared connection reference via `self._conn` or `self._db`.
- Transaction support through the connection's context manager.

---

## Summary

| Repository | File | Lines | Status | Notes |
|---|---|---|---|---|
| OrderRepository | `order_repository.py` | 509 | Implemented | Batch loading, shift queries |
| ProductRepository | `product_repository.py` | — | Implemented | |
| CustomerRepository | `customer_repository.py` | — | Implemented | |
| UserRepository | `user_repository.py` | — | Implemented | |
| DeliveryRepository | `delivery_repository.py` | — | Implemented | |
| FinancialRepository | `financial_repository.py` | — | Implemented | |
| ReportRepository | `report_repository.py` | — | Implemented | |
| AuditRepository | `audit_repository.py` | — | Implemented | |
| CashLedgerRepository | `cash_ledger_repository.py` | 204 | Implemented | Append-only |
| CashierSessionRepository | `cashier_session_repository.py` | 164 | Implemented | Station-aware |
| DriverSettlementRepository | `driver_settlement_repository.py` | 131 | Implemented | INSERT-only |
| OrderStatusHistoryRepository | `order_status_history_repository.py` | 121 | Implemented | INSERT-only |
| **Total** | **12 files** | | |

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- `user_repository.py`: `get_drivers()` restricted to `role = 'cashier'` with no cashier slot; user delete/reactivate and duplicate-name checks [#67, #110, #108].
- `cashier_session_repository.py`: `set_handover_link()` sets the handover FK without the `is_open` guard [#61].
- `delivery_repository.py`: removed the double `localtime` conversion in date filters; business-day scoped queries [#65, #104].
- `cash_ledger_repository.py`, `financial_repository.py`, `order_repository.py`: `CASH_DROP` booking, refund routing and mixed payment parts [#86, #81, #100].
- `customer_repository.py`, `parked_draft_repository.py`, `audit_repository.py` changed for customer lookup and durable parking [#95, #93].
