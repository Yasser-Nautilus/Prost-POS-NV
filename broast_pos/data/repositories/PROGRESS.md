# 📁 data/repositories — PROGRESS

## 🎯 Goal

Abstract **all database access** behind a clean repository interface. Services call repositories — never SQLite directly. This is the key layer that enables future Google Sheets sync without touching any service code.

---

## ✅ Tasks

### 1. Base Repository (`base_repository.py`)

- **What**: Abstract base class defining the CRUD contract
- **Details**:
  - Generic class `BaseRepository[T]` using Python's `ABC` and `Generic`
  - Abstract methods: `get_by_id(id)`, `save(entity)`, `delete(id)`
  - `save()` handles both insert (when id is None) and update (when id exists)
  - `delete()` performs soft-delete (status change), never hard-delete
- **Why**: This is the contract that both SQLite and future Google Sheets implementations must fulfill.
- **Status**: `To Review`

### 2. Order Repository (`order_repository.py`)

- **What**: All order-related database queries in one place
- **Details**:
  - `get_by_id(order_id)` → fetch order with items
  - `get_by_invoice(invoice_no)` → lookup by invoice number
  - `get_by_table(table_number)` → load active order for a dine-in table
  - `save(order)` → insert or update order + items
  - `get_active_orders()` → all non-completed, non-cancelled orders
  - `get_active_by_type(order_type)` → filtered by type (for tracking view)
  - `get_unassigned_deliveries()` → delivery orders not yet assigned to a driver (from both cashiers)
  - `get_today_orders()` → all orders created today (current shift)
  - `get_orders_for_report(date_str)` → non-cancelled orders for a specific date
  - `get_next_invoice_number()` → next sequential int for current shift
  - Private helpers: `_row_to_order()`, `_load_items()`, `_insert()`, `_update()`, `_save_items()`
- **Why**: Simplified without modifiers. Each item is just product_id, name, qty (int), price, notes.
- **Status**: `To Review`

### 3. User Repository (`user_repository.py`)

- **What**: All user/authentication database queries
- **Details**:
  - `get_by_id(user_id)` → fetch user
  - `get_by_username(username)` → login lookup
  - `get_by_pin(pin_hash)` → PIN verification for manager overrides
  - `save(user)` → create or update user
  - `get_all_active()` → for user management screen
  - `get_drivers()` → users with driver role (for delivery assignment)
- **Status**: `To Review`

### 4. Product Repository (`product_repository.py`)

- **What**: Product and category database queries
- **Details**:
  - `get_categories()` → sorted list of active categories
  - `get_products_by_category(category_id)` → sorted products for POS grid
  - `search_products(query)` → text search across product names
  - `save_product(product)`, `save_category(category)`
  - ~~`get_modifiers_for_product()`~~ — **REMOVED** (no modifiers)
  - ~~`save_modifier()`~~ — **REMOVED**
- **Why**: Simplified — no modifier queries, no join tables. Products are self-contained.
- **Status**: `To Review`

### 5. Customer Repository (`customer_repository.py`)

- **What**: Customer, address, and zone database queries
- **Details**:
  - **Customer**:
    - `find_by_phone(phone)` → exact match (11-digit) → return customer with all addresses, or None
    - `save_customer(customer)` → create or update
  - **Address**:
    - `get_addresses(customer_id)` → all saved addresses for this customer
    - `save_address(address)` → create new address (street_name + zone_id + copied fee)
  - **Zone** (manager only):
    - `get_all_active_zones()` → for dropdown in customer panel
    - `save_zone(zone)` → create or update zone (name + delivery_fee)
    - `deactivate_zone(zone_id)` → soft delete
- **Status**: `To Review`

### 6. Delivery Repository (`delivery_repository.py`)

- **What**: Delivery trip, driver attendance, and settlement queries
- **Details**:
  - **Driver attendance**:
    - `check_in(driver_id)` → create attendance record with check_in_at timestamp
    - `check_out(driver_id)` → update attendance record with check_out_at
    - `get_checked_in_drivers()` → all currently active drivers
    - `get_driver_status(driver_id)` → CHECKED_OUT / AVAILABLE / OUT
  - **Trip lifecycle**:
    - `create_trip(driver_id, order_ids)` → new trip record
    - `mark_dispatched(trip_id)` → set dispatched_at timestamp
    - `mark_returned(trip_id)` → set returned_at timestamp
    - `mark_settled(trip_id)` → set settled_at timestamp
  - **Trip queries**:
    - `get_active_trips()` → trips dispatched but not yet returned
    - `get_unsettled_trips(driver_id=None)` → returned but not settled (optional driver filter)
    - `get_trip_with_orders(trip_id)` → full trip detail including order list
  - **End-of-day**:
    - `get_all_drivers_daily_summary(date)` → per-driver: trip count, order count, fees earned
    - `get_driver_daily_trips(driver_id, date)` → all trips for one driver on a date
- **Status**: `To Review`

### 7. Financial Repository (`financial_repository.py`)

- **What**: Shift lifecycle, expense tracking, and reconciliation queries
- **Details**:
  - **Shift**:
    - `open_shift(user_id)` → create shift record, reset invoice counter to 1
    - `close_shift(shift_id, closed_by)` → set closed_at, is_active = false
    - `get_active_shift()` → currently open shift (or None)
    - `get_shift_history()` → past closed shifts
  - **Shift transfer**:
    - `save_transfer(shift_id, from_user, to_user, snapshot)` → record transfer checkpoint
    - `get_transfers_for_shift(shift_id)` → all transfers in this shift
  - **Expenses**:
    - `add_expense(transaction)` → insert cash-out entry (immutable, no update/delete)
    - `get_shift_expenses(shift_id)` → all expenses for this shift
    - `get_expenses_for_date(date)` → for export to Excel/Sheets
  - **Reporting queries**:
    - `get_shift_order_summary(shift_id)` → aggregate orders by type (count + revenue)
    - `get_pending_delivery_total(shift_id)` → unsettled driver orders total
    - `get_pending_dinein_total(shift_id)` → unpaid dine-in tables total
    - `get_pending_kitchen_total(shift_id)` → orders still in preparation total
    - `has_unsettled_trips()` → bool — prerequisite check for close
    - `has_printed_daily_summary(shift_id)` → checks `shifts.summary_printed_at IS NOT NULL`
    - `mark_summary_printed(shift_id)` → sets `shifts.summary_printed_at = NOW()` (called when daily summary is first printed)
  - **Invoice**:
    - `get_next_invoice_no(shift_id)` → atomic `UPDATE shifts SET next_invoice_no = next_invoice_no + 1 WHERE id = ? RETURNING next_invoice_no` (race-safe for 2 cashiers)
- **Why**: Pending calculations are critical for expected cash. Close prerequisites prevent data loss.
- **Status**: `To Review`

### 8. Audit Repository (`audit_repository.py`)

- **What**: Centralized audit trail logging
- **Details**:
  - `log(event_type, user_id, user_name, order_id=None, details=None)` → insert audit_log entry
  - `get_logs_for_date(date)` → all audit entries for a given date
  - `get_logs_for_order(order_id)` → audit trail for a specific order
  - Event types: `order_cancelled`, `discount_applied`, `item_removed`, `shift_opened`, `shift_closed`, `shift_transferred`, `user_created`, `user_updated`
  - Details stored as JSON (e.g., cancel reason, discount amount, removed item info)
- **Why**: The `audit_log` table is defined in the schema but needs a repository to actually write/query it. Without this, audit logging will be implemented inconsistently across services.
- **Status**: `To Review`

---

## 📝 Notes

- **This layer enables future Google Sheets sync**
- All SQL lives ONLY in repository files — nowhere else
- Use parameterized queries (`?` placeholders) — never string concatenation
- **No modifier-related queries** — removed entirely (simpler joins, faster queries)
- Order item loading: just `SELECT * FROM order_items WHERE order_id = ?` (no modifier joins)
