# 📦 Prost POS — Complete Project Structure + Progress

> **Last Updated**: 2026-05-08
> **Tech**: Python 3 · PyQt6 · SQLite (WAL) · ESC/POS · White-Label
> **Restaurant**: بروستش / Prostsh (configurable via restaurant.json)
> **Overall Status**: 🔴 **0% implemented** — Architecture complete, all tasks Not Started
> **Existing Code**: Only `__init__.py` placeholder files in all packages

---

# 📊 Progress Summary Dashboard

| Module | Files Planned | Tasks | Status |
|--------|:---:|:---:|:---:|
| config/ | 4 | 5 | 🔴 Not Started |
| core/models/ | 6 | 7 | 🔴 Not Started |
| core/services/ | 7 | 7 | 🔴 Not Started |
| data/database/ | 4 | 5 | 🔴 Not Started |
| data/repositories/ | 7 | 7 | 🔴 Not Started |
| infrastructure/printing/ | 4 | 5 | 🔴 Not Started |
| infrastructure/sync/ | 2 | 4 | 🔴 Not Started |
| ui/styles/ | 1 | 1 | 🔴 Not Started |
| ui/windows/ | 2 | 2 | 🔴 Not Started |
| ui/views/ | 8 | 9 | 🔴 Not Started |
| ui/components/ | 6 | 6 | 🔴 Not Started |
| **feature/order_lifecycle** | cross-cutting | 8 | 🔴 Not Started |
| **feature/delivery_system** | cross-cutting | 8 | 🔴 Not Started |
| **feature/printing_flow** | cross-cutting | 5 | 🔴 Not Started |
| **feature/reports** | cross-cutting | 4 | 🔴 Not Started |
| **feature/user_permissions** | cross-cutting | 5 | 🔴 Not Started |
| **TOTAL** | ~50 files | ~88 tasks | 🔴 **0/88** |

---

# 🏗️ Project Structure (Annotated)

```
broast_pos/
├── main.py
├── config/
│   ├── restaurant.json         # White-label identity (name, logo, colors, fonts)
│   ├── config.py               # APP_NAME, VERSION, ENVIRONMENT, DEBUG
│   ├── printers.json           # Printer role → device mapping
│   └── business_rules.py      # TAX, MAX_DISCOUNT, AUTO_PRINT, timers
├── core/
│   ├── models/                 # Pure dataclasses — NO DB, NO UI
│   │   ├── order.py            # Order, OrderItem, OrderStatus, OrderType, PaymentMethod
│   │   ├── user.py             # User, UserRole (CASHIER/MANAGER/ADMIN)
│   │   ├── product.py          # Product, Category (NO modifiers)
│   │   ├── customer.py         # Customer, CustomerAddress, Zone
│   │   ├── delivery.py         # DeliveryTrip, DriverAttendance, DriverStatus
│   │   └── financial.py        # Shift, ShiftTransfer, CashTransaction, ShiftSummary
│   └── services/               # Business logic — calls repos, never DB directly
│       ├── order_service.py    # Create, amend(تابع), complete, cancel
│       ├── auth_service.py     # Login, session, verify_pin (manager override)
│       ├── delivery_service.py # Check-in/out, trips, settlement, daily summary
│       ├── product_service.py  # CRUD, search (<100ms)
│       ├── customer_service.py # Phone lookup, addresses, zones
│       ├── financial_service.py# Shift lifecycle, expenses, invoice counter
│       └── report_service.py   # Daily/monthly/yearly reports
├── data/
│   ├── database/
│   │   ├── connection.py       # SQLite singleton, WAL mode, foreign keys
│   │   ├── schema.sql          # 14 tables (NO modifier tables)
│   │   ├── migrations.py       # Version-tracked schema updates
│   │   └── seed.py             # Default admin + sample data
│   └── repositories/           # Abstract DB access — enables future sync
│       ├── base_repository.py  # Generic ABC: get_by_id, save, delete
│       ├── order_repository.py
│       ├── user_repository.py
│       ├── product_repository.py
│       ├── customer_repository.py
│       ├── delivery_repository.py
│       └── financial_repository.py
├── infrastructure/
│   ├── printing/
│   │   ├── printer_manager.py  # Routes to KITCHEN / CASHIER_1 / CASHIER_2
│   │   ├── escpos_printer.py   # USB/Network/Serial thermal adapter
│   │   ├── receipt_templates.py# 10 print layouts
│   │   └── printer_config.py   # JSON config loader
│   └── sync/                   # Future Google Sheets
│       ├── sync_interface.py   # Abstract contract
│       └── sheets_sync.py      # No-op stub
└── ui/                         # PyQt6 — ZERO business logic
    ├── app.py
    ├── styles/
    │   └── theme.py            # Dark navy QSS, Arabic fonts, RTL
    ├── windows/
    │   ├── main_window.py      # Sidebar navigation shell (role-based)
    │   └── login_window.py     # Avatar tiles + PIN
    ├── views/
    │   ├── login_view.py       # User avatar tiles → PIN → session
    │   ├── pos_view.py         # 🔥 Main cashier screen (3-column)
    │   ├── tracking_view.py    # Active orders, timers, auto-complete visual
    │   ├── delivery_view.py    # 3-panel: drivers | trips | settlement
    │   ├── reports_view.py     # Reports dashboard + print
    │   ├── products_view.py    # Products/categories/zones (Manager)
    │   ├── users_view.py       # User management (Admin)
    │   └── financial_view.py   # Shift/expenses/reconciliation (Manager)
    └── components/             # 6 reusable widgets
        ├── product_grid.py     # Tap = add to order (NO popup)
        ├── order_panel.py      # Live items, +/-, notes, totals
        ├── payment_dialog.py   # كاش / فيزا / اونلاين
        ├── pin_dialog.py       # Manager override numpad
        ├── table_grid.py       # Green=free / Red=occupied (shared)
        └── customer_panel.py   # Phone → auto-fill → address cards
```

---

# 📁 MODULE-LEVEL PROGRESS

---

## 📁 config/ — Configuration

**Goal**: Centralize all system configuration. White-label ready: one `restaurant.json` swap = new restaurant.

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Restaurant Branding (`restaurant.json`) | name_ar/en, logo, slogan, receipt_footer, theme colors, category_colors[], fonts | 🔴 |
| 2 | General Settings (`config.py`) | APP_NAME (from JSON), VERSION, ENVIRONMENT, DEBUG, LANGUAGE=ar | 🔴 |
| 3 | Printer Config (`printers.json`) | kitchen: network, cashier_1/2: USB. Loaded at startup | 🔴 |
| 4 | Business Rules | TAX_RATE=0, MAX_DISCOUNT=100, AUTO_PRINT=True, TRACKING_REFRESH=10s | 🔴 |
| 5 | Paths & Files | DATABASE_PATH, LOGS_PATH, FONTS_PATH, BRANDING_PATH | 🔴 |

**Notes**: No logic here. Theme colors → Qt StyleSheet at startup. Category colors rotate.

---

## 📁 core/models/ — Data Models

**Goal**: Pure Python dataclasses. NO database, NO UI imports.

| # | Task | Key Details | Status |
|---|------|-------------|:---:|
| 1 | Order Model | 4 types (صالة/تيك اواي/دليفري/استلام محل), 3 payments (كاش/فيزا/اونلاين), computed totals, cancellation fields | 🔴 |
| 2 | OrderItem | product_id, name, qty (**int**), unit_price, notes (str). **NO modifiers list** | 🔴 |
| 3 | User Model | UserRole enum (CASHIER/MANAGER/ADMIN), PIN hash (SHA-256, **UNIQUE**), cashier_slot (1/2) | 🔴 |
| 4 | Product Model | Product + Category. NO Modifier model. Each variation = separate product | 🔴 |
| 5 | Customer Model | Phone (11-digit Egyptian, unique), CustomerAddress, Zone (fixed delivery_fee) | 🔴 |
| 6 | Delivery Model | DeliveryTrip (lifecycle: created→dispatched→returned→settled), DriverAttendance, DriverStatus | 🔴 |
| 7 | Financial Model | Shift (invoice counter resets to #1), ShiftTransfer (snapshot), CashTransaction (**immutable, expense-only**) | 🔴 |

**Key Rules**:
- `is_prepaid`: True for اونلاين, False for كاش/فيزا
- Visa NOT available for delivery
- `restaurant_revenue` = total - delivery_fee (critical for shift reports)
- Quantity is **int** — no 0.5 chickens

---

## 📁 core/services/ — Business Logic

**Goal**: All rules, validations, workflows. Services → repositories. **Never** talk to UI.

| # | Service | Key Responsibilities | Status |
|---|---------|---------------------|:---:|
| 1 | OrderService | create (shift guard), amend (تابع, manager PIN for removals), complete, cancel (PIN+reason), apply_discount (PIN) | 🔴 |
| 2 | AuthService | get_all_users (avatar tiles), login, logout, verify_pin (manager override → returns WHO), check_permission | 🔴 |
| 3 | DeliveryService | check_in/out, create_trip, mark_dispatched/returned, settle_trip (cash vs online logic), daily_summary | 🔴 |
| 4 | ProductService | get_categories, get_products_by_category, search (<100ms), CRUD (manager only) | 🔴 |
| 5 | CustomerService | find_by_phone (exact 11-digit), create_customer+address, zone CRUD (manager), validation | 🔴 |
| 6 | FinancialService | open_shift (reset invoice #1), transfer (snapshot), close (prerequisites: all settled + summary printed), add_expense (immutable) | 🔴 |
| 7 | ReportService | daily (type breakdown), payment breakdown, cancelled orders, product sales, driver summary, monthly, yearly | 🔴 |

**Key Rules**:
- Shift must be active to create orders
- Takeaway: save triggers immediate Payment Dialog
- Delivery (online): auto-marked paid at save
- Adding items = free. Removing items = manager PIN
- Print failures logged but **never block** the cashier

---

## 📁 data/database/ — SQLite Database

**Goal**: Connection, schema, migrations, seed data.

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Connection (`connection.py`) | Singleton, WAL mode, check_same_thread=False, foreign keys, Row factory | 🔴 |
| 2 | Schema (`schema.sql`) | 14 tables: users, categories, products, customers, zones, customer_addresses, orders, order_items, delivery_trips, delivery_trip_orders, driver_attendance, shifts, shift_transfers, cash_transactions, audit_log | 🔴 |
| 3 | Indexes | 11 performance indexes (orders_status, customers_phone, products_category, etc.) | 🔴 |
| 4 | Migrations (`migrations.py`) | schema_version table, auto-run at startup, ALTER TABLE only | 🔴 |
| 5 | Seed Data (`seed.py`) | Default admin (PIN: 1234 hashed), sample categories + products. Idempotent | 🔴 |

**Notes**: No modifier tables (3 tables eliminated). order_items.quantity = INTEGER. PIN hash is UNIQUE.

---

## 📁 data/repositories/ — Data Access Layer

**Goal**: Abstract all DB access. Services → repos → SQLite. Enables future Google Sheets sync.

| # | Repository | Key Methods | Status |
|---|-----------|-------------|:---:|
| 1 | BaseRepository | Abstract: get_by_id, save (insert/update), delete (soft) | 🔴 |
| 2 | OrderRepository | get_by_id/invoice/table, save, get_active, get_unassigned_deliveries, get_next_invoice_number | 🔴 |
| 3 | UserRepository | get_by_id/username/pin, save, get_all_active, get_drivers | 🔴 |
| 4 | ProductRepository | get_categories, get_products_by_category, search, save_product/category | 🔴 |
| 5 | CustomerRepository | find_by_phone (exact), save_customer, get/save_address, zone CRUD | 🔴 |
| 6 | DeliveryRepository | check_in/out, create/dispatch/return/settle trip, get_active/unsettled, daily_summary | 🔴 |
| 7 | FinancialRepository | open/close_shift, get_active_shift, add_expense (immutable), pending calculations, has_unsettled_trips | 🔴 |

**Notes**: All SQL lives ONLY here. Parameterized queries only. No modifier joins needed.

---

## 📁 infrastructure/printing/ — Thermal Printing

**Goal**: Reliable, silent ESC/POS printing. 2 cashier printers + 1 shared kitchen. **Never block cashier.**

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | PrinterManager | Route: KITCHEN (shared), CASHIER_1, CASHIER_2. Never raise, never block | 🔴 |
| 2 | ESC/POS Adapter | USB/Network/Serial via python-escpos. Arabic encoding. Auto-reconnect | 🔴 |
| 3 | Receipt Templates | **10 layouts**: 4 customer receipts (dine-in/delivery/takeaway/pickup), kitchen ticket, amendment ticket (تابع), daily sales report, shift transfer report, driver settlement, driver summary | 🔴 |
| 4 | Silent Printing | Auto-trigger: create→kitchen, amend→amendment, complete→receipt, close→summary. Zero dialogs | 🔴 |
| 5 | Printer Config | JSON config loaded at startup. Future: admin UI | 🔴 |

**Key**: Kitchen ticket has NO prices, NO customer info. Order number in LARGE BOLD. Notes shown as `ملاحظة: {text}`.

---

## 📁 infrastructure/sync/ — Future Google Sheets

**Goal**: Define contracts now, implement later. Offline-first.

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Sync Interface | Abstract: sync_order, sync_expense, sync_report, is_connected | 🔴 |
| 2 | Event Hooks (design only) | After create/cancel/settle/close → non-blocking sync triggers | 🔴 |
| 3 | Sheets Adapter (stub) | No-op methods, logs "sync not configured" | 🔴 |
| 4 | Background Worker | Queue-based, retry, offline-safe. **FUTURE — do not implement now** | 🔴 |

---

## 📁 ui/styles/ — Theme

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Global Theme (`theme.py`) | Dark navy (#1a1d23), Arabic fonts (Cairo/Tajawal), RTL, 48px min buttons, consistent spacing | 🔴 |

---

## 📁 ui/windows/ — App Windows

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Main Window | Sidebar: POS, Tracking, Delivery (all), Reports, Products, Financial (manager), Users (admin). QStackedWidget | 🔴 |
| 2 | Login Window | Avatar tiles + masked PIN + numpad. 5-second login goal | 🔴 |

---

## 📁 ui/views/ — Screens

| # | View | Details | Status |
|---|------|---------|:---:|
| 0 | Login View | Avatar tiles for active users → PIN entry → session created → navigate to POS | 🔴 |
| 1 | **POS View** 🔥 | 3-column (categories|products|order panel), parked orders bar, order type selector, table grid (dine-in), customer panel (delivery) | 🔴 |
| 2 | Tracking View | Tab filters by type, order cards with live timers, takeaway auto-highlight at 20min (visual only), auto-refresh 10s | 🔴 |
| 3 | Delivery View | 3-panel: drivers (check-in/out) | orders+trips (assign/dispatch/return) | settlement (cash vs online breakdown) + end-of-day summary | 🔴 |
| 4 | Reports View | Daily (type breakdown, payment split, cancelled, product ranking, driver summary), monthly (charts, bestsellers), yearly. Print any report | 🔴 |
| 5 | Products View | Category/product CRUD, zone management (name + delivery_fee), sort order. Manager only | 🔴 |
| 6 | Users View | User CRUD, avatar upload, role assign, cashier_slot, PIN (unique), driver setup. Admin only | 🔴 |
| 7 | Financial View | Open shift (any role), expense entry (immutable), shift transfer (manager PIN, snapshot, print), close shift (prerequisites check, final summary) | 🔴 |

---

## 📁 ui/components/ — Reusable Widgets (6 total)

| # | Component | Details | Status |
|---|-----------|---------|:---:|
| 1 | Product Grid | Large buttons (80×60px min), category-colored, tap = add directly (NO popup) | 🔴 |
| 2 | Order Panel | Scrollable items, +/- buttons (not QSpinBox), per-item notes, live totals (subtotal, service, discount, delivery_fee, grand total) | 🔴 |
| 3 | Payment Dialog | 3 methods (كاش/فيزا/اونلاين), Visa disabled for delivery, cash: amount+change, quick buttons (50/100/200/500) | 🔴 |
| 4 | PIN Dialog | Masked input (any length), on-screen numpad, verify_pin → returns user if MANAGER/ADMIN, audit trail | 🔴 |
| 5 | Table Grid | Green=free (new order), Red=occupied (load existing). Shared across cashiers. Shows order # + cashier name | 🔴 |
| 6 | Customer Panel | Phone (11-digit) → exact match → auto-fill name/addresses. Address cards (colored). Zone dropdown → auto-fill fee (read-only) | 🔴 |

**Removed**: ~~Modifier Dialog~~ — no modifier system exists.

---

# 🧩 FEATURE-LEVEL PROGRESS

These track **end-to-end business features** across multiple modules.

---

## 📦 feature/order_lifecycle — Full Order Flow

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Create Order (In-Memory) | Select type → add items (tap=add, no popup) → notes → live totals. NOT in DB yet | 🔴 |
| 2 | Parked Orders | Multi-order buffer (tabs), in-memory only, lost on crash (acceptable v1) | 🔴 |
| 3 | Validate & Save | Business rules enforced → invoice # generated → kitchen ticket auto-prints → takeaway: immediate payment | 🔴 |
| 4 | Payment Flow | Separate from save. Dine-in: click table → pay. Pickup: find order → pay. Delivery cash: via settlement | 🔴 |
| 5 | Edit Saved Order (تابع) | Add items = free. Remove items = manager PIN. Amendment kitchen ticket (changes only) | 🔴 |
| 6 | Status Transitions | Non-delivery: ACTIVE→COMPLETED. Delivery: ACTIVE→OUT→DELIVERED→COMPLETED. CANCELLED from any non-completed | 🔴 |
| 7 | Cancel Order | Manager PIN + reason → audit trail. Cannot cancel completed orders | 🔴 |
| 8 | Invoice Numbers | Sequential int, resets to #1 on open_shift, race-safe for 2 cashiers | 🔴 |

### Order Flow Per Type:
- **Dine-In (صالة)**: Select table → add items → confirm → kitchen prints → [eat] → click table → pay → receipt → table free
- **Takeaway (تيك اواي)**: Add items → confirm → kitchen prints → **immediate payment dialog** → receipt → tracking shows timer
- **Delivery Cash (دليفري+كاش)**: Phone → address → items → confirm → kitchen prints → assign driver → dispatch → deliver+collect → return → settle
- **Delivery Online (دليفري+اونلاين)**: Same but auto-marked PAID at save, driver collects nothing
- **Pickup (استلام محل)**: Phone+name → items → confirm → kitchen prints → [customer arrives] → find order → pay → receipt

---

## 🚚 feature/delivery_system — Driver Lifecycle & Settlement

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Driver Management | Manager adds (via Users), cashier check-in/out. Only checked-in drivers in dispatch list | 🔴 |
| 2 | Assign Driver to Trip | Manual selection of orders → select driver → create trip. Cross-cashier trips OK | 🔴 |
| 3 | Mark Out for Delivery | Record dispatched_at, orders → OUT_FOR_DELIVERY, driver status → "out" | 🔴 |
| 4 | Mark Returned | Record returned_at, orders → DELIVERED, driver → "available". **No settlement blocking** | 🔴 |
| 5 | **Per-Trip Settlement** 🔥 | cash_collected = Σ(order_total WHERE كاش). total_fees = Σ(delivery_fee ALL). No shortage tracking | 🔴 |
| 6 | Settlement Receipt | Per-trip: orders list with payment method + collected amount, summary totals | 🔴 |
| 7 | **End-of-Day Summary** 🔥 | All drivers: trips, orders, fees earned. Grand total = total driver expenses | 🔴 |
| 8 | Expense Entry (v1) | Manual: amount + description + category. Immutable. Future: auto from settlement | 🔴 |

### Settlement Rules:
| Payment | Driver Collects | Driver Hands Over |
|---------|----------------|-------------------|
| كاش | food + delivery_fee (everything) | everything |
| اونلاين | nothing (prepaid) | nothing |
| فيزا | ❌ NOT AVAILABLE FOR DELIVERY | — |

---

## 🖨️ feature/printing_flow — Silent Thermal Printing

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Kitchen Ticket | Auto on save. NO prices, NO customer info. Order # in LARGE BOLD. Per-item notes | 🔴 |
| 2 | Customer Receipt (4 variants) | Dine-in (table), Delivery (customer+driver+fee), Takeaway (انتظار banner), Pickup (customer+phone) | 🔴 |
| 3 | Daily Summary | Matches receipt photo format. Must print before shift close allowed | 🔴 |
| 4 | Driver Settlement | Per-trip receipt for cash accountability | 🔴 |
| 5 | Failure Handling | Log + badge icon. **Never show dialog, never block cashier** | 🔴 |

---

## 📊 feature/reports — Financial Summaries

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Aggregate by Type | صالة/تيك اواي/دليفري/استلام محل → count + revenue | 🔴 |
| 2 | Daily Summary | Shift-based, structured data (not print format) | 🔴 |
| 3 | Print Integration | Send to thermal printer, silent, exact format | 🔴 |
| 4 | Consistency Checks | Cross-validate sums, handle edge cases, no double-counting | 🔴 |

---

## 🔐 feature/user_permissions — Role-Based Access

| # | Task | Details | Status |
|---|------|---------|:---:|
| 1 | Role Model | CASHIER (orders, tracking, delivery), MANAGER (+reports, products, financial), ADMIN (+users) | 🔴 |
| 2 | PIN Storage | SHA-256 hash, UNIQUE per user, no recovery (admin resets) | 🔴 |
| 3 | Manager Override | PIN dialog → verify → action proceeds with audit trail. Per-action, doesn't change session | 🔴 |
| 4 | Audit Logging | Cancel, discount, shift open/close, user changes → audit_log table (JSON details) | 🔴 |
| 5 | Navigation Access | Sidebar items shown/hidden by role | 🔴 |

---

# 🧭 EXECUTION ROADMAP

| Phase | Scope | Depends On | Status |
|:---:|-------|:---:|:---:|
| **1** | Database + Models + Connection | — | 🔴 |
| **2** | Repositories + Base CRUD | Phase 1 | 🔴 |
| **3** | Auth Service + Login UI | Phase 2 | 🔴 |
| **4** | Product Service + POS View (core) | Phase 2 | 🔴 |
| **5** | Order Service + Kitchen Printing | Phase 4 | 🔴 |
| **6** | Payment Flow + Receipt Printing | Phase 5 | 🔴 |
| **7** | Tracking View + Status Transitions | Phase 5 | 🔴 |
| **8** | Customer/Delivery Service + Delivery View | Phase 5 | 🔴 |
| **9** | Financial Service + Shift Lifecycle | Phase 6 | 🔴 |
| **10** | Reports + Daily Summary | Phase 9 | 🔴 |
| **11** | Permissions + Audit + PIN Override | Phase 3 | 🔴 |
| **12** | Polish: Theme, White-Label, Config | All | 🔴 |

**Rule**: Never move to next phase if current one is unstable. Test in real workflow after each phase.

---

# 📌 Critical Business Rules Reference

### Order Type Requirements
| Type | Arabic | Requires |
|------|--------|----------|
| Dine-In | صالة | Table number |
| Delivery | دليفري | Phone + Address + Zone |
| Takeaway | تيك اواي | Nothing extra |
| Pickup | استلام محل | Phone |

### Payment Availability
| Method | Dine-In | Takeaway | Pickup | Delivery |
|--------|:---:|:---:|:---:|:---:|
| كاش | ✅ | ✅ | ✅ | ✅ driver collects ALL |
| فيزا | ✅ | ✅ | ✅ | ❌ NOT available |
| اونلاين | ✅ | ✅ | ✅ | ✅ driver collects NOTHING |

### Permission Matrix
| Action | CASHIER | MANAGER | ADMIN |
|--------|:---:|:---:|:---:|
| Create order | ✅ | ✅ | ✅ |
| Apply discount | ❌ (override) | ✅ | ✅ |
| Cancel order | ❌ (override) | ✅ | ✅ |
| Remove item from saved order | ❌ (override) | ✅ | ✅ |
| Manage products | ❌ | ✅ | ✅ |
| Check-in/out drivers | ✅ | ✅ | ✅ |
| Add drivers | ❌ | ✅ | ✅ |
| Open shift | ✅ | ✅ | ✅ |
| Close/transfer shift | ❌ | ✅ | ✅ |
| View reports | ❌ | ✅ | ✅ |
| Manage users | ❌ | ❌ | ✅ |

### Financial Formulas
```
subtotal         = Σ(qty × unit_price) for all items
service          = subtotal × (service_pct / 100)
total            = subtotal + service + delivery_fee - discount
change           = max(0, paid - total)
restaurant_revenue = total - delivery_fee
expected_cash    = total_sales - total_expenses - pending_delivery - pending_dinein - pending_kitchen
```

---

# ❌ Removed from Original Design

| Item | Reason |
|------|--------|
| Modifier Dialog | No modifier system — each variation is separate product |
| modifiers table | Eliminated from schema |
| product_modifiers table | Eliminated from schema |
| order_item_modifiers table | Eliminated from schema |
| Dedicated Expenses View | Deferred to v2 — lives inside Financial View |
| Fast user switch | Full logout/login every time (Option A) |
| Draft system | Unsaved orders = memory only |
| Touch screen optimization | Input is mouse + keyboard |

---

✅ **ARCHITECTURE COMPLETE — READY FOR IMPLEMENTATION**
