# 📁 data/database — PROGRESS

## 🎯 Goal

Set up the **SQLite database layer** — connection management, schema definition, migrations, and seed data. This is the foundation that every repository sits on top of.

---

## ✅ Tasks

### 1. Create Database Connection (`connection.py`)

- **What**: Singleton database connection with WAL mode and proper configuration
- **Details**:
  - Singleton pattern — one connection for the entire application
  - Enable WAL (Write-Ahead Logging) mode for concurrent read/write safety
  - `check_same_thread=False` for Qt compatibility
  - Enable foreign keys enforcement
  - Row factory set to `sqlite3.Row` for dict-like access
  - Methods: `execute()`, `fetch_one()`, `fetch_all()`, `executescript()`
  - Transaction support: `begin()`, `commit()`, `rollback()`
- **Why**: Two cashiers on the same machine need concurrent access. WAL mode prevents lock contention.
- **Critical**: Invoice numbering must be race-safe — use `AUTOINCREMENT` on orders table.
- **Status**: `Not started`

### 2. Define Schema (`schema.sql`)

- **What**: Complete table definitions matching all core models
- **Details**:
  - `users` — id, username, display_name, avatar_path, pin_hash (UNIQUE), role, cashier_slot, is_active, created_at
  - `categories` — id, name, sort_order, is_active
  - `products` — id, name, price, category_id (FK), is_active, sort_order
  - `customers` — id, name, phone (UNIQUE, 11-digit), notes, created_at
  - `zones` — id, name, delivery_fee, is_active
  - `customer_addresses` — id, customer_id (FK), street_name, zone_id (FK), zone_name (denormalized), delivery_fee (copied from zone)
  - `orders` — id, invoice_no (UNIQUE AUTO), order_type, status, table_no, customer fields, financial fields (subtotal, discount, service, delivery_fee, total), staff fields, cancellation fields, timestamps
  - `order_items` — id, order_id (FK), product_id, product_name, quantity (**INTEGER**), unit_price, total_price, notes (TEXT)
  - `delivery_trips` — id, driver_id, driver_name, created_at, dispatched_at, returned_at, settled_at, cash_collected, total_delivery_fees, is_settled
  - `delivery_trip_orders` — trip_id, order_id (join table)
  - `driver_attendance` — id, driver_id, check_in_at, check_out_at
  - `shifts` — id, opened_by, opened_at, closed_by (nullable), closed_at (nullable), next_invoice_no (resets to 1), is_active
  - `shift_transfers` — id, shift_id, from_user_id, to_user_id, timestamp, summary_snapshot (JSON)
  - `cash_transactions` — id, shift_id, type (`expense` only), amount, description, category, timestamp, user_id, **immutable**
  - `audit_log` — id, event_type, user_id, user_name, order_id, details (JSON), timestamp
  - ~~`modifiers`~~ — **REMOVED** (product variations are separate products)
  - ~~`product_modifiers`~~ — **REMOVED**
  - ~~`order_item_modifiers`~~ — **REMOVED**
- **Why**: Schema must mirror the models exactly. No modifier tables needed — simplifies the database significantly.
- **Status**: `Not started`

### 3. Index Definitions (inside `schema.sql`)

- **What**: Performance indexes for common queries
- **Details**:
  - `idx_orders_status` — fast filtering by order status
  - `idx_orders_type` — fast filtering by order type
  - `idx_orders_created_at` — fast date range queries
  - `idx_orders_driver` — fast driver lookup
  - `idx_orders_table_no` — fast table lookup for dine-in pay/edit flow
  - `idx_customers_phone` — fast phone search (exact match)
  - `idx_addresses_customer` — fast address lookup by customer
  - `idx_products_category` — fast category filtering
  - `idx_trips_driver` — fast driver trip lookup
  - `idx_trips_settled` — fast unsettled trip filtering
  - `idx_attendance_driver` — fast check-in status
- **Why**: At 300+ orders/day, unindexed queries slow down within weeks.
- **Status**: `Not started`

### 4. Migrations System (`migrations.py`)

- **What**: Safe schema update mechanism for future changes
- **Details**:
  - Version tracking table: `schema_version`
  - `migrate()` function checks current version and applies pending migrations
  - Each migration is a function: `migrate_v1_to_v2()`, etc.
  - Uses `ALTER TABLE` for adding columns, never drops existing data
  - Runs automatically at app startup
- **Status**: `Not started`

### 5. Seed Data (`seed.py`)

- **What**: Sample data for fresh installations and testing
- **Details**:
  - Default admin user (username: admin, PIN: hashed "1234")
  - Sample categories (e.g., "بروست", "مشروبات", "إضافات")
  - Sample products per category — each variation is a separate product:
    - "تشيكن فرايز حار" (price: 70)
    - "تشيكن فرايز عادي" (price: 70)
    - "2 قطعة دجاج حار" (price: 110)
    - "2 قطعة دجاج عادي" (price: 110)
  - Only runs if tables are empty (idempotent)
- **Status**: `Not started`

---

## 📝 Notes

- Schema must be kept **perfectly aligned** with `core/models/`
- **No modifier tables** — removed entirely (3 tables eliminated)
- `order_items.quantity` is **INTEGER**, not REAL/FLOAT
- `order_items.notes` is **TEXT** — per-item special instructions
- All timestamps stored as ISO 8601 strings
- PIN is stored as SHA-256 hash, never plain text
- **PIN hash is UNIQUE** — enables user identification by PIN alone (manager override)
- `shifts.next_invoice_no` resets to 1 when a new shift is opened (daily)
- `delivery_trips.cash_collected` = sum of order totals WHERE payment = كاش
- `delivery_trips.total_delivery_fees` = sum of delivery fees for ALL orders
- `cash_transactions` are **expense-only** and **immutable** (no edit/delete after creation)
- `cash_transactions.category` supports: delivery_fees, supplies, other
- `shifts` have NO `opening_cash` — shift just opens with no cash amount
- `shift_transfers` record mid-day cashier handovers with state snapshots
- **Shift is shared** across both devices — one active shift at a time
- **Orders blocked** if no active shift exists
- **Multi-device**: normally single PC. During peak, main PC holds the database, secondary PC connects over local network via lightweight API. Repository pattern enables transparent switching.
