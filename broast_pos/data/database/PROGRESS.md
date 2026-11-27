# Database — Progress

> **Last Updated:** 2026-11-26
> **Source of Truth:** `schema.sql`, `connection.py`, `migrations.py`, `seed.py`

---

## Overview

The database layer uses **SQLite** with a singleton connection, WAL mode, foreign key enforcement, and a versioned migration system. The current schema defines **19 tables** at **version 6**.

---

## Connection (`connection.py` — 244 lines)

**Status:** Implemented

### Configuration

| Setting | Value | Purpose |
|---|---|---|
| `journal_mode` | WAL | Write-Ahead Logging for concurrent reads |
| `foreign_keys` | ON | Enforce referential integrity |
| `busy_timeout` | 5,000 ms | Wait before raising SQLITE_BUSY |

### Behavior

- **Singleton pattern:** `DatabaseConnection.get_instance()` returns a single shared connection.
- **Transaction context manager:** `with db.transaction():` provides automatic commit/rollback.
- **Nested transactions:** Uses `SAVEPOINT` / `RELEASE` for nested `with db.transaction():` blocks.
- **Row factory:** `sqlite3.Row` for dict-like row access.

---

## Schema (`schema.sql` — 475 lines)

**Status:** Implemented

### Tables (19)

| # | Table | Purpose |
|---|---|---|
| 1 | `categories` | Product categories |
| 2 | `products` | Product catalog |
| 3 | `customers` | Customer records |
| 4 | `customer_addresses` | Delivery addresses per customer |
| 5 | `zones` | Delivery zones with fees |
| 6 | `users` | User accounts with PIN hashes |
| 7 | `orders` | Order headers |
| 8 | `order_items` | Line items per order |
| 9 | `delivery_trips` | Delivery trip tracking |
| 10 | `driver_attendance` | Driver clock-in/out records |
| 11 | `shifts` | Cashier shift records |
| 12 | `shift_transfers` | Cash transfers between shifts |
| 13 | `cash_transactions` | Shift-level cash transactions |
| 14 | `audit_log` | Centralized audit trail |
| 15 | `order_status_history` | Immutable order status transitions |
| 16 | `driver_settlements` | Driver settlement records |
| 17 | `cashier_sessions` | Station-based cashier sessions |
| 18 | `cash_ledger` | Append-only cash movement ledger |
| 19 | `schema_version` | Migration version tracking |

### Cash Ledger Table

> [!IMPORTANT]
> The `cash_ledger` table has special database-level protections:

- **Append-only design:** `BEFORE UPDATE` and `BEFORE DELETE` triggers raise errors, preventing any modification of existing entries.
- **Integer piaster storage:** `amount_piasters INTEGER NOT NULL` — avoids floating-point precision errors.
- **Signed cash movements:** Positive = cash inflow, Negative = cash outflow.
- **Unique idempotency indexes:** Prevent duplicate entries for the same order, trip, expense, or session event.
- **Foreign key references:** `session_id`, `order_id`, `trip_id`, `expense_id`, `actor_user_id`, `approval_user_id`.

### Cashier Sessions Table

| Column | Type | Purpose |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | INTEGER FK | Cashier user |
| `station` | TEXT | `ALL`, `COUNTER`, or `DELIVERY` |
| `opening_float` | REAL | Starting cash amount |
| `closing_float` | REAL | Counted cash at close |
| `expected_cash` | REAL | Calculated expected cash |
| `variance` | REAL | `closing_float - expected_cash` |
| `status` | TEXT | `open` or `closed` |
| `opened_at` | TEXT | ISO timestamp |
| `closed_at` | TEXT | ISO timestamp |
| `closed_by` | INTEGER FK | User who closed |
| `notes` | TEXT | Optional notes |
| `handover_to_session_id` | INTEGER FK | Linked successor session |

### Additional Schema Details

- `users.pin_salt` — `TEXT` column, `NULL` for legacy SHA-256 users, populated with random salt for PBKDF2 users.
- `orders.is_paid` — `INTEGER DEFAULT 0`, boolean flag for payment status.
- `audit_log` — Extended fields: `old_value`, `new_value` for before/after snapshots.
- `driver_settlements` — All monetary fields stored as integer piasters.

---

## Migrations (`migrations.py` — 364 lines)

**Status:** Implemented

### Current Version: 6

| Migration | Version | Responsibility |
|---|---|---|
| v1 → v2 | 2 | Add `order_status_history` table |
| v2 → v3 | 3 | Extend `audit_log` with `old_value` and `new_value` columns |
| v3 → v4 | 4 | Add `driver_settlements` table |
| v4 → v5 | 5 | Add `cashier_sessions` and `cash_ledger` tables with triggers and indexes |
| v5 → v6 | 6 | Add `users.pin_salt` column |

### Migration Safety

> [!CAUTION]
> **Do not reuse migration version 6.** Migration v6 (`add_pin_salt`) is already deployed and adds the `users.pin_salt` column. Any future schema changes must use **version 7 or higher**.

### Migration Runner

- `run_migrations(conn)` — Checks current version from `schema_version` table, applies all pending migrations in order.
- Each migration runs in a transaction.
- `LATEST_VERSION = 6` constant in `migrations.py`.

---

## Seed Data (`seed.py` — 164 lines)

**Status:** Implemented

Seeds the database with a default admin user on first run.

- **Username:** Configured via constants.
- **Default PIN:** Hashed with legacy SHA-256 (no salt, `pin_salt=NULL`).
- **Role:** Admin.
- **Auto-upgrade:** On first login, `AuthService` detects the missing salt and upgrades to PBKDF2.

> [!WARNING]
> The seed admin uses a legacy SHA-256 hash without salt. This is by design for backward compatibility — the hash is automatically upgraded to PBKDF2-HMAC-SHA256 on first successful login.

---

## Summary

| Component | File | Lines | Status |
|---|---|---|---|
| Connection | `connection.py` | 244 | Implemented |
| Schema | `schema.sql` | 475 | Implemented |
| Migrations | `migrations.py` | 364 | Implemented |
| Seed | `seed.py` | 164 | Implemented |
| **Total** | **4 files** | **1,247** | |

| Metric | Value |
|---|---|
| Schema Version | 6 |
| Total Tables | 19 |
| Applied Migrations | 5 |
| Connection Mode | WAL |
| Foreign Keys | Enforced |
| Busy Timeout | 5,000 ms |
| Cash Ledger Protection | UPDATE/DELETE triggers |

## Update 2026-11-27 (Batch 5: menu and products)

- `menu_data.py`: pieces, meals, crispy/zinger and tender/zinger items are now separate regular and spicy products (for example "2 قطع دجاج عادي" and "2 قطع دجاج حار"). `SPLIT_PRODUCTS` maps each old name to its two new names.
- `seed.ensure_menu_products`: `PRAGMA user_version` 2 marks the split. A database imported with the old menu is upgraded once: the old product keeps its id and becomes the regular one, a spicy copy with the same price, category and active state is inserted right after it. Missing or renamed products are skipped.
---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- Migrations: v13 adds `users.phone`; v15 adds business-day closure keys without rewriting historical financial records [#94, #104].
- `schema.sql`: new table `order_payments` (`CREATE IF NOT EXISTS`) for mixed payment [#100].
- `menu_data.py`, `seed.py`: one-time menu import (`ensure_menu_products()`, tracked with `PRAGMA user_version` so items the owner deletes are not brought back) and updated seed menu [#110].
- `connection.py`: all operations now run under a thread lock (`threading.RLock`), nested `transaction()` scopes use real SQLite savepoints, and `executescript` is refused inside a managed transaction [#93]. `__init__.py` and `seed.py` add `validate_no_default_admin()`: production start fails if no active admin/manager exists or one still has the default PIN 1234 [#90].

## Update 2026-11-27 (Batch 6: shifts, keyboard, live orders)

- `connection.py` calls `clock.configure_process_timezone()` at import, so every stored timestamp (column defaults included) is Cairo time even on a machine whose OS timezone is wrong. Fixes shifts saved two hours behind and a brand-new order showing "02:06" elapsed.

---
