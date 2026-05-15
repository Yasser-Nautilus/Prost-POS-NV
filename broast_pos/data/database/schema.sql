-- ============================================================================
-- Prost POS — Database Schema (v1)
--
-- 14 core tables + 1 meta table (schema_version).
-- NO modifier tables — product variations are separate product rows.
--
-- Conventions:
--   • All IDs are INTEGER PRIMARY KEY AUTOINCREMENT.
--   • All timestamps are TEXT in ISO 8601 format (YYYY-MM-DDTHH:MM:SS).
--   • Booleans are INTEGER (0/1) with CHECK constraints.
--   • Foreign keys reference parent(id) and are enforced via PRAGMA.
--   • UNIQUE constraints noted in PROGRESS.md are applied here.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- Meta: schema version tracking (used by migrations.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL DEFAULT 1,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------------
-- 1. users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL,
    display_name  TEXT    NOT NULL,
    avatar_path   TEXT,
    pin_hash      TEXT    NOT NULL UNIQUE,   -- SHA-256, enables identification by PIN alone
    role          TEXT    NOT NULL CHECK (role IN ('cashier', 'manager', 'admin')),
    cashier_slot  INTEGER CHECK (cashier_slot IN (1, 2) OR cashier_slot IS NULL),  -- NULL for drivers
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------------
-- 2. categories
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);


-- ---------------------------------------------------------------------------
-- 3. products
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    price         REAL    NOT NULL CHECK (price >= 0),
    category_id   INTEGER NOT NULL REFERENCES categories(id),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order    INTEGER NOT NULL DEFAULT 0
);


-- ---------------------------------------------------------------------------
-- 4. customers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    NOT NULL UNIQUE,  -- 11-digit Egyptian (starts with 01)
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------------
-- 5. zones
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    delivery_fee  REAL    NOT NULL CHECK (delivery_fee >= 0),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);


-- ---------------------------------------------------------------------------
-- 6. customer_addresses
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_addresses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    street_name   TEXT    NOT NULL,
    zone_id       INTEGER NOT NULL REFERENCES zones(id),
    zone_name     TEXT    NOT NULL,        -- denormalized for display
    delivery_fee  REAL    NOT NULL         -- copied from zone at creation time
);


-- ---------------------------------------------------------------------------
-- 7. shifts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shifts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    opened_by         INTEGER NOT NULL REFERENCES users(id),
    opened_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    closed_by         INTEGER REFERENCES users(id),       -- NULL while shift is open
    closed_at         TEXT,                                -- NULL while shift is open
    next_invoice_no   INTEGER NOT NULL DEFAULT 1,          -- resets to 1 each new shift
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    summary_printed_at TEXT                                -- set when daily summary is first printed; prerequisite for close
);


-- ---------------------------------------------------------------------------
-- 8. orders
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Invoice
    invoice_no        INTEGER NOT NULL,
    shift_id          INTEGER NOT NULL REFERENCES shifts(id),
    UNIQUE(invoice_no, shift_id),                          -- unique per shift

    -- Type & status
    order_type        TEXT    NOT NULL CHECK (order_type IN ('dine_in', 'takeaway', 'delivery', 'pickup')),
    status            TEXT    NOT NULL DEFAULT 'new'
                              CHECK (status IN ('new', 'preparing', 'ready', 'out_for_delivery', 'delivered', 'completed', 'cancelled')),
    table_no          INTEGER,                              -- dine-in only

    -- Customer info (denormalized for receipt / history)
    customer_id       INTEGER REFERENCES customers(id),
    customer_name     TEXT,
    customer_phone    TEXT,
    customer_address  TEXT,
    customer_zone     TEXT,
    delivery_fee      REAL    NOT NULL DEFAULT 0,

    -- Driver (delivery only)
    driver_id         INTEGER REFERENCES users(id),
    driver_name       TEXT,

    -- Financial breakdown
    subtotal          REAL    NOT NULL DEFAULT 0,
    discount_amount   REAL    NOT NULL DEFAULT 0,
    discount_type     TEXT    CHECK (discount_type IN ('flat', 'percent') OR discount_type IS NULL),
    service_amount    REAL    NOT NULL DEFAULT 0,
    total             REAL    NOT NULL DEFAULT 0,

    -- Payment
    payment_method    TEXT    CHECK (payment_method IN ('cash', 'visa', 'online') OR payment_method IS NULL),
    amount_paid       REAL    NOT NULL DEFAULT 0,
    change_given      REAL    NOT NULL DEFAULT 0,
    is_paid           INTEGER NOT NULL DEFAULT 0 CHECK (is_paid IN (0, 1)),
    paid_at           TEXT,

    -- Creator
    created_by_id     INTEGER NOT NULL REFERENCES users(id),
    created_by_name   TEXT    NOT NULL,
    cashier_slot      INTEGER NOT NULL CHECK (cashier_slot IN (1, 2)),

    -- Cancellation
    cancelled_by_id   INTEGER REFERENCES users(id),
    cancelled_by_name TEXT,
    cancel_reason     TEXT,
    cancelled_at      TEXT,

    -- Timestamps
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ---------------------------------------------------------------------------
-- 9. order_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL REFERENCES orders(id),
    product_id    INTEGER NOT NULL REFERENCES products(id),
    product_name  TEXT    NOT NULL,           -- denormalized for receipts
    quantity      INTEGER NOT NULL CHECK (quantity > 0),  -- INTEGER, not REAL
    unit_price    REAL    NOT NULL CHECK (unit_price >= 0),
    total_price   REAL    NOT NULL CHECK (total_price >= 0),
    notes         TEXT                        -- per-item special instructions
);


-- ---------------------------------------------------------------------------
-- 10. delivery_trips
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_trips (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id           INTEGER NOT NULL REFERENCES users(id),
    driver_name         TEXT    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    dispatched_at       TEXT,
    returned_at         TEXT,
    settled_at          TEXT,
    cash_collected      REAL,    -- calculated & stored at settlement (snapshot)
    total_delivery_fees REAL,    -- calculated & stored at settlement (snapshot)
    is_settled          INTEGER NOT NULL DEFAULT 0 CHECK (is_settled IN (0, 1))
);


-- ---------------------------------------------------------------------------
-- 11. delivery_trip_orders (join table — no autoincrement PK)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_trip_orders (
    trip_id   INTEGER NOT NULL REFERENCES delivery_trips(id),
    order_id  INTEGER NOT NULL REFERENCES orders(id),
    PRIMARY KEY (trip_id, order_id)
);


-- ---------------------------------------------------------------------------
-- 12. driver_attendance
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS driver_attendance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id     INTEGER NOT NULL REFERENCES users(id),
    check_in_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    check_out_at  TEXT                  -- NULL = still checked in
);


-- ---------------------------------------------------------------------------
-- 13. shift_transfers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shift_transfers (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id          INTEGER NOT NULL REFERENCES shifts(id),
    from_user_id      INTEGER NOT NULL REFERENCES users(id),
    to_user_id        INTEGER NOT NULL REFERENCES users(id),
    timestamp         TEXT    NOT NULL DEFAULT (datetime('now')),
    summary_snapshot  TEXT    NOT NULL   -- JSON: sales, expenses, pending at transfer time
);


-- ---------------------------------------------------------------------------
-- 14. cash_transactions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cash_transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id      INTEGER NOT NULL REFERENCES shifts(id),
    type          TEXT    NOT NULL DEFAULT 'expense' CHECK (type = 'expense'),  -- expense only
    amount        REAL    NOT NULL CHECK (amount > 0),
    description   TEXT    NOT NULL,
    category      TEXT    NOT NULL CHECK (category IN ('delivery_fees', 'supplies', 'other')),
    timestamp     TEXT    NOT NULL DEFAULT (datetime('now')),
    user_id       INTEGER NOT NULL REFERENCES users(id)
    -- IMMUTABLE: application layer enforces no UPDATE / DELETE
);


-- ---------------------------------------------------------------------------
-- 15. audit_log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    user_name   TEXT    NOT NULL,
    order_id    INTEGER REFERENCES orders(id),  -- nullable (not all events are order-related)
    details     TEXT,                            -- JSON: cancel reason, discount info, etc.
    timestamp   TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- ============================================================================
-- PERFORMANCE INDEXES
--
-- At 300+ orders/day, unindexed queries degrade within weeks.
-- These cover all critical query paths used by repositories.
-- ============================================================================

-- Orders: filter by status (active orders, completed, cancelled)
CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);

-- Orders: filter by type (dine_in, takeaway, delivery, pickup)
CREATE INDEX IF NOT EXISTS idx_orders_type
    ON orders(order_type);

-- Orders: date-range queries (daily reports, shift summaries)
CREATE INDEX IF NOT EXISTS idx_orders_created_at
    ON orders(created_at);

-- Orders: find all orders assigned to a driver
CREATE INDEX IF NOT EXISTS idx_orders_driver
    ON orders(driver_id);

-- Orders: find active dine-in order by table number (pay/edit flow)
CREATE INDEX IF NOT EXISTS idx_orders_table_no
    ON orders(table_no);

-- Customers: exact phone lookup (11-digit Egyptian number)
CREATE INDEX IF NOT EXISTS idx_customers_phone
    ON customers(phone);

-- Customer addresses: all addresses for a given customer
CREATE INDEX IF NOT EXISTS idx_addresses_customer
    ON customer_addresses(customer_id);

-- Products: fast category-based filtering for POS grid
CREATE INDEX IF NOT EXISTS idx_products_category
    ON products(category_id);

-- Delivery trips: all trips for a specific driver
CREATE INDEX IF NOT EXISTS idx_trips_driver
    ON delivery_trips(driver_id);

-- Delivery trips: find unsettled trips quickly
CREATE INDEX IF NOT EXISTS idx_trips_settled
    ON delivery_trips(is_settled);

-- Driver attendance: check-in status for a driver
CREATE INDEX IF NOT EXISTS idx_attendance_driver
    ON driver_attendance(driver_id);
